"""
Parse a SCORM 2004 PIF (.zip) and return package metadata.
Rejects SCORM 1.2 and full Sequencing & Navigation packages with clear messages.
"""
import zipfile
import io
from typing import Optional
from xml.etree import ElementTree as ET
from dataclasses import dataclass, field

# IMS/ADL namespace map
NS = {
    "imscp":  "http://www.imsglobal.org/xsd/imscp_v1p1",
    "adlcp":  "http://www.adlnet.org/xsd/adlcp_v1p3",
    "adlseq": "http://www.adlnet.org/xsd/adlseq_v1p3",
    "adlnav": "http://www.adlnet.org/xsd/adlnav_v1p3",
    "imsss":  "http://www.imsglobal.org/xsd/imsss",
}


@dataclass
class ScormPackageMeta:
    identifier: str
    title: str
    version: str
    edition: str
    launch_href: str
    mastery_score: Optional[float]
    sequencing_mode: str          # single_sco | simple_flow
    sco_identifiers: list[str] = field(default_factory=list)


def parse_scorm_zip(zip_bytes: bytes) -> ScormPackageMeta:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = [n.lower() for n in zf.namelist()]
        orig_names = zf.namelist()
        manifest_idx = next((i for i, n in enumerate(names) if n == "imsmanifest.xml"), None)
        if manifest_idx is None:
            raise ValueError("Not a SCORM PIF: missing imsmanifest.xml")
        manifest_xml = zf.read(orig_names[manifest_idx])

    root = ET.fromstring(manifest_xml)

    # --- detect schema version ---
    schema_version = ""
    # try both namespaced and non-namespaced
    for sv_path in [".//imscp:metadata/imscp:schemaversion", ".//metadata/schemaversion"]:
        try:
            el = root.find(sv_path, NS)
            if el is not None:
                schema_version = el.text or ""
                break
        except Exception:
            pass

    if "1.2" in schema_version or "SCORM 1.2" in schema_version:
        raise ValueError(
            "SCORM 1.2 packages are not supported. "
            "Please provide a SCORM 2004 (3rd or 4th Edition) package."
        )

    edition = "2004"
    if "4th" in schema_version or "4.0" in schema_version:
        edition = "2004 4th Edition"
    elif "3rd" in schema_version or "3.0" in schema_version:
        edition = "2004 3rd Edition"

    identifier = root.get("identifier", "unknown")

    # --- title from first organization ---
    title = "Untitled"
    for org_path in [".//imscp:organizations/imscp:organization/imscp:title",
                     ".//organizations/organization/title"]:
        try:
            el = root.find(org_path, NS)
            if el is not None and el.text:
                title = el.text.strip()
                break
        except Exception:
            pass

    # --- find SCOs ---
    sco_identifiers: list[str] = []
    launch_href: Optional[str] = None
    mastery_score: Optional[float] = None

    resources_el = root.find(".//imscp:resources", NS) or root.find(".//resources")
    if resources_el is not None:
        for res in list(resources_el):
            adlcp_ns = NS["adlcp"]
            res_type = res.get("type", "")
            scorm_type = res.get(f"{{{adlcp_ns}}}scormType", "")

            if scorm_type.lower() == "sco" or "sco" in res_type.lower():
                href = res.get("href", "")
                if href and not launch_href:
                    launch_href = href
                sco_id = res.get("identifier", f"sco_{len(sco_identifiers)}")
                sco_identifiers.append(sco_id)

                # mastery score from adlcp:masteryScore
                ms = res.get(f"{{{adlcp_ns}}}masteryScore")
                if ms and mastery_score is None:
                    try:
                        v = float(ms)
                        mastery_score = v / 100.0 if v > 1.0 else v
                    except ValueError:
                        pass

    if not launch_href:
        # Fallback: first resource with href
        for res in (list(resources_el) if resources_el is not None else []):
            href = res.get("href", "")
            if href:
                launch_href = href
                break

    if not launch_href:
        raise ValueError("No launchable resource found in manifest")

    # --- sequencing mode ---
    has_ss_rules = root.find(".//imsss:sequencingRules", NS) is not None
    has_ss_rollup = root.find(".//imsss:rollupRules", NS) is not None

    if len(sco_identifiers) <= 1:
        seq_mode = "single_sco"
    elif has_ss_rules or has_ss_rollup:
        raise ValueError(
            "This SCORM package uses Full Sequencing & Navigation rules "
            "(sequencingRules/rollupRules) which are not supported. "
            "Only single-SCO and simple linear flow packages are accepted."
        )
    else:
        seq_mode = "simple_flow"

    return ScormPackageMeta(
        identifier=identifier,
        title=title,
        version=schema_version,
        edition=edition,
        launch_href=launch_href,
        mastery_score=mastery_score,
        sequencing_mode=seq_mode,
        sco_identifiers=sco_identifiers,
    )


def extract_scorm_zip(zip_bytes: bytes, dest_prefix: str, upload_fn) -> list[str]:
    """Extract all files from the zip and upload via upload_fn(key, data, content_type).
    Returns list of uploaded keys."""
    from app.services.storage import content_type_for
    keys: list[str] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for item in zf.infolist():
            if item.is_dir():
                continue
            data = zf.read(item.filename)
            key = f"{dest_prefix}/{item.filename}"
            ct = content_type_for(item.filename)
            upload_fn(key, data, ct)
            keys.append(key)
    return keys
