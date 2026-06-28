"""Parse a cmi5 course structure package (cmi5.xml)."""
import io
import zipfile
from typing import Optional
from xml.etree import ElementTree as ET
from dataclasses import dataclass, field

CMI5_NS = "https://w3id.org/xapi/profiles/cmi5/v1/CourseStructure.xsd"


@dataclass
class Cmi5AU:
    id: str
    title: str
    launch_href: str
    move_on: str        # CompletedOrPassed | Passed | Completed | CompletedAndPassed | NotApplicable
    mastery_score: Optional[float]


@dataclass
class Cmi5PackageMeta:
    identifier: str
    title: str
    aus: list[Cmi5AU] = field(default_factory=list)


def _text(el, *paths) -> str:
    """Try multiple element paths and return first non-empty text."""
    for path in paths:
        try:
            found = el.find(path)
            if found is not None and found.text:
                return found.text.strip()
        except Exception:
            pass
    return ""


def parse_cmi5_zip(zip_bytes: bytes) -> Cmi5PackageMeta:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names_lower = [n.lower() for n in zf.namelist()]
        orig_names  = zf.namelist()
        idx = next((i for i, n in enumerate(names_lower) if n == "cmi5.xml"), None)
        if idx is None:
            raise ValueError("Not a cmi5 package: missing cmi5.xml")
        xml_bytes = zf.read(orig_names[idx])

    root = ET.fromstring(xml_bytes)

    def ns(tag):
        return f"{{{CMI5_NS}}}{tag}"

    def find_all(el, tag):
        # Try with namespace and without
        results = el.findall(f".//{ns(tag)}")
        if not results:
            results = el.findall(f".//{tag}")
        return results

    def find_one(el, tag):
        r = el.find(f".//{ns(tag)}")
        if r is None:
            r = el.find(f".//{tag}")
        return r

    identifier = root.get("id", "unknown-cmi5")

    title_el = find_one(root, "title")
    if title_el is not None:
        ls = title_el.find(f".//{ns('langstring')}") or title_el.find(".//langstring")
        title = ls.text.strip() if ls is not None and ls.text else (title_el.text or "Untitled")
    else:
        title = "Untitled"

    aus: list[Cmi5AU] = []
    for au_el in find_all(root, "au"):
        au_id = au_el.get("id", f"au_{len(aus)}")

        au_title_el = find_one(au_el, "title")
        if au_title_el is not None:
            ls = au_title_el.find(f".//{ns('langstring')}") or au_title_el.find(".//langstring")
            au_title = ls.text.strip() if ls is not None and ls.text else au_id
        else:
            au_title = au_id

        url_el = find_one(au_el, "url")
        launch_href = url_el.text.strip() if url_el is not None and url_el.text else ""

        move_on = au_el.get("moveOn", "CompletedOrPassed")
        ms_str = au_el.get("masteryScore")
        mastery_score: Optional[float] = None
        if ms_str:
            try:
                mastery_score = float(ms_str)
            except ValueError:
                pass

        aus.append(Cmi5AU(
            id=au_id,
            title=au_title,
            launch_href=launch_href,
            move_on=move_on,
            mastery_score=mastery_score,
        ))

    if not aus:
        raise ValueError("cmi5.xml contains no <au> elements")

    return Cmi5PackageMeta(identifier=identifier, title=title, aus=aus)


def extract_cmi5_zip(zip_bytes: bytes, dest_prefix: str, upload_fn) -> list[str]:
    """Extract all files and upload via upload_fn(key, data, content_type)."""
    from app.services.storage import content_type_for
    keys: list[str] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for item in zf.infolist():
            if item.is_dir():
                continue
            data = zf.read(item.filename)
            key = f"{dest_prefix}/{item.filename}"
            upload_fn(key, data, content_type_for(item.filename))
            keys.append(key)
    return keys
