# Implementation Plan — ProtectREVERSE

**Version:** 0.1.1 (plan revision after Phase 1 stabilisation)
**Status:** Milestone 0 and Milestone 1 complete and tested. Everything below M1 is planned, not built.
**Rule of this document:** a milestone is "done" only when its tests run green and its docs are updated. No milestone is claimed done because code exists.

---

## 1. Where the project actually stands

### Built and tested (43 passing tests)

| Area | What exists | Tests |
|---|---|---|
| Intake | local directory, ZIP (traversal-safe extraction), authorised HTTPS git clone | security suite |
| Inventory | file walk with limits, language mix, LOC, size | unit |
| Manifests | requirements.txt, package.json, pyproject.toml, go.mod, pom.xml, lockfile detection | unit |
| Import graph | Python AST edges, JS/TS regex edges, local-module resolver (absolute, nested, relative, circular), fan-in hubs | 10 resolver regressions |
| Routes | Flask / FastAPI / Django / Express declarations with file + line | unit |
| Quality | tests, CI, documentation, TODO markers, large modules, committed `.env` | unit |
| Technology | fingerprints with evidence-based confidence | unit |
| Evidence | five statuses, three confidence levels, locators, per-finding limitations | integration |
| Explain | simple / developer / architect registers, evidence-linked | integration |
| Planner | task graph from findings, dependencies, acceptance criteria | integration |
| AGENT.md | four modes with fact / inference / proposal / open-question registers | integration |
| Reports | Markdown, JSON, self-contained HTML (filters + tabs), redaction verified across all three | integration + security |
| CLI | `scan`, `list`, `show`, `explain`, `plan`, `agentmd`, `delete`, `serve` | integration |
| Local server | stdlib HTTP report viewer on 127.0.0.1 | manual |

### Known gaps, stated plainly
- Website, domain, DNS and TLS analyzers: **not built**.
- API specification (OpenAPI) analyzer: **not built**.
- Dependency vulnerability intelligence: **not built**. No advisory data is bundled or fetched.
- Interactive frontend workbench: **not built**. Only the generated HTML report exists.
- FastAPI backend + database + job queue: **not built**. Current design is a stdlib CLI and a file-based workspace.
- LICENSE-EULA.md: **not written yet**.
- No Git repository has been created or published. Local workspace only.

---

## 2. Architecture principles (do not change without approval)

1. **Evidence first.** Every finding carries an ID, a claim, a source, a locator, a collection time, a status, a confidence and its limitations.
2. **No execution.** Imported project code is never run. Analysis is static and text-level only.
3. **Local first.** The tool works offline against local material. Remote analysis requires an explicit URL and stays passive.
4. **Redaction by default.** Secret-shaped values never reach a report; only their kind and location do.
5. **Honest labels.** OBSERVED means present in material; INFERRED means supported but unproven; UNKNOWN means evidence is insufficient. Confidence is never presented as truth.
6. **Small verified milestones.** Each change is inspected, implemented, tested, documented and reported.

---

## 3. Milestones

### M0 — Foundations ✅ complete
Repository skeleton, evidence model, security layer, CLI, report export, test harness.
**Acceptance:** done — 43 tests green, redaction verified across md/json/html.

### M1 — Local project intelligence ✅ complete
Inventory, manifests, import graph, routes, quality, technology, planner, AGENT.md, explain.
**Acceptance:** done — fixture pipeline produces labelled findings; empty folders omitted from features.

### M2 — Static security analysis (Phase 2A) — next
**Scope:** Python AST rules for dangerous patterns, insecure configuration, auth/authz review, input validation and output encoding review, hardcoded secrets with safe redaction.
**Deliverables:** `analyzers/security.py`, rule registry with IDs and CWE references, per-finding remediation text in three registers, `security` report section.
**Rules (first batch, all static):** `eval`/`exec`, `subprocess` with `shell=True`, `pickle.loads` on untrusted input, `yaml.load` without SafeLoader, disabled TLS verification, `debug=True` in a deployment path, wildcard CORS with credentials, missing auth decorator on a route that mutates state, string-built SQL, `os.system`, `assert` used for access control, `tempfile.mktemp`.
**Tests:** one positive and one negative fixture per rule; false-positive guard for framework wrappers; redaction regression; every finding has file + line + evidence.
**Acceptance:** all rule tests green, no rule fires on the fixture app except where the fixture is deliberately vulnerable.
**Risk:** heuristic rules over-report. Mitigation: each rule requires an AST pattern, not a substring match, and carries its own limitation text.

