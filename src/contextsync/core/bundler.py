import os
from pathlib import Path
from typing import List, Optional
import pathspec

from contextsync.config import ContextSyncConfig
from contextsync.core.tree_walker import TreeWalker, ContextNode


class ProgressiveBundler:
    """
    Constructs a highly-optimized XML payload by providing FULL raw source code
    only for the active 'target_directory', and compressing all other regions 
    of the repository into their lightweight CONTEXT.md summaries.
    """

    def __init__(self, repo_root: Path, config: ContextSyncConfig):
        self.repo_root = repo_root
        self.walker = TreeWalker(self.repo_root, config)
        self.walker.build_tree()
        self._gitignore_spec = self._load_gitignore()

    def _load_gitignore(self) -> pathspec.PathSpec:
        """Loads repository .gitignore to avoid bundling cache/env files."""
        gitignore_path = self.repo_root / ".gitignore"
        lines = []
        if gitignore_path.exists():
            with open(gitignore_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        # Always exclude standard generated files
        lines.extend([".git/", "__pycache__/", "venv/", ".env", "node_modules/"])
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)

    def _should_include_file(self, file_path: Path) -> bool:
        """Determines if a raw source file should be bundled based on gitignore and extensions."""
        rel_path = file_path.relative_to(self.repo_root).as_posix()
        if self._gitignore_spec.match_file(rel_path):
            return False
            
        allowed_extensions = {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".md", ".json"}
        return file_path.suffix in allowed_extensions

    def _get_working_zone_code(self, target_node: ContextNode) -> str:
        """
        Deep inspection mapping: Recursively extracts raw source code 
        from the active directory.
        """
        xml_fragments = []
        xml_fragments.append(f'  <working_directory path="{target_node.path}">')
        
        target_dir_path = self.repo_root / target_node.path
        
        if target_dir_path.exists() and target_dir_path.is_dir():
            for root, dirs, files in os.walk(target_dir_path):
                # Filter dirs in place to respect gitignore
                dirs[:] = [d for d in dirs if not self._gitignore_spec.match_file(
                    Path(root).joinpath(d).relative_to(self.repo_root).as_posix() + "/"
                )]
                
                for file_name in files:
                    file_path = Path(root) / file_name
                    if self._should_include_file(file_path):
                        rel_file = file_path.relative_to(self.repo_root).as_posix()
                        
                        try:
                            # Read code payload
                            content = file_path.read_text(encoding="utf-8")
                            xml_fragments.append(f'    <file name="{rel_file}">')
                            xml_fragments.append(content)
                            xml_fragments.append(f'    </file>')
                        except UnicodeDecodeError:
                            pass # Skip binaries
                            
        xml_fragments.append('  </working_directory>')
        return "\n".join(xml_fragments)

    def _get_mesh_zone_summaries(self, active_node: ContextNode) -> str:
        """
        Shallow inspection mapping: Walks the entire context DAG (parents, children, laterals)
        and extracts ONLY the `.contextmesh` summaries for non-active components.
        """
        xml_fragments = []
        
        # We need all nodes from the tree except the active_node
        all_nodes = self.walker._tree.values()
        
        for node in all_nodes:
            if node.path == active_node.path:
                continue # Handled by the working zone deep-inspection
                
            xml_fragments.append(f'  <module name="{node.path}">')
            summary_content = "No context summary generated yet."
            if node.content:
                summary_content = node.content
            xml_fragments.append(f'    <summary>\n{summary_content}\n    </summary>')
            xml_fragments.append('  </module>')
            
        return "\n".join(xml_fragments)

    def generate_bundle(self, target_path: str) -> str:
        """
        Main API entry point: Generates the master progressive XML payload.
        """
        # Ensure we have a valid node target
        target_abs = self.repo_root / target_path
        active_node = self.walker._tree.get(target_abs.resolve())
        if not active_node:
            # Fallback to creating a pseudo node if directory exists but has no context
            target_abs = self.repo_root / target_path
            if target_abs.exists() and target_abs.is_dir():
                active_node = ContextNode(path=target_abs / self.walker.context_filename, dir_path=target_abs, depth=0)
            else:
                return f"<error>Target directory '{target_path}' does not exist.</error>"

        mesh_zone = self._get_mesh_zone_summaries(active_node)
        working_zone = self._get_working_zone_code(active_node)
        
        return f"""<context_mesh>
<!-- Architectural Context (The Mesh Zone) -->
{mesh_zone}

<!-- Active Working Context (Deep Inspection) -->
{working_zone}
</context_mesh>"""
