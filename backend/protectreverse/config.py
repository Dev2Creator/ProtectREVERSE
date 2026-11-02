"""Hard limits and configuration.

Every limit here exists to keep an investigation bounded and to avoid turning
a read-only analysis into a resource problem.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    max_files: int = 20_000
    max_total_bytes: int = 120 * 1024 * 1024
    max_file_bytes: int = 2 * 1024 * 1024
    max_depth: int = 24
    max_zip_members: int = 20_000
    max_zip_bytes: int = 200 * 1024 * 1024
    max_zip_ratio: float = 200.0
    max_text_bytes_scanned: int = 512 * 1024
    http_timeout: float = 10.0
    http_max_bytes: int = 3 * 1024 * 1024
    max_network_pages: int = 20


LIMITS = Limits()

# Extensions we treat as text for scanning. Binary formats are inventoried but
# never parsed.
TEXT_EXTENSIONS = {
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".go", ".rs",
    ".java", ".kt", ".rb", ".php", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs",
    ".swift", ".scala", ".sh", ".bash", ".zsh", ".ps1", ".sql", ".html", ".htm",
    ".css", ".scss", ".sass", ".vue", ".svelte", ".jinja", ".j2", ".md", ".txt",
    ".rst", ".json", ".jsonl", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf",
    ".env", ".xml", ".gradle", ".properties", ".lock", ".csv", ".tf", ".dockerfile",
}

MANIFEST_NAMES = {
    "requirements.txt", "requirements-dev.txt", "pyproject.toml", "setup.py",
    "setup.cfg", "Pipfile", "poetry.lock", "package.json", "package-lock.json",
    "yarn.lock", "pnpm-lock.yaml", "go.mod", "go.sum", "Cargo.toml",
    "Cargo.lock", "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile",
    "Gemfile.lock", "composer.json", "composer.lock", "mix.exs", "deno.json",
}

WORKSPACE_DIR = os.path.join(os.path.expanduser("~"), ".protectreverse", "workspaces")
REPORT_DIR = os.path.join(os.path.expanduser("~"), ".protectreverse", "reports")
