from datetime import datetime
from pydantic import BaseModel, field_validator


class LevelCreate(BaseModel):
    code: str
    name: str
    rank: int

    @field_validator("code", "name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("field cannot be empty")
        return v


class LevelUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    rank: int | None = None


class LevelRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    code: str
    name: str
    rank: int
    created_at: datetime
