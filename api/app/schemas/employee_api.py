"""
Typed mirror of the Employee API's GetFullDetails response shape:

    {"employeelist":[{"CPF":"...","NAME":"...","MAIL":"...", ...,
      "CONTROLLING": {...} | null, "L1": {...} | null, "L2": {...} | null,
      "IC_HRER": {...} | null, "SUBORDINATES": [...] | null,
      "IS_RETIRED": bool}]}

CONTROLLING/L1/L2/IC_HRER are the same shape recursively (one level deep in
practice, but modeled as fully recursive since the upstream API doesn't
document a hard depth limit). SUBORDINATES is accepted but deliberately not
walked recursively during sync — see services/sso.py's
upsert_user_from_employee_details for why (it would let one login trigger an
unbounded cascade of API calls across an entire reporting tree).
"""
from __future__ import annotations
from datetime import date
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class EmployeeDetails(BaseModel):
    cpf: str = Field(alias="CPF")
    name: str = Field(alias="NAME")
    mail: Optional[str] = Field(default=None, alias="MAIL")
    designation: Optional[str] = Field(default=None, alias="DESIGNATION")
    mobile: Optional[str] = Field(default=None, alias="MOBILE")
    posting: Optional[str] = Field(default=None, alias="POSTING")
    valid_upto: Optional[date] = Field(default=None, alias="VALIDUPTO")
    location: Optional[str] = Field(default=None, alias="LOCATION")
    gender: Optional[str] = Field(default=None, alias="GENDER")
    birth_date: Optional[date] = Field(default=None, alias="BIRTHDATE")
    controlling: Optional["EmployeeDetails"] = Field(default=None, alias="CONTROLLING")
    l1: Optional["EmployeeDetails"] = Field(default=None, alias="L1")
    l2: Optional["EmployeeDetails"] = Field(default=None, alias="L2")
    ic_hrer: Optional["EmployeeDetails"] = Field(default=None, alias="IC_HRER")
    # Accepted but not synced recursively — see module docstring.
    subordinates: Optional[List["EmployeeDetails"]] = Field(default=None, alias="SUBORDINATES")
    is_retired: bool = Field(default=False, alias="IS_RETIRED")

    model_config = {"populate_by_name": True}

    @field_validator("valid_upto", "birth_date", mode="before")
    @classmethod
    def _parse_date(cls, v):
        """The sample response mixes date formats across fields — VALIDUPTO
        as DD-MM-YYYY ("31-03-2046") but BIRTHDATE already ISO
        ("1986-04-01") — so this can't assume one format; it has to detect
        which it got. Segment length is the only reliable signal (a 4-digit
        first segment means the year is already leading, i.e. ISO)."""
        if v is None or v == "" or isinstance(v, date):
            return v
        if isinstance(v, str) and v.count("-") == 2:
            first, month, last = v.split("-")
            if len(first) == 4:
                return v  # already YYYY-MM-DD
            return f"{last}-{month}-{first}"  # DD-MM-YYYY -> YYYY-MM-DD
        return v


class EmployeeApiResponse(BaseModel):
    employeelist: List[EmployeeDetails] = Field(default_factory=list)
