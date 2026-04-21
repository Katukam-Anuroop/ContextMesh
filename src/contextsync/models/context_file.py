"""ContextFile model — represents a CONTEXT.md in the tree."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship as sa_relationship

from contextsync.models.database import Base


# --- SQLAlchemy ORM Model ---

class ContextFileORM(Base):
    __tablename__ = "context_files"
    __table_args__ = (UniqueConstraint("repo", "path", name="uq_repo_path"),)

    id = Column(String(16), primary_key=True)
    repo = Column(String(500), nullable=False, index=True)
    path = Column(String(1000), nullable=False)
    parent_id = Column(String(16), ForeignKey("context_files.id"), nullable=True)
    content = Column(Text, nullable=False, default="")
    sync_hash = Column(String(40), nullable=False, default="")
    synced_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    cqi_score = Column(Float, nullable=True)

    # Relationships
    parent = sa_relationship("ContextFileORM", remote_side=[id], backref="children")
    outgoing_relationships = sa_relationship(
        "RelationshipORM", foreign_keys="RelationshipORM.source_id", back_populates="source"
    )
    incoming_relationships = sa_relationship(
        "RelationshipORM", foreign_keys="RelationshipORM.target_id", back_populates="target"
    )
    change_logs = sa_relationship("ChangeLogORM", back_populates="context_file")
    entities = sa_relationship("EntityORM", back_populates="context_file")


# --- Pydantic Schemas ---

class ContextFileCreate(BaseModel):
    """Schema for creating a new context file entry."""
    repo: str
    path: str
    parent_id: Optional[str] = None
    content: str = ""
    sync_hash: str = ""

    model_config = {"from_attributes": True}


class ContextFile(BaseModel):
    """Schema for reading a context file entry."""
    id: str
    repo: str
    path: str
    parent_id: Optional[str] = None
    content: str
    sync_hash: str
    synced_at: datetime
    cqi_score: Optional[float] = None

    model_config = {"from_attributes": True}
