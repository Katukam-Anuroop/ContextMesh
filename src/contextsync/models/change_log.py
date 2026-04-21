"""ChangeLog model — tracks every CDC operation for observability."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import relationship as sa_relationship

from contextsync.models.database import Base


class ChangeLogORM(Base):
    __tablename__ = "change_log"

    id = Column(String(16), primary_key=True)
    context_id = Column(String(16), ForeignKey("context_files.id"), nullable=False, index=True)
    commit_hash = Column(String(40), nullable=False)
    change_type = Column(String(50), nullable=False)
    salience = Column(Float, nullable=False)
    sections = Column(Text, nullable=True)  # JSON: which sections were patched
    patch_diff = Column(Text, nullable=True)
    llm_model = Column(String(100), nullable=True)
    token_cost = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    context_file = sa_relationship("ContextFileORM", back_populates="change_logs")


class ChangeLogCreate(BaseModel):
    """Schema for creating a change log entry."""
    context_id: str
    commit_hash: str
    change_type: str
    salience: float
    sections: Optional[str] = None
    patch_diff: Optional[str] = None
    llm_model: Optional[str] = None
    token_cost: Optional[float] = None

    model_config = {"from_attributes": True}


class ChangeLog(BaseModel):
    """Schema for reading a change log entry."""
    id: str
    context_id: str
    commit_hash: str
    change_type: str
    salience: float
    sections: Optional[str] = None
    patch_diff: Optional[str] = None
    llm_model: Optional[str] = None
    token_cost: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}
