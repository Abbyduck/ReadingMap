"""Regression checks for release exclusion and redacted index inspection."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import check_release as guard


class ReleaseGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="reading-map-guard-test-")
        self.root = Path(self.directory.name)
        self.root_patch = patch.object(guard, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.root_patch.stop)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def run_check(self, **kwargs):
        output = StringIO()
        with redirect_stdout(output):
            status = guard.check_release(**kwargs)
        return status, output.getvalue()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def test_ignore_rules_apply_without_initializing_project(self):
        self.write(".gitignore", "backend/.env\n/implementation-*.png\n")
        self.write("backend/.env", "DATABASE_PASSWORD=local-private-value")
        self.write("implementation-check.png", "screenshot")
        self.write("README.md", "Public source")
        status, output = self.run_check(list_files=True)
        self.assertEqual(status, 0)
        self.assertNotIn("backend/.env", output)
        self.assertNotIn("implementation-check.png", output)
        self.assertFalse((self.root / ".git").exists())

    def test_provider_token_is_blocked_without_echoing_value(self):
        token = "sk-proj-" + "X" * 40
        self.write("leaked.txt", token)
        status, output = self.run_check()
        self.assertEqual(status, 1)
        self.assertIn("provider token", output)
        self.assertNotIn(token, output)

    def test_staged_blob_is_checked_when_working_copy_is_clean(self):
        self.git("init", "--quiet")
        token = "ghp_" + "X" * 40
        self.write("config.txt", token)
        self.git("add", "config.txt")
        self.write("config.txt", "Clean working copy")
        status, output = self.run_check(staged_only=True)
        self.assertEqual(status, 1)
        self.assertIn("[index]", output)
        self.assertNotIn(token, output)

    def test_force_added_private_file_is_blocked(self):
        self.git("init", "--quiet")
        self.write(".gitignore", "backend/.env\n")
        self.write("backend/.env", "DJANGO_DEBUG=true")
        self.git("add", "-f", "backend/.env")
        status, output = self.run_check(staged_only=True)
        self.assertEqual(status, 1)
        self.assertIn("private/local file", output)

    def test_local_secret_reuse_is_blocked(self):
        self.write(".gitignore", "backend/.env\n")
        secret = "locally-generated-" + "X" * 32
        self.write("backend/.env", "DJANGO_SECRET_KEY=" + secret)
        self.write("notes.md", secret)
        status, output = self.run_check()
        self.assertEqual(status, 1)
        self.assertIn("matches a local credential", output)
        self.assertNotIn(secret, output)

    def test_utf16_token_is_blocked(self):
        token = "github_pat_" + "X" * 40
        issues = guard.inspect_blob("encoded.txt", token.encode("utf-16"), "test", [])
        self.assertTrue(issues)
        self.assertNotIn(token, "\n".join(issues))


if __name__ == "__main__":
    unittest.main()
