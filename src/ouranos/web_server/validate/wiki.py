from __future__ import annotations

from datetime import datetime
from pathlib import Path

from anyio import Path as ioPath
from pydantic import Field, field_validator

from gaia_validators import MissingValue, missing

from ouranos.core.database.models.app import ModificationType
from ouranos.core.validate.base import BaseModel


class WikiTopicInfo(BaseModel):
    name: str
    description: str | None = None
    path: str

    @field_validator("path", mode="before")
    def parse_path(cls, value):
        if isinstance(value, (ioPath, Path)):
            return str(value)
        return value


class WikiTopicCreationPayload(BaseModel):
    name: str
    description: str | None = None


class WikiTopicUpdatePayload(BaseModel):
    name: str | MissingValue = missing
    description: str | MissingValue = missing


class WikiTopicTemplatePayload(BaseModel):
    content: str


class WikiArticleInfo(BaseModel):
    topic: str = Field(validation_alias="topic_name")
    name: str
    description: str | None = None
    version: int
    path: str = Field(validation_alias="content_path")

    @field_validator("path", mode="before")
    def parse_path(cls, value):
        if isinstance(value, (ioPath, Path)):
            return str(value)
        return value


class WikiArticleCreationPayload(BaseModel):
    # topic is provided by the route
    name: str
    content: str
    description: str | None = None
    # author_id is provided by the route


class WikiArticleUpdatePayload(BaseModel):
    # topic is provided by the route
    name : str | MissingValue = missing
    content: str | MissingValue = missing
    description: str | MissingValue = missing
    # author_id is provided by the route


class WikiArticleModificationInfo(BaseModel):
    # topic is provided by the route
    topic: str = Field(validation_alias="topic_name")
    article: str = Field(validation_alias="article_name")
    article_version: int
    author_id: int
    timestamp: datetime
    modification_type: ModificationType


class WikiArticlePictureInfo(BaseModel):
    topic: str = Field(validation_alias="topic_name")
    article: str = Field(validation_alias="article_name")
    name: str
    path: str

    @field_validator("path", mode="before")
    def parse_path(cls, value):
        if isinstance(value, (ioPath, Path)):
            return str(value)
        return value


class WikiArticlePictureCreationPayload(BaseModel):
    name: str
    content: bytes
