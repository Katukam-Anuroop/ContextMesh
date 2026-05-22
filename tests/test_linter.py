import os
import shutil
import tempfile
from pathlib import Path
import unittest

from contextsync.core.linter import ContextLinter, extract_defined_entities, LintIssue
from contextsync.config import ContextSyncConfig

class TestLinter(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory structure representing a project
        self.test_dir = Path(tempfile.mkdtemp())
        self.repo_root = self.test_dir

        # Create basic directory structure
        self.src_dir = self.repo_root / "src"
        self.src_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a sample python file
        self.py_file = self.src_dir / "app.py"
        self.py_file.write_text(
            "class User:\n"
            "    pass\n\n"
            "async def get_user_id():\n"
            "    pass\n\n"
            "MAX_CONNECTIONS = 100\n",
            encoding="utf-8"
        )
        
        # Create .cursor/rules directory
        self.rules_dir = self.repo_root / ".cursor" / "rules"
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        
        # Mock configuration
        self.config = ContextSyncConfig()
        # Set a low threshold for min_files_for_context so dirs are eligible
        self.config.tree.min_files_for_context = 1

    def tearDown(self):
        # Remove temporary directory
        shutil.rmtree(self.test_dir)

    def test_extract_defined_entities(self):
        classes, functions, constants = extract_defined_entities(self.py_file)
        self.assertIn("User", classes)
        self.assertIn("get_user_id", functions)
        self.assertIn("MAX_CONNECTIONS", constants)

    def test_linter_finds_stale_references(self):
        # Create a rules file with a valid and an invalid reference
        rule_file = self.rules_dir / "user_rules.mdc"
        rule_file.write_text(
            "---\n"
            "description: User rules\n"
            "globs: **/*.py\n"
            "---\n"
            "This rule references `User` and `get_user_id` and also references a stale class `AdminUser`.\n"
            "It also has `invalid_func()` which does not exist.\n",
            encoding="utf-8"
        )
        
        linter = ContextLinter(self.repo_root, self.config)
        report = linter.run_scan()
        
        # We expect 2 stale warnings: AdminUser and invalid_func
        self.assertEqual(report.total_rules, 1)
        stale_messages = [issue.message for issue in report.issues if issue.issue_type == "stale_reference"]
        self.assertEqual(len(stale_messages), 2)
        self.assertTrue(any("AdminUser" in msg for msg in stale_messages))
        self.assertTrue(any("invalid_func" in msg for msg in stale_messages))

    def test_linter_ignores_keywords(self):
        # Create a rule file referencing python builtins, FastAPI constructs, etc.
        rule_file = self.rules_dir / "fastapi_rules.mdc"
        rule_file.write_text(
            "---\n"
            "description: FastAPI rules\n"
            "globs: **/*.py\n"
            "---\n"
            "Leverage `Depends` and `response_model` or define route using `async def` and `def`.\n"
            "Also we use `str` or `None` and `len()` or `print()`.\n",
            encoding="utf-8"
        )
        
        linter = ContextLinter(self.repo_root, self.config)
        report = linter.run_scan()
        
        # We expect NO stale warnings because these are all in ignore_words or fall-through
        stale_issues = [issue for issue in report.issues if issue.issue_type == "stale_reference"]
        self.assertEqual(len(stale_issues), 0)
