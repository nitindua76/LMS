from typing import Optional, List
from pydantic import BaseModel, field_validator
from app.models.course import ContentType


class ContentItemCreate(BaseModel):
    order_index: int
    type: ContentType
    url: str                          # display label (always required)
    video_duration_sec: Optional[int] = None

    @field_validator("url")
    @classmethod
    def url_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("url cannot be empty")
        return v


class ContentItemUpdate(BaseModel):
    order_index: Optional[int] = None
    type: Optional[ContentType] = None
    url: Optional[str] = None
    storage_key: Optional[str] = None
    video_duration_sec: Optional[int] = None


class ContentItemRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    section_id: int
    order_index: int
    type: ContentType
    url: str
    storage_key: Optional[str] = None
    video_duration_sec: Optional[int] = None


class SectionCreate(BaseModel):
    order_index: int
    title: str

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title cannot be empty")
        return v


class SectionUpdate(BaseModel):
    order_index: Optional[int] = None
    title: Optional[str] = None


class SectionReorder(BaseModel):
    section_ids: List[int]


class SectionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    course_id: int
    order_index: int
    title: str
    content_items: List[ContentItemRead] = []


class SectionSummary(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    order_index: int
    title: str
