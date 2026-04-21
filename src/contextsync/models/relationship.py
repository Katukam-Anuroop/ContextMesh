"""Relationship model — semantic links between context files."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Boolean, Column, ForeignKey, String, Text
from sqlalchemy.orm import relationship as sa_relationship

from contextsync.models.database import Base


class RelationshipORM(Base):
    __tablename__ = "relationships"

    source_id = Column(String(16), ForeignKey("context_files.id"), primary_key=True)
    target_id = Column(String(16), ForeignKey("context_files.id"), primary_key=True)
    rel_type = Column(String(50), primary_key=True)  # imports | signals | calls | uses
    description = Column(Text, nullable=True)
    verified = Column(Boolean, default=False)

    source = sa_relationship(
        "ContextFileORM", foreign_keys=[source_id], back_populates="outgoing_relationships"
    )
    target = sa_relationship(
        "ContextFileORM", foreign_keys=[target_id], back_populates="incoming_relationships"
    )


class RelationshipCreate(BaseModel):
    """Schema for creating a relationship."""
    source_id: str
    target_id: str
    rel_type: str
    description: Optional[str] = None
    verified: bool = False

    model_config = {"from_attributes": True}


class Relationship(BaseModel):
    """Schema for reading a relationship."""
    source_id: str
    target_id: str
    rel_type: str
    description: Optional[str] = None
    verified: bool

    model_config = {"from_attributes": True}