### M3 — Dependency intelligence (Phase 2B) — needs an advisory source decision
**Scope:** parse manifests and lockfiles, map declared vs locked versions, compare against advisory data, separate confirmed matches from unverified version ranges, produce safe upgrade guidance.
**Open decision for the owner:** advisory source. Options: (a) offline snapshot of a public dataset, refreshed manually; (b) OSV API lookups, opt-in per scan; (c) no network, report only "outdated by version" without CVE claims.
**Default recommendation:** (a) plus (c) labels, so the tool never claims a vulnerability it has not checked.
**Acceptance:** every vulnerability claim names its advisory source and its match basis; unmatched versions are labelled UNKNOWN, never "safe".
**Risk:** stale data presented as current. Mitigation: snapshot date printed in every report.

### M4 — Website and domain posture (Phase 2C) — gated on explicit authorisation
**Scope:** TLS certificate metadata and expiry, HTTP security headers, cookie attributes, redirect chain, public DNS (SPF/DMARC/CAA), robots and sitemap references.
**Hard constraints:** http/https only; private, loopback, link-local and metadata addresses blocked; DNS re-resolved and redirects re-validated at every hop; no crawling beyond the given host; no authentication bypass; no intrusive requests.
**Acceptance:** SSRF and redirect-to-private tests green; header checks match a recorded fixture; every observation timestamped.
**Risk:** SSRF. Mitigation: shared `validate_url` on every hop plus a test that proves a redirect into RFC1918 is refused.

### M5 — API security review (Phase 2D)
**Scope:** OpenAPI/Swagger parsing without executing the spec; missing auth documentation; sensitive response fields; schema validation gaps; rate-limit documentation; inconsistent security definitions.
**Acceptance:** the review distinguishes "no security scheme declared" from "authentication absent at runtime" and says so in the report.
**Risk:** spec ≠ reality. Mitigation: every API finding is INFERRED at best.

### M6 — Attack-surface graph and workbench UI (Phase 2E + Phase 3)
**Scope:** module/route/dependency graph with entry points and trust boundaries, data-flow sketch with inferred edges marked; local web workbench (project overview, file explorer, graph, routes, dependencies, findings, evidence viewer, planner, AGENT.md, export centre).
**Design:** HTML + CSS + vanilla JS modules, no framework, no build step; Python serves JSON over localhost.
**Acceptance:** every control performs a real action; keyboard navigation and focus states; no invented numbers on any screen.
**Risk:** UI claiming more than the analyzers know. Mitigation: status chips rendered from the data, never assumed.

### M7 — Security learning lab (Phase 2F)
**Scope:** synthetic vulnerable projects shipped in-repo, one lesson per vulnerability class, remediation exercises, before/after diffs, automatic self-check.
**Acceptance:** every exercise is self-contained and offline; no real third-party target is referenced.

### M8 — Unified intelligence report + release (Phase 2G + Phase 5)
**Scope:** merged report (architecture, stack, dependency health, quality, security posture, evidence, limitations, fixes, prioritised plan), export centre (md/html/json/zip), accessibility pass, LICENSE-EULA.md, third-party notices, release verification.
**Acceptance:** one command produces the full bundle from a fixture; every finding in it has source, locator, status, confidence and limitation.

---

## 4. Explicit non-goals

No exploitation, no authentication or access-control bypass, no credential attacks, no intrusive scanning, no brute force, no session or token extraction, no persistence or evasion, no malware, no private-person dossiers, no people search, no facial recognition, no location tracking. Remote analysis is passive and requires an authorised target.

---

## 5. Approval gates

- **Now:** awaiting approval for M2. Nothing beyond M1 will be built until agreed.
- **M3:** owner must choose the advisory source before any vulnerability claim is possible.
- **M4:** remote-target analysis stays disabled until the SSRF test suite is green.
- **Publishing:** no GitHub repository is created or pushed without explicit approval.

---

## 6. Testing strategy

1. Unit tests per analyzer, one positive and one negative fixture each.
2. Security tests for URL validation, ZIP safety, redaction and no-execution guarantees.
3. Integration test that runs the whole pipeline on the fixture and asserts every finding is labelled.
4. Regression tests for every fixed bug (the resolver bug has ten).
5. Export tests that grep Markdown, JSON and HTML for raw secret values.
6. Manual browser check of the generated report before any release claim.
