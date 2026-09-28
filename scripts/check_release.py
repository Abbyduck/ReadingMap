"""Check publishable files and staged blobs without printing credential values."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = "source_data/drafts/reading_lists/香蕉妈妈__065__2026年香蕉妈妈牛1-高章泛听泛读书单-小红书__incremental-v2.json"
PRIVATE_ROOTS = {"backups", "tmp", "booklist", "research_data", "somedata"}
PRIVATE_PARTS = {".venv", "node_modules", "__pycache__", ".local", ".runtime", "staticfiles"}
PATTERNS = [
    ("credential-bearing URL", re.compile(r"(?i)\b(?:mysql(?:\+\w+)?|postgres(?:ql)?|mongodb(?:\+srv)?|redis|https?)://[^\s:/\"']+:([^\s@\"']+)@")),
    ("provider token", re.compile(r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{20,})\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("literal secret", re.compile(r"""(?i)["']?\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|secret[_-]?key|django_secret_key|database_password|email_host_password)\b["']?\s*[:=]\s*["']([^"'\r\n]{8,})["']""")),
]
PLACEHOLDERS = {"test-only-not-for-running-the-server", "changeme", "change-me", "your-secret-key", "your-api-key"}


def git(args, *, cwd=None):
    result = subprocess.run(["git", *args], cwd=ROOT if cwd is None else cwd, capture_output=True, check=True)
    return result.stdout


@contextmanager
def publication_inventory():
    probe = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=ROOT, capture_output=True)
    if probe.returncode == 0:
        git_root = Path(probe.stdout.decode().strip()).resolve()
        if git_root != ROOT.resolve():
            raise RuntimeError("Project is inside a different Git repository; check that repository separately.")
        yield []
    else:
        # Apply Git's actual ignore rules without initializing or staging this project.
        with tempfile.TemporaryDirectory(prefix="reading-map-release-") as directory:
            git(["init", "--quiet", directory])
            yield [f"--git-dir={Path(directory) / '.git'}", f"--work-tree={ROOT}"]


def private_path(name):
    path = Path(name)
    parts = path.parts
    if not parts:
        return False
    env_example = path.name == ".env.example" or (path.name.startswith(".env.") and path.name.endswith(".example"))
    if path.name.startswith(".env") and not env_example:
        return True
    if parts[0] in PRIVATE_ROOTS or set(parts) & PRIVATE_PARTS:
        return True
    if parts[0] == "frontend" and len(parts) > 1 and parts[1] == "dist":
        return True
    if len(parts) == 1 and path.name.startswith("implementation-") and path.suffix == ".png":
        return True
    if parts[0] == "source_data" and name != SAMPLE and not name.startswith("source_data/schemas/"):
        return True
    return path.suffix.lower() in {".pem", ".key", ".p12", ".pfx", ".sqlite3", ".db", ".sql", ".log"}


def local_secret_patterns():
    # Compare local values to release contents; never display the values or file contents.
    values = set()
    env_path = ROOT / "backend" / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip("'\"")
            if re.search(r"(?i)password|secret|api.?key|token", key) and len(value) >= 6:
                values.add(value)
            if key.strip() == "DATABASE_URL":
                password = unquote(urlsplit(value).password or "")
                if len(password) >= 4:
                    values.add(password)
    credential_file = ROOT / "backend" / ".local" / "admin-credentials.txt"
    if credential_file.is_file():
        for line in credential_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("Password: "):
                values.add(line.removeprefix("Password: ").strip())
    return [re.compile(r"(?<![\w])" + re.escape(value) + r"(?![\w])") for value in values if value]


def inspect_blob(name, raw, label, local_patterns):
    issues = []
    # Token/private-key and local-value matching also inspect binary bytes and encoded text.
    binary_text = raw.decode("utf-8", errors="replace")
    texts = [binary_text]
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        texts.append(raw.decode("utf-16", errors="replace"))
    for content in texts:
        for kind, pattern in PATTERNS:
            for match in pattern.finditer(content):
                if kind == "literal secret" and match.group(1).lower() in PLACEHOLDERS:
                    continue
                line = content.count("\n", 0, match.start()) + 1
                issues.append(f"{name}:{line} [{label}]: {kind} (value redacted)")
        for pattern in local_patterns:
            match = pattern.search(content)
            if match:
                line = content.count("\n", 0, match.start()) + 1
                issues.append(f"{name}:{line} [{label}]: matches a local credential (value redacted)")
    return issues


def check_release(*, staged_only=False, list_files=False):
    issues = []
    local_patterns = local_secret_patterns()
    with publication_inventory() as prefix:
        tracked = set(git([*prefix, "ls-files", "--cached", "-z"]).decode("utf-8").split("\0")) - {""}
        if staged_only and prefix:
            raise RuntimeError("--staged requires an initialized project Git repository.")
        untracked = set() if staged_only else set(git([*prefix, "ls-files", "--others", "--exclude-standard", "-z"]).decode("utf-8").split("\0")) - {""}
        names = sorted(tracked | untracked)
        for name in names:
            if list_files:
                print(name)
            if private_path(name):
                issues.append(f"{name}: private/local file is eligible for publication")
            path = ROOT / name
            if path.is_symlink():
                issues.append(f"{name}: review symlink before publication")
                continue
            if not staged_only and path.is_file():
                if path.stat().st_size >= 100 * 1024 * 1024:
                    issues.append(f"{name}: file exceeds 100 MiB")
                issues.extend(inspect_blob(name, path.read_bytes(), "working tree", local_patterns))
            if name in tracked:
                issues.extend(inspect_blob(name, git([*prefix, "show", f":{name}"]), "index", local_patterns))
    for issue in sorted(set(issues)):
        print(issue)
    print(f"Checked {len(names)} publishable files; {len(set(issues))} blocking issue(s).")
    return 1 if issues else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="Inspect only files/blobs currently in the Git index.")
    parser.add_argument("--list", action="store_true", help="Also list eligible paths, never file contents.")
    args = parser.parse_args()
    try:
        return check_release(staged_only=args.staged, list_files=args.list)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError):
        # Exception messages can contain inputs; keep failures redacted and fail closed.
        print("Release check could not finish. Verify Git, file access and local configuration; publication is blocked.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
