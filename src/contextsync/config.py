"""ContextSync configuration — Pydantic-based parsing of .contextsync.yaml."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class SecurityMode(str, Enum):
    LOCAL = "local"
    HYBRID = "hybrid"
    CLOUD = "cloud"


class ApprovalMode(str, Enum):
    MANUAL = "manual"
    REVIEW = "review"
    AUTO = "auto"


class ChangeType(str, Enum):
    NEW_MODULE = "NEW_MODULE"
    DELETED_MODULE = "DELETED_MODULE"
    API_CHANGE = "API_CHANGE"
    DEPENDENCY_CHANGE = "DEPENDENCY_CHANGE"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    REFACTOR = "REFACTOR"
    BUGFIX = "BUGFIX"


class TreeConfig(BaseModel):
    filename: str = "CONTEXT.md"
    max_depth: int = 4
    auto_scaffold: bool = True
    min_files_for_context: int = 3
    min_entities_for_context: int = 2


class SalienceConfig(BaseModel):
    threshold: float = 0.4
    always_update_on: list[ChangeType] = Field(
        default_factory=lambda: [
            ChangeType.NEW_MODULE,
            ChangeType.DELETED_MODULE,
            ChangeType.API_CHANGE,
        ]
    )
    never_update_on: list[ChangeType] = Field(
        default_factory=lambda: [ChangeType.BUGFIX]
    )


class SurfaceConfig(BaseModel):
    path: str
    update_on: list[str] = Field(default_factory=list)


class ConsumptionAggregatorConfig(BaseModel):
    targets: list[str] = Field(default_factory=lambda: [".cursorrules", "AGENTS.md"])
    scope: str = "auto"  # auto | full | manual


class MCPConfig(BaseModel):
    enabled: bool = True
    port: int = 3100


class ConsumptionConfig(BaseModel):
    aggregator: ConsumptionAggregatorConfig = Field(default_factory=ConsumptionAggregatorConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)


class LLMConfig(BaseModel):
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"
    temperature: float = 0.2
    max_tokens_per_patch: int = 500
    send_code: bool = False  # if False, sends only AST summaries


class SecurityConfig(BaseModel):
    mode: SecurityMode = SecurityMode.HYBRID


class QAConfig(BaseModel):
    approval_mode: ApprovalMode = ApprovalMode.REVIEW
    max_diff_percent: float = 0.5  # flag if >50% of context changes
    verify_entities: bool = True
    verify_relationships: bool = True


class RelationshipDetectionConfig(BaseModel):
    detect_django_signals: bool = True
    detect_imports: bool = True
    detect_api_calls: bool = True


class MonorepoConfig(BaseModel):
    enabled: str = "auto"  # auto | true | false
    scope_to_codeowners: bool = True


class ContextSyncConfig(BaseModel):
    """Root configuration model for .contextsync.yaml."""
    version: int = 1
    tree: TreeConfig = Field(default_factory=TreeConfig)
    salience: SalienceConfig = Field(default_factory=SalienceConfig)
    surfaces: list[SurfaceConfig] = Field(default_factory=list)
    consumption: ConsumptionConfig = Field(default_factory=ConsumptionConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    qa: QAConfig = Field(default_factory=QAConfig)
    preserved_sections: list[str] = Field(
        default_factory=lambda: ["## Caveats", "## Decisions"]
    )
    relationships: RelationshipDetectionConfig = Field(
        default_factory=RelationshipDetectionConfig
    )
    monorepo: MonorepoConfig = Field(default_factory=MonorepoConfig)


CONFIG_FILENAME = ".contextsync.yaml"


def find_config(start_path: Path | None = None) -> Path | None:
    """Walk up from start_path to find .contextsync.yaml."""
    path = start_path or Path.cwd()
    path = path.resolve()

    while True:
        config_path = path / CONFIG_FILENAME
        if config_path.exists():
            return config_path
        parent = path.parent
        if parent == path:
            return None
        path = parent


def load_config(config_path: Path | None = None) -> ContextSyncConfig:
    """Load configuration from .contextsync.yaml.

    If no path is provided, searches up from cwd.
    If not found, returns defaults.
    """
    if config_path is None:
        config_path = find_config()

    if config_path is None or not config_path.exists():
        return ContextSyncConfig()

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return ContextSyncConfig()

    return ContextSyncConfig.model_validate(raw)


def save_config(config: ContextSyncConfig, path: Path) -> None:
    """Save configuration to .contextsync.yaml."""
    data = config.model_dump(mode="json")
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, indent=2)


def generate_default_config() -> str:
    """Generate a commented default config YAML string."""
    return """# ContextSync Configuration
# Docs: https://docs.contextsync.dev/config

version: 1

tree:
  filename: CONTEXT.md
  max_depth: 4
  auto_scaffold: true
  min_files_for_context: 3
  min_entities_for_context: 2

salience:
  threshold: 0.4
  always_update_on:
    - NEW_MODULE
    - DELETED_MODULE
    - API_CHANGE
  never_update_on:
    - BUGFIX

surfaces:
  - path: .cursorrules
    update_on: [pattern_change, new_convention]
  - path: AGENTS.md
    update_on: [new_module, architecture_change]

consumption:
  aggregator:
    targets: [.cursorrules, AGENTS.md]
    scope: auto
  mcp:
    enabled: true
    port: 3100

llm:
  provider: gemini
  model: gemini-2.5-flash
  temperature: 0.2
  max_tokens_per_patch: 500
  send_code: false

security:
  mode: hybrid

qa:
  approval_mode: review
  max_diff_percent: 0.5
  verify_entities: true
  verify_relationships: true

preserved_sections:
  - "## Caveats"
  - "## Decisions"

relationships:
  detect_django_signals: true
  detect_imports: true
  detect_api_calls: true

monorepo:
  enabled: auto
  scope_to_codeowners: true
"""
