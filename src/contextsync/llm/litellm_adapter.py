"""LiteLLM-based adapter — unified interface for Gemini, OpenAI, Ollama, and 100+ providers."""

from __future__ import annotations

import json
from typing import Optional

import litellm
from litellm import acompletion

from contextsync.llm.base import (
    LLMAdapter,
    PatchRequest,
    PatchResult,
    ScaffoldRequest,
    ScaffoldResult,
)

# Suppress LiteLLM's verbose logging
litellm.suppress_debug_info = True


PATCH_SYSTEM_PROMPT = """<persona>
You are ContextSync, an expert Senior Staff Engineer responsible for maintaining project documentation.
Your job is to surgically update CONTEXT.md files based on code diffs to prevent context drift.
</persona>

<instructions>
1. You will be provided with the `<current_context>`, a `<git_diff_summary>`, and a `<directory_structure>`.
2. Analyze exactly what changed in the code and determine which sections of the CONTEXT.md are affected.
3. Apply surgical updates. DO NOT rewrite sections that are unaffected.
4. Keep the exact structural format of the existing CONTEXT.md.
5. Use highly precise, factual language. Reference specific classes, functions, and files.
</instructions>

<negative_constraints>
- NEVER invent relationships or dependencies that are not in the diff or structure.
- NEVER modify sections listed as "preserved".
- NEVER use marketing language or generic phrases like "handles the logic".
- NEVER output conversational filler (e.g. "Here is the updated file").
</negative_constraints>

<output_format>
You must structure your response exactly like this:

<analysis>
(Write a brief step-by-step reasoning on what changed and which sections you will modify)
</analysis>

<updated_context>
(The fully updated raw markdown of the CONTEXT.md file goes here)
</updated_context>
</output_format>"""

SCAFFOLD_SYSTEM_PROMPT = """<persona>
You are ContextSync, an expert Senior Staff Engineer responsible for creating high-quality architectural documentation.
Your job is to generate a pristine CONTEXT.md file for a given directory to help AI coding assistants deeply understand the codebase.
</persona>

<instructions>
1. You will be provided with the `<directory_path>`, `<directory_listing>`, and rich `<code_analysis>` including function signatures, classes, and docstrings.
2. Read the code analysis carefully to understand the data models, API surfaces, and internal patterns.
3. Generate a highly technical, precise CONTEXT.md.
</instructions>

<negative_constraints>
- NEVER use vague phrases like "defines the core model" or "handles business logic". Name exact classes and their purposes.
- NEVER invent information not present in the code analysis. If uncertain, append `[inferred]`.
- NEVER output conversational filler (e.g. "Here is the documentation").
</negative_constraints>

<context_template>
<!-- CONTEXT.md v1 — managed by ContextSync -->

# {Module Name}

## Purpose
One clear, technical sentence about what this module does and why it exists in the system.

## Key Components
(List the most important files. For each, list key classes (with bases) and major functions with signatures.)
### {filename.py}
- `ClassName(BaseClass)` — brief purpose
  - `method_name(args)` — brief purpose
- `function_name(args)` — brief purpose

## Architecture & Patterns
(What design patterns are used? Extracted from decorators, imports, and base classes.)

## Relationships
- **→ target_module**: explicit dependency description
- **← source_module**: explicit dependency description
</context_template>

<output_format>
You must structure your response exactly like this:

<analysis>
(Briefly reason about the module's core purpose and key entities based on the analysis)
</analysis>

<updated_context>
(The generated markdown following the template goes here)
</updated_context>
</output_format>"""


