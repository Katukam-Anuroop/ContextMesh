"""Base LLM adapter — abstract interface for pluggable LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class PatchRequest:
    """Request to generate a context patch."""
    current_context: str  # Current CONTEXT.md content
    code_diff: str  # The git diff that triggered this update
    changed_files: list[str]  # List of changed file paths
    change_types: list[str]  # List of change type classifications
    changed_functions: list[str]  # Affected function names
    changed_classes: list[str]  # Affected class names
    directory_listing: str  # Current directory contents
    preserved_sections: list[str]  # Sections to never modify
    parent_context: Optional[str] = None  # Parent CONTEXT.md (if exists)
    scope_description: str = ""  # What this directory/module is about


@dataclass
class PatchResult:
    """Result of a context patch generation."""
    patched_content: str  # The updated CONTEXT.md content
    sections_modified: list[str]  # Which sections were changed
    confidence: float  # 0.0-1.0 confidence score
    model_used: str  # Which model generated this
    tokens_used: int  # Total tokens consumed
    cost_usd: float  # Estimated cost in USD


@dataclass
class ScaffoldRequest:
    """Request to generate initial CONTEXT.md content for a directory."""
    directory_path: str
    directory_listing: str  # Files and subdirs in this directory
    code_summaries: dict[str, str]  # file_path -> brief summary
    parent_context: Optional[str] = None
    project_root_context: Optional[str] = None


@dataclass
class ScaffoldResult:
    """Result of scaffold generation."""
    content: str
    model_used: str
    tokens_used: int
    cost_usd: float


class LLMAdapter(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate_patch(self, request: PatchRequest) -> PatchResult:
        """Generate a surgical patch to a CONTEXT.md file."""
        ...

    @abstractmethod
    async def generate_scaffold(self, request: ScaffoldRequest) -> ScaffoldResult:
        """Generate initial CONTEXT.md content for a new directory."""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model name/identifier."""
        ...
