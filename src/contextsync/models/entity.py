"""Entity model — tracks code entities referenced in context files for QA validation."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship as sa_relationship

from contextsync.models.database import Base


class EntityORM(Base):
    __tablename__ = "entities"

    id = Column(String(16), primary_key=True)
    context_id = Column(String(16), ForeignKey("context_files.id"), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    entity_type = Column(String(50), nullable=False)  # function | class | file | module
    exists = Column(Boolean, default=True)
    last_verified = Column(DateTime, nullable=True)

    context_file = sa_relationship("ContextFileORM", back_populates="entities")


class EntityCreate(BaseModel):
    """Schema for creating an entity."""
    context_id: str
    name: str
    entity_type: str
    exists: bool = True

    model_config = {"from_attributes": True}


class Entity(BaseModel):
    """Schema for reading an entity."""
    id: str
    context_id: str
    name: str
    entity_type: str
    exists: bool
    last_verified: Optional[datetime] = None

    model_config = {"from_attributes": True}
