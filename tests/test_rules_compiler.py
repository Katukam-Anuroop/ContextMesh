import json
import shutil
import tempfile
from pathlib import Path
import unittest

from contextsync.cli.rules import detect_frameworks, TEMPLATES

class TestRulesCompiler(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory structure representing a project
        self.test_dir = Path(tempfile.mkdtemp())
        self.repo_root = self.test_dir

    def tearDown(self):
        # Remove temporary directory
        shutil.rmtree(self.test_dir)

    def test_detect_frameworks_empty(self):
        # An empty directory should detect nothing
        frameworks = detect_frameworks(self.repo_root)
        self.assertEqual(frameworks, [])

    def test_detect_frameworks_typescript_react_next(self):
        # Create package.json indicating Next.js + React + TS
        package_json = self.repo_root / "package.json"
        package_json.write_text(
            json.dumps({
                "dependencies": {
                    "next": "^14.0.0",
                    "react": "^18.2.0"
                },
                "devDependencies": {
                    "typescript": "^5.0.0"
                }
            }),
            encoding="utf-8"
        )
        
        frameworks = detect_frameworks(self.repo_root)
        self.assertIn("nextjs", frameworks)
        self.assertIn("react", frameworks)
        self.assertIn("typescript", frameworks)

    def test_detect_frameworks_fastapi(self):
        # Create a python file and pyproject.toml indicating FastAPI
        pyproject = self.repo_root / "pyproject.toml"
        pyproject.write_text(
            "[project]\n"
            "dependencies = [\n"
            "    \"fastapi>=0.100.0\"\n"
            "]\n",
            encoding="utf-8"
        )
        # Create at least one py file so python framework detection triggers
        py_file = self.repo_root / "app.py"
        py_file.write_text("print('hello')", encoding="utf-8")
        
        frameworks = detect_frameworks(self.repo_root)
        self.assertIn("python", frameworks)
        self.assertIn("fastapi", frameworks)
