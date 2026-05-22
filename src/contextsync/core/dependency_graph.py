import ast
import os
from pathlib import Path
from typing import Set

class PythonDependencyExtractor:
    """
    Parses a target directory's Python source code using AST representation.
    Extracts all 'import X' and 'from Y import Z' statements, mathematically
    resolves them to local repository directory paths, and returns them to be
    used as lateral context graph edges.
    """
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()

    def _resolve_module_to_path(self, module_name: str) -> Path | None:
        """
        Attempts to resolve Python dot-notation `package.module.cls` into a physical 
        directory path mapping if that module exists locally in the repository.
        Ignores third-party packages (like 'requests' or 'django') logically since they
        won't map to local files.
        """
        if not module_name:
            return None
            
        parts = module_name.split('.')
        
        # Try progressively dropping parts from the right
        # e.g., if module_name is "contextsync.models.context_file.ContextNode",
        # we will try to resolve the longest physical file/dir match.
        for i in range(len(parts), 0, -1):
            sub_parts = parts[:i]
            # Standard python repository heuristics
            search_bases = [self.repo_root, self.repo_root / "src", self.repo_root / "lib"]
            
            for base in search_bases:
                candidate = base.joinpath(*sub_parts)
                if candidate.exists():
                    if candidate.is_file():
                        return candidate.parent.resolve()
                    elif candidate.is_dir():
                        return candidate.resolve()
                        
                # Also try the .py extension directly
                candidate_file = base.joinpath(*sub_parts).with_suffix('.py')
                if candidate_file.exists() and candidate_file.is_file():
                    return candidate_file.parent.resolve()
                    
        return None

    def extract_dependencies(self, target_dir: Path) -> Set[Path]:
        """
        Walks the directory, parses all .py files, and returns a set of unique 
        directory dependencies (excluding itself).
        """
        dependencies = set()
        target_dir = target_dir.resolve()
        
        if not target_dir.exists() or not target_dir.is_dir():
            return dependencies
            
        for root, dirs, files in os.walk(target_dir):
            # Ignore hidden and cache directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            
            for file in files:
                if file.endswith('.py'):
                    file_path = Path(root) / file
                    try:
                        content = file_path.read_text(encoding='utf-8')
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    resolved = self._resolve_module_to_path(alias.name)
                                    if resolved and resolved != target_dir:
                                        dependencies.add(resolved)
                                        
                            elif isinstance(node, ast.ImportFrom):
                                if node.module:
                                    resolved = self._resolve_module_to_path(node.module)
                                    if node.level > 0:
                                        # Handle relative imports (e.g., from ..models import X)
                                        # For simplicity in V1, we approximate resolution by parent paths
                                        pass 
                                    if resolved and resolved != target_dir:
                                        dependencies.add(resolved)
                    except Exception:
                        pass # Ignore syntax errors in target codebase
                        
        return dependencies
