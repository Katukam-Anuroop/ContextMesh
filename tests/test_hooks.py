import os
import shutil
import tempfile
from pathlib import Path
import unittest

import click

from contextsync.cli.hooks import install
from contextsync.cli.app import init_ci

class TestHooks(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory structure representing a project
        self.test_dir = Path(tempfile.mkdtemp())
        self.repo_root = self.test_dir

    def tearDown(self):
        # Remove temporary directory
        shutil.rmtree(self.test_dir)

    def test_install_fails_without_git(self):
        # Without .git dir, it should raise a SystemExit / typer.Exit / click.exceptions.Exit
        with self.assertRaises((SystemExit, click.exceptions.Exit)):
            install(path=self.repo_root)

    def test_install_creates_pre_commit_hook(self):
        # Create .git directory
        git_dir = self.repo_root / ".git"
        git_dir.mkdir()
        
        # Call install
        install(path=self.repo_root)
        
        pre_commit_path = git_dir / "hooks" / "pre-commit"
        self.assertTrue(pre_commit_path.is_file())
        
        content = pre_commit_path.read_text(encoding="utf-8")
        self.assertIn("contextmesh lint", content)
        
        # Check that it is executable
        self.assertTrue(os.access(pre_commit_path, os.X_OK))

    def test_init_ci_creates_workflow(self):
        # Call init_ci
        init_ci(path=self.repo_root)
        
        workflow_path = self.repo_root / ".github" / "workflows" / "contextmesh-pr.yml"
        self.assertTrue(workflow_path.is_file())
        
        content = workflow_path.read_text(encoding="utf-8")
        self.assertIn("ContextMesh PR Validation", content)
        self.assertIn("contextmesh validate --ci --changed-only", content)

    def test_init_ci_does_not_overwrite_existing(self):
        workflows_dir = self.repo_root / ".github" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        workflow_path = workflows_dir / "contextmesh-pr.yml"
        
        # Write pre-existing workflow
        original_content = "existing workflow content"
        workflow_path.write_text(original_content, encoding="utf-8")
        
        # Call init_ci
        init_ci(path=self.repo_root)
        
        # Check that original content was not modified
        self.assertEqual(workflow_path.read_text(encoding="utf-8"), original_content)

    def test_local_scaffold_creates_context_files(self):
        from contextsync.cli.app import scaffold
        
        # Write a config file
        config_path = self.repo_root / ".contextmesh.yaml"
        config_path.write_text(
            "tree:\n"
            "  filename: CONTEXT.md\n"
            "  min_files_for_context: 1\n"
            "llm:\n"
            "  provider: local\n"
            "  model: custom\n",
            encoding="utf-8"
        )
        
        # Create a directory with files
        src_dir = self.repo_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "app.py").write_text(
            "class Customer:\n"
            "    pass\n\n"
            "def calculate_total():\n"
            "    pass\n",
            encoding="utf-8"
        )
        
        # Run scaffold with local_only=True
        scaffold(path=self.repo_root, force=True, depth="basic", local_only=True)
        
        # Check that CONTEXT.md was created in src
        context_path = src_dir / "CONTEXT.md"
        self.assertTrue(context_path.is_file())
        
        # Verify content has deterministic structures
        content = context_path.read_text(encoding="utf-8")
        self.assertIn("Customer", content)
        self.assertIn("calculate_total", content)
        self.assertIn("Guided Rules & Tribal Knowledge", content)
