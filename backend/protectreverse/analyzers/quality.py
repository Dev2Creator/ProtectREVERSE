"""Quality, maintenance and secret-hygiene observations.

Everything here is a static observation. None of it proves runtime behaviour.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from ..config import TEXT_EXTENSIONS
from ..evidence import Confidence, Finding, Status
from ..security import find_secrets
from .base import AnalysisContext, Analyzer, evidence_for
from .inventory import count_lines

TEST_PATTERNS = ("test_", "_test.", ".test.", ".spec.", "_spec.")
CI_FILES = {".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml", ".travis.yml", "bitbucket-pipelines.yml"}
TODO = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")


class QualityAnalyzer(Analyzer):
    name = "quality"
    category = "quality"

    def analyze(self, ctx: AnalysisContext) -> List[Finding]:
        files: List[Path] = ctx.cache.get("files", [])
        findings: List[Finding] = []

        tests = [p for p in files if any(part in p.name for part in TEST_PATTERNS)
                 or any(part in {"tests", "test", "__tests__", "spec"} for part in p.parts)]
        source = [p for p in files if p.suffix in {".py", ".js", ".ts", ".go", ".rs", ".java", ".rb"}]

        if tests:
            findings.append(Finding(
                category="quality.tests",
                claim=f"{len(tests)} test-related file(s) found in a project with {len(source)} source file(s)",
                status=Status.OBSERVED,
                confidence=Confidence.HIGH,
                evidence=[evidence_for(tests[0], ctx.root)],
                details={"tests": [str(p.relative_to(ctx.root)) for p in tests[:40]]},
                limitations=["Test files do not prove the tests pass or cover the important paths"],
            ))
        elif source:
            findings.append(Finding(
                category="quality.tests",
                claim="No tests were detected next to the source code",
                status=Status.INFERRED,
                confidence=Confidence.MEDIUM,
                evidence=[evidence_for(ctx.root, ctx.root)],
                limitations=["Tests may live in a separate repository or use an unrecognised naming scheme"],
            ))

        ci = [p for p in files if p.name in CI_FILES or
              (".github" in p.parts and "workflows" in p.parts and p.suffix in {".yml", ".yaml"})]
        findings.append(Finding(
            category="quality.ci",
            claim=(f"CI configuration detected: {', '.join(str(p.relative_to(ctx.root)) for p in ci[:4])}"
                   if ci else "No continuous-integration configuration was found"),
            status=Status.OBSERVED if ci else Status.UNKNOWN,
            confidence=Confidence.HIGH if ci else Confidence.LOW,
            evidence=[evidence_for(ci[0], ctx.root)] if ci else [evidence_for(ctx.root, ctx.root)],
            details={"ci_files": [str(p.relative_to(ctx.root)) for p in ci]},
        ))

        readme = [p for p in files if p.name.lower().startswith("readme")]
        docs = [p for p in files if p.suffix.lower() in {".md", ".rst", ".txt"}]
        claim = (
            f"{len(docs)} documentation file(s); README present ({readme[0].name})"
            if readme else f"{len(docs)} documentation file(s); no README detected"
        )
        findings.append(Finding(
            category="quality.documentation",
            claim=claim,
            status=Status.OBSERVED,
            confidence=Confidence.HIGH,
            evidence=[evidence_for(readme[0] if readme else ctx.root, ctx.root)],
            details={"docs_files": [str(p.relative_to(ctx.root)) for p in docs[:60]]},
            limitations=["Counting documents says nothing about their accuracy or freshness"],
        ))

        big = []
        todos = 0
        secrets: Dict[str, List[str]] = {}
        for path in files:
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            try:
                text = path.read_text(errors="replace")
            except OSError:
                continue
            lines = count_lines(path)
            if lines > 800:
                big.append((lines, path))
            todos += len(TODO.findall(text))
            for kind in find_secrets(text):
                secrets.setdefault(kind, []).append(str(path.relative_to(ctx.root)))

        if big:
            big.sort(reverse=True)
            findings.append(Finding(
                category="quality.module_size",
                claim="Large modules that may be hard to review: " +
                      ", ".join(f"{p.name} ({n} lines)" for n, p in big[:4]),
                status=Status.OBSERVED,
                confidence=Confidence.MEDIUM,
                evidence=[evidence_for(big[0][1], ctx.root)],
                details={"large_modules": [{"file": str(p.relative_to(ctx.root)), "lines": n} for n, p in big[:10]]},
                limitations=["Long files are a review signal, not a defect"],
            ))

        if todos:
            findings.append(Finding(
                category="quality.todos",
                claim=f"{todos} TODO/FIXME-style marker(s) in source and docs",
                status=Status.OBSERVED,
                confidence=Confidence.MEDIUM,
                evidence=[evidence_for(ctx.root, ctx.root)],
                details={"count": todos},
            ))

        if secrets:
            kinds = ", ".join(f"{kind} in {len(paths)} file(s)" for kind, paths in sorted(secrets.items()))
            findings.append(Finding(
                category="security.secret_like_strings",
                claim=f"Secret-shaped strings detected and redacted — {kinds}",
                status=Status.INFERRED,
                confidence=Confidence.LOW,
                evidence=[evidence_for(ctx.root / secrets[k][0], ctx.root) for k in list(secrets)[:2]],
                details={"kinds": {k: len(v) for k, v in secrets.items()},
                         "files": {k: v[:5] for k, v in secrets.items()}},
                limitations=[
                    "Pattern matching cannot confirm a value is a live credential",
                    "Values are never stored, exported or logged; only the location and kind are recorded",
                ],
            ))
        return findings
