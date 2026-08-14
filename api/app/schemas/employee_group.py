from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from app.models.employee_group import RuleOperator, GroupMatchType


class RuleInput(BaseModel):
    """Shape used both for real rules (field required) and the CPF-based
    hierarchy operators (field ignored — the CPF goes in value)."""
    field: str = ""
    operator: RuleOperator
    value: str


class EmployeeGroupRuleRead(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    field: str
    operator: RuleOperator
    value: str


class EmployeeGroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    match_type: GroupMatchType = GroupMatchType.all
    rules: List[RuleInput] = []


class EmployeeGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    match_type: Optional[GroupMatchType] = None


class EmployeeGroupRead(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    name: str
    description: Optional[str] = None
    match_type: GroupMatchType
    created_at: datetime
    updated_at: datetime
    rules: List[EmployeeGroupRuleRead] = []
    member_count: int = 0


class EmployeeGroupSummary(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    name: str
    description: Optional[str] = None
    match_type: GroupMatchType
    member_count: int = 0
    rule_count: int = 0


class PreviewRequest(BaseModel):
    match_type: GroupMatchType = GroupMatchType.all
    rules: List[RuleInput]


class GroupMember(BaseModel):
    id: int
    name: str
    email: str
    cpf: Optional[str] = None
    designation: Optional[str] = None


class GroupMembersResponse(BaseModel):
    total: int
    members: List[GroupMember]


class PreviewMember(BaseModel):
    id: int
    name: str
    email: str
    designation: Optional[str] = None


class PreviewResponse(BaseModel):
    total: int
    sample: List[PreviewMember]


class CourseTargetGroupRead(BaseModel):
    id: int
    group_id: int
    group_name: str
    member_count: int


class CourseTargetGroupCreate(BaseModel):
    group_id: int