class LiteLLMAdapter(LLMAdapter):
    """Unified LLM adapter using LiteLLM for multi-provider support."""

    def __init__(
        self,
        model: str = "gemini/gemini-2.5-flash",
        temperature: float = 0.2,
        max_tokens: int = 2000,
        api_key: Optional[str] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._extra_kwargs: dict = {}

        # Handle Ollama API key for hosted Ollama services
        if "ollama" in model.lower():
            import os
            ollama_key = api_key or os.environ.get("OLLAMA_API_KEY", "")
            ollama_base = os.environ.get("OLLAMA_API_BASE", "")

            if ollama_key:
                # Hosted Ollama service — pass key as api_key
                self._extra_kwargs["api_key"] = ollama_key
                # Default to Ollama cloud API if no custom base set
                if not ollama_base:
                    ollama_base = "https://api.ollama.com"
                self._extra_kwargs["api_base"] = ollama_base
        elif api_key:
            if "gemini" in model:
                litellm.api_key = api_key
            elif "gpt" in model or "openai" in model:
                litellm.api_key = api_key

    async def generate_patch(self, request: PatchRequest) -> PatchResult:
        """Generate a surgical context patch via LLM."""
        user_prompt = self._build_patch_prompt(request)

        response = await acompletion(
            model=self.model,
            messages=[
                {"role": "system", "content": PATCH_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            **self._extra_kwargs,
        )

        content = response.choices[0].message.content or ""
        usage = response.usage

        # Try to extract from standard XML block
        import re
        match = re.search(r"<updated_context>([\s\S]*?)</updated_context>", content)
        if match:
            content = match.group(1).strip()
        else:
            content = content.replace("<analysis>", "").replace("</analysis>", "").strip()

        # Extract which sections were modified by comparing
        sections_modified = self._detect_modified_sections(
            request.current_context, content
        )

        return PatchResult(
            patched_content=content.strip(),
            sections_modified=sections_modified,
            confidence=0.8,  # TODO: derive from response metadata
            model_used=self.model,
            tokens_used=(usage.total_tokens if usage else 0),
            cost_usd=self._estimate_cost(usage.total_tokens if usage else 0),
        )

    async def generate_scaffold(self, request: ScaffoldRequest) -> ScaffoldResult:
        """Generate initial CONTEXT.md content."""
        user_prompt = self._build_scaffold_prompt(request)

        response = await acompletion(
            model=self.model,
            messages=[
                {"role": "system", "content": SCAFFOLD_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            **self._extra_kwargs,
        )

        content = response.choices[0].message.content or ""
        usage = response.usage

        # Try to extract from standard XML block
        import re
        match = re.search(r"<updated_context>([\s\S]*?)</updated_context>", content)
        if match:
            content = match.group(1).strip()
        else:
            content = content.replace("<analysis>", "").replace("</analysis>", "").strip()

        return ScaffoldResult(
            content=content.strip(),
            model_used=self.model,
            tokens_used=(usage.total_tokens if usage else 0),
            cost_usd=self._estimate_cost(usage.total_tokens if usage else 0),
        )

    def get_model_name(self) -> str:
        return self.model

    def _build_patch_prompt(self, request: PatchRequest) -> str:
        """Build the user prompt for patch generation."""
        preserved_note = ""
        if request.preserved_sections:
            preserved_note = (
                f"\n\nPRESERVED SECTIONS (DO NOT MODIFY):\n"
                + "\n".join(f"- {s}" for s in request.preserved_sections)
            )

        parent_note = ""
        if request.parent_context:
            parent_note = (
                f"\n\nPARENT CONTEXT.md (for reference only — do not duplicate):\n"
                f"```\n{request.parent_context[:500]}\n```"
            )

        return f"""<current_context>
{request.current_context}
</current_context>

<git_diff_summary>
- Changed files: {', '.join(request.changed_files[:20])}
- Change types: {', '.join(request.change_types[:10])}
- Changed functions: {', '.join(request.changed_functions[:15])}
- Changed classes: {', '.join(request.changed_classes[:10])}
</git_diff_summary>

<directory_structure>
{request.directory_listing}
</directory_structure>
{preserved_note}{parent_note}"""

    def _build_scaffold_prompt(self, request: ScaffoldRequest) -> str:
        """Build the user prompt for scaffold generation."""
        summaries = "\n".join(
            f"- `{path}`: {summary}"
            for path, summary in list(request.code_summaries.items())[:30]
        )

        parent_note = ""
        if request.parent_context:
            parent_note = f"\n\n<parent_context>\n{request.parent_context[:500]}\n</parent_context>"

        return f"""<directory_path>{request.directory_path}</directory_path>

<directory_listing>
{request.directory_listing}
</directory_listing>

<code_analysis>
{summaries}
</code_analysis>
{parent_note}"""

    def _detect_modified_sections(self, original: str, patched: str) -> list[str]:
        """Detect which ## sections were modified."""
        import re

        def extract_sections(text: str) -> dict[str, str]:
            sections: dict[str, str] = {}
            current_header = ""
            current_content: list[str] = []

            for line in text.split("\n"):
                if line.startswith("## "):
                    if current_header:
                        sections[current_header] = "\n".join(current_content)
                    current_header = line.strip()
                    current_content = []
                elif current_header:
                    current_content.append(line)

            if current_header:
                sections[current_header] = "\n".join(current_content)

            return sections

        orig_sections = extract_sections(original)
        new_sections = extract_sections(patched)

        modified = []
        for header in set(list(orig_sections.keys()) + list(new_sections.keys())):
            if orig_sections.get(header) != new_sections.get(header):
                modified.append(header)

        return modified

    def _estimate_cost(self, total_tokens: int) -> float:
        """Rough cost estimation based on model."""
        # Per-token costs (approximate, in USD)
        costs = {
            "gemini": 0.000_000_15,  # Gemini Flash
            "gpt-4o-mini": 0.000_000_30,
            "gpt-4o": 0.000_005,
            "ollama": 0.0,  # Local, free
        }
        for key, cost in costs.items():
            if key in self.model.lower():
                return total_tokens * cost
        return total_tokens * 0.000_000_30  # Default to cheap model pricing
