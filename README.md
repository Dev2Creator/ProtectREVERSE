# ProtectREVERSE

*Understand. Investigate. Verify. Build.*

Evidence-first software intelligence for projects you are authorised to inspect. Static analysis, architecture mapping and defensive security review, running locally with no execution of the code it examines.

**Status: v0.1.1 — Milestone 0 and 1 complete (43 tests passing). Everything else is planned, not built.** The honest inventory lives in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md); read that before assuming a feature exists.

## What works today

- Ingest a local directory, a ZIP (traversal-safe) or an authorised HTTPS git repository.
- Inventory: files, languages, lines of code, size, with walk limits.
- Dependency manifests: requirements.txt, package.json, pyproject.toml, go.mod, pom.xml, plus lockfile detection.
- Module graph from Python AST and JS/TS imports, including nested packages, relative imports and circular chains.
- Route extraction for Flask, FastAPI, Django and Express, with file and line.
- Quality signals: tests, CI, documentation, TODO density, oversized modules, committed `.env`.
- Technology fingerprints with evidence-based confidence.
- Every finding carries an ID, source, locator, timestamp, status, confidence and limitations.
- Three explanation registers: simple, developer, architect.
- Implementation planner with dependencies and acceptance criteria.
- AGENT.md generator in four modes, keeping facts, inferences and proposals apart.
- Reports as Markdown, JSON and a self-contained HTML page with filters.
- Local report server on 127.0.0.1.

## What does not exist yet

Website and domain analyzers, API specification review, dependency vulnerability data, the interactive workbench, a FastAPI service, a database and job queue. No vulnerability claims are made anywhere in this version.

## Quick start

```bash
python3 -m pytest                      # 43 tests
cd backend
python3 -m protectreverse scan ../tests/fixtures/python_app --out ../.reports --plan --agentmd understand
python3 -m protectreverse serve --port 8000
```

## Safety rules the code enforces

Remote URLs are limited to http/https; private, loopback, link-local and cloud-metadata addresses are refused, and redirects are re-validated hop by hop. Archives cannot escape their destination. Imported project code is never executed. Secret-shaped values are redacted before they reach any report; only their kind and location are recorded.

## Limitations

Static analysis is not proof of runtime behaviour. A declared dependency is not a used dependency. A filename heuristic is not a fact about execution. Every report restates this, per finding, in its limitations field.

## Licence

Custom proprietary, source-available EULA: see [LICENSE-EULA.md](LICENSE-EULA.md). Reading, studying and authorised testing are permitted; redistribution and commercial use require written permission. Provided AS IS, with no warranty.

## Author

Aneek Mukherjee (Dev2Creator).
