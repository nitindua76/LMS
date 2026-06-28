from datetime import datetime
from pydantic import BaseModel, field_validator


class DisciplineCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        return v


class DisciplineUpdate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        return v


class DisciplineRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    created_at: datetime
