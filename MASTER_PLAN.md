# ProtectREVERSE — Revised Product Vision, Architecture and Roadmap

**Version:** 2.0 (supersedes IMPLEMENTATION_PLAN.md v0.1.1)
**Date:** 2 November 2026
**Status of this document:** planning artefact. It states what exists, what must change, and in what order. It does not claim any unbuilt capability works.

---

## 0. What the earlier plan got wrong

The v0.1.1 plan treated ProtectREVERSE as a defensive static analyser with a report viewer. That is roughly 15% of the intended product. The corrected vision adds four capabilities that the current codebase has no representation of at all:

1. **Multi-surface investigation** — websites, APIs and documentation, not only local source trees.
2. **Reverse engineering as a first-class output** — reconstruction of structure, flows and boundaries, not just findings.
3. **Blueprint compilation** — turning an investigation into a buildable specification for a different project.
4. **A persistent, stateful workspace** — the current design has no database and no application shell.

The existing evidence discipline, security guards and 43 passing tests are the part worth keeping. The rest gets rebuilt around them.

---

## 1. Current repository vs. intended product

Measured state: 2,859 lines of backend code across 20 modules, 410 lines of tests, 8 analyzers, 4 AGENT.md modes, no database, no web application, no network-facing analyzers.

| Capability the vision requires | Current state | Verdict | Work implied |
|---|---|---|---|
| Local directory / ZIP intake | Working, traversal-safe | **Preserve** | none |
| Authorised git clone | Working, HTTPS only | **Extend** | GitHub REST metadata, branch selection, depth limits |
| Website investigation | Absent | **Add** | new `collect/web/` package |
| Screenshot / document intake | Absent | **Add** | image + PDF text extraction, OCR optional |
| API / OpenAPI / Postman investigation | Absent | **Add** | `collect/api/` |
| OSINT (public product, org, domain, advisory) | Absent | **Add** | `collect/osint/`, stub sources first |
| Inventory, manifests, import graph, routes, quality, tech | Working | **Preserve + extend** | route coverage, more languages |
| Dependency vulnerability intelligence | Absent | **Add** | `analyzers/dependencies/` + advisory store |
| Static security rules | Absent | **Add** | `analyzers/security_rules/` |
| TLS, headers, cookies, DNS posture | Absent | **Add** | `collect/web/posture.py`, gated by authorisation |
| Reverse engineering engine | Absent | **Add** | `reverse/` — the largest new module |
| Feature and flow inference | Absent | **Add** | `reverse/features.py`, `reverse/flows.py` |
| Blueprint generator | Absent | **Add** | `blueprint/` compiler + templates |
| AGENT.md generator | 175 lines, 4 generic modes, no customisation | **Rebuild** | 35 sections, 8 modes, override system, doc set |
| Planner | Findings-to-tasks only | **Rebuild** | becomes `blueprint/roadmap.py` with milestones and estimates |
| Explanation engine | 3 registers, evidence-linked | **Extend** | contradiction-aware, audience routing per section |
| Evidence model | 5 statuses, 3 confidence levels, locators | **Extend** | add CONTRADICTED, next-step, source provenance, graph edges |
| Report export (md/json/html) | Working, redaction verified | **Preserve** | add doc-set bundle |
| Workspace UI | One static HTML report | **Rebuild** | FastAPI + SQLite + ES-module frontend, 17 screens |
| Persistence | JSON files in a workspace folder | **Rebuild** | SQLite with migration path |
| CLI | Working, 8 commands | **Preserve + extend** | new commands map to new stages |
| Security guards (SSRF, traversal, redaction, no execution) | Working, tested | **Preserve, extend to every new collector** | shared enforcement point |

### Things that must not be lost

The 43 tests, the five-status evidence discipline, per-finding limitations, redaction verified across every export format, URL validation with per-hop re-check, traversal-safe extraction, and the rule that no imported code is ever executed. Every new collector inherits these or it does not ship.

---

## 2. Revised architecture

Eight stages, one direction, no stage allowed to invent what the previous stage did not supply.

```
INPUT            intake/           authorisation, scope, target descriptor
COLLECT          collect/          web · repo · local · api · docs · osint
NORMALISE        normalize/        artifacts, text, structure, hashes, provenance
STORE            store/            SQLite: investigations, artifacts, evidence, findings, graphs
ANALYSE          analyzers/        inventory, manifests, imports, routes, quality, tech, security, dependencies
REVERSE          reverse/          architecture, components, flows, features, contradictions
SYNTHESISE       blueprint/        product spec, features, architecture, db/api design, roadmap
GENERATE         generate/         AGENT.md, doc set, reports, exports
PRESENT          app/              FastAPI JSON API + ES-module workspace
```

### Package tree

```
backend/protectreverse/
  contract/        scope.py authorisation.py budget.py        # what we are allowed to touch
  intake/          local.py archive.py git.py url.py file_upload.py
  collect/         base.py
    web/           fetch.py robots.py sitemap.py html_tree.py assets.py meta.py
                   posture.py (tls, headers, cookies, dns)
    repo/          github.py tree.py history.py ci.py
    api/           openapi.py postman.py schema.py
    osint/         product.py organisation.py domain.py advisories.py
  normalize/       artifacts.py text.py structure.py hashing.py provenance.py
  store/           schema.sql db.py repositories.py migrations/
  analyzers/       base.py inventory.py manifests.py imports.py routes.py quality.py tech.py
    security/      rules_python.py rules_js.py rules_config.py registry.py cwe.py
    dependencies/  graph.py advisory_store.py match.py
  reverse/         graph.py architecture.py components.py flows.py features.py
                   trust_boundaries.py contradictions.py
  blueprint/       compiler.py product.py features.py architecture.py data_model.py
                   api_design.py ux.py roadmap.py risks.py
  generate/        agentmd.py modes.py overrides.py sections.py docs.py bundle.py
  explain/         engine.py registers.py citations.py
  evidence/        models.py status.py confidence.py locator.py
  reporting/       markdown.py json_export.py html.py
  app/             main.py routes_*.py jobs.py auth_local.py
  frontend/        index.html styles/ js/ (ES modules, no build step)
```

### Evidence model v2

Every finding gains: `provenance` (collector, method, request or file, timestamp), `edges` (relates-to, contradicts, supports, located-in), `next_step`, and the `CONTRADICTED` status. Blueprints and AGENT.md sections carry a `provenance` tag of either `evidence`, `proposal` or `assumption`, and the generator refuses to render a proposal inside an evidence section.

### Persistence

SQLite, single file per workspace, WAL mode. Tables: `investigation`, `scope`, `artifact`, `artifact_blob`, `evidence`, `finding`, `finding_edge`, `graph_node`, `graph_edge`, `blueprint`, `blueprint_section`, `generated_document`, `job`. Migrations as ordered SQL files, no ORM. JSON workspace export remains available so existing CLI workflows keep working.

---

## 3. Investigation pipelines

**Website (passive by default).** Authorisation recorded → URL validated and re-validated per hop → single-page fetch with a request budget → HTML tree, metadata, assets, links, forms, robots, sitemap → visible layout and component inventory from markup, not screenshots → technology fingerprints with confidence → route list from anchors and declared navigation → observed functionality → architecture hypotheses, each labelled INFERRED or UNKNOWN. No crawling beyond the declared host unless the scope says otherwise. No authentication bypass, no form submission, no intrusive requests until the M-security gate is satisfied.

**Repository.** Existing clone plus: GitHub metadata via API (stars, releases, licence, last commit, open issues as counts, not opinions), branch listing, directory tree, CI configuration, build scripts, deployment descriptors, test layout, history sampling for change hotspots.

**Local project.** Current behaviour plus: database configuration detection, container and deployment files, environment templates, frontend/backend relationship mapping, monorepo detection.

**API and documentation.** OpenAPI 2/3 and Swagger parsed without executing; Postman collections parsed; endpoint inventory; auth scheme documentation gaps; request/response shape summary; SDK and integration hints. Every claim stays INFERRED because a spec is a description, not runtime truth.

**OSINT, tightly scoped.** Public products, public repositories, organisations, domains, public documentation, published advisories, release history, public infrastructure metadata such as nameservers and certificate issuer. Refused permanently: private individuals, contact discovery, social profiling, location, facial recognition, credential material. A request that needs those is declined with a reason, not silently ignored.

---

## 4. Reverse engineering engine

The heart of the product, and the module with the least code today.

- **Graph builder** — unify module, route, component, dependency and navigation evidence into one typed graph with provenance on every edge.
- **Architecture recogniser** — layer detection, pattern candidates (MVC, layered, hexagonal, microservice, monolith, JAMstack, SSR), each emitted as a hypothesis with the evidence that supports it and the evidence that would falsify it.
- **Component and feature inventory** — what exists, where it lives, what it appears to do, with locator and confidence. On websites, components come from repeated markup structures and shared partials; on source, from modules and classes.
- **Flow reconstruction** — entry points to side effects, request-through-handler-to-storage, page-to-page journeys. Each hop either has evidence or is marked inferred or unknown.
- **Trust boundaries** — where untrusted input crosses into privileged code, drawn only where evidence exists.
- **Contradiction detector** — a declared dependency never imported, a route with no handler, a README claiming a feature with no supporting code, a spec endpoint with no implementation. Emits `CONTRADICTED` with both sides of the conflict.

Output is an `ArchitectureReport` bound to the graph, rendered in three registers, exportable as ARCHITECTURE.md.

---

## 5. Blueprint compiler

Input: an `Investigation` plus a `ProjectIntent` (what the user wants to build). Output: a coherent specification, not a filled-in template.

Pipeline: intent resolution → capability selection (which observed features to carry, adapt or drop) → stack resolution (respect user overrides, never silently copy the source stack) → data model derivation → API surface derivation → UX inventory → roadmap synthesis with dependency ordering → risk register → consistency pass that checks every generated requirement maps to a feature, a milestone and an acceptance test.

Every artefact is tagged evidence, proposal or assumption. Where the source project had no observable backing for a proposed feature (for example a payments flow inferred from a pricing page), the blueprint records that gap instead of hiding it.

The generated document set: AGENT.md, IMPLEMENTATION_PLAN.md, PROJECT_SPECIFICATION.md, ARCHITECTURE.md, API_SPECIFICATION.md, SECURITY_REQUIREMENTS.md, TASKS.md, and DATABASE.md where a data model exists. Documents that do not apply are not generated; the compiler records why each was skipped.

---

## 6. AGENT.md generator v2

The current generator writes four fixed sections with no user input. v2 keeps the register discipline and adds the rest.

**Modes (8):** reconstruct, inspired-build, modernize, extend, migrate, build-from-scratch, security-improvement, documentation. Each mode changes section emphasis, the non-goals list and the definition of done, not just a label.

**Customisation overrides:** project name, language, frontend framework, backend, database, hosting, UI preferences, performance targets, target platform, include/exclude features, complexity tier, priorities. Overrides are recorded in the document so a later reader knows which choices were the user's.

**Sections (35):** identity, overview, problem, functional requirements, feature inventory, stack, architecture, directory structure, frontend, backend, database, API, UI/UX, components, user flows, security, privacy, coding conventions, naming, dependency rules, performance, accessibility, error handling, testing architecture, test cases, milestones, task dependencies, implementation sequence, deployment, environment configuration, documentation requirements, known limitations, unresolved questions, non-goals, definition of done.

**Validation before write:** no empty required section, every feature appears in at least one milestone, every milestone has acceptance criteria, every removed feature is listed with a reason, and no evidence section contains a proposal. The validator fails the build rather than emitting a hollow document.

---

## 7. Workspace application

FastAPI service over SQLite, frontend as plain ES modules with no build step. Local by default: binds 127.0.0.1, no telemetry, no cloud dependency for core paths.

Screens mapped to modules:

1. Overview → investigation summary, coverage, open questions
2. Investigation Sources → collectors used, scope, budgets consumed
3. Project Inventory → artifacts and files
4. Reverse Engineering → architecture report and hypotheses
5. Architecture Explorer → graph viewer
6. Feature Explorer → feature inventory with locators
7. Technology Stack → fingerprints and confidence
8. Dependencies → graph, advisories, upgrade path
9. API Explorer → endpoints and schemas
10. OSINT Findings → public-source results, clearly separated
11. Security Intelligence → findings, threat model, remediation
12. Evidence Viewer → every finding with locator and provenance
13. Implementation Blueprint → compiled specification
14. Custom Project Configuration → overrides
15. AGENT.md Generator → mode, overrides, preview, validation report
16. Export Centre → document set, bundles
17. Jobs → long-running collection and analysis

Design constraints: no fabricated numbers, honest empty states, no decorative charts, keyboard-reachable controls, dark and light themes, no framework lock-in.

---

## 8. Roadmap

Sequenced so that each milestone produces something verifiable and nothing downstream is built on a guess.

### R0 — Foundations ✅ complete
Evidence model v1, security guards, CLI, exports, 43 tests.

### R1 — Local project intelligence ✅ complete
Inventory, manifests, import graph with resolver, routes, quality, tech, planner, explain, reports.

### R2 — Contract, normalisation and store (foundation for everything else)
Scope and authorisation records, request budgets, artifact normalisation with provenance and hashes, SQLite schema and repositories, migration path from the JSON workspace.
**Acceptance:** an existing local investigation persists and reloads byte-identically; a request without a recorded authorisation is refused by the collector base class.

### R3 — Evidence model v2
CONTRADICTED status, next-step field, provenance and edges, blueprint provenance tags.
**Acceptance:** contradiction tests pair a claim with its counter-evidence; export redaction still passes on all formats.

### R4 — Repository and local intelligence
GitHub metadata, branch listing, CI and build detection, deployment descriptors, hotspot sampling, monorepo detection, database configuration detection.
**Acceptance:** a second fixture repository with CI and a build file yields verified findings; no network call without an authorised scope.

### R5 — Website investigation (passive)
Fetch pipeline, robots and sitemap, markup tree, layout and component inventory, navigation reconstruction, technology fingerprints, route discovery, functionality observation, architecture hypotheses.
**Acceptance:** against a local fixture site, component and navigation output matches the fixture; SSRF tests including redirect-into-private-range stay green; every hypothesis carries INFERRED or UNKNOWN.

### R6 — Website posture and API investigation
TLS and certificate metadata, security headers, cookie attributes, DNS records, redirect chain, OpenAPI and Postman parsing, endpoint and auth documentation gaps.
**Acceptance:** posture checks match recorded fixtures; specs are parsed without execution; findings remain INFERRED where runtime is unobserved.

### R7 — Reverse engineering engine
Graph builder, architecture recogniser, component and feature inventory, flow reconstruction, trust boundaries, contradiction detector, ARCHITECTURE.md.
**Acceptance:** on the two fixtures plus a web fixture, the engine names its pattern candidates with supporting and opposing evidence; every inferred edge is distinguishable from an observed one.

### R8 — Security intelligence
Python and JS rule registry with CWE references, configuration review, secret detection reusing the existing redactor, dependency graph and advisory matching with a dated offline store, threat model generation, remediation plans in three registers.
**Acceptance:** each rule has a positive and negative fixture; every vulnerability claim names its advisory source and match basis; unknown versions are UNKNOWN, never "safe".

### R9 — Blueprint compiler
Intent resolution, feature selection, stack resolution with overrides, data model and API derivation, UX inventory, roadmap with estimates and dependencies, risk register, consistency pass, document set.
**Acceptance:** a blueprint compiled from the fixture has no orphan requirement; every generated document validates against its section contract; skipped documents record a reason.

### R10 — AGENT.md v2 and explanation engine
Eight modes, 35 sections, override system, validator, multi-document bundle, three registers with citation links and contradiction awareness.
**Acceptance:** all eight modes produce valid documents; the validator rejects an intentionally hollow input; overrides appear verbatim in the output.

### R11 — Workspace application
FastAPI JSON API, SQLite repositories, job runner, 17 screens, graph viewer, evidence viewer, export centre.
**Acceptance:** every screen works with data from a real investigation; no placeholder panels; keyboard access verified; no fabricated values on any screen.

### R12 — Hardening and release
Accessibility pass, performance budgets, packaging, third-party notices, EULA alignment, release verification on all fixtures, documentation refresh.
**Acceptance:** full suite green, bundle reproducible, report bundle matches the documented structure.

---

## 9. Standing constraints

**Preserved invariants.** No execution of inspected code. Redaction before any output. URL validation on every hop, including redirects. Traversal-safe extraction. Evidence before claim. Confidence never presented as certainty. Local-first, no cloud dependency in core paths.

**Permanent non-goals.** Exploitation, authentication or access control bypass, credential theft, malware, persistence, evasion, intrusive or disruptive scanning, private-individual surveillance, doxxing, personal profiling, facial recognition, location tracking.

**Honesty rules for the product itself.** A screen exists only if it does data. A feature is complete only when its tests are green and its limitations are written. Anything not built is labelled not built, in the UI and in the docs.

---

## 10. Open decisions for the owner

1. **Advisory source for dependencies** — offline dated snapshot (recommended), opt-in OSV queries, or version-only reporting with no vulnerability claims.
2. **Headless browser** — static HTML/CSS parsing only (recommended for R5), or add an optional Playwright path for rendered-layout observation later.
3. **Model integration** — none in core paths (recommended), optional local model for prose synthesis with explicit consent.
4. **Build order** — the roadmap above is depth-first through the pipeline. If the workspace UI is wanted earlier for demonstration, R11 can move ahead of R8 and R9 at the cost of empty screens in the interim.
5. **Repository shape** — keep one public repo on `main` with milestone tags, or split `protectreverse-core` and `protectreverse-app`.

---

## 11. Immediate next step

R2 is the unglamorous milestone that everything else depends on: scope records, normalisation with provenance, and the store. Without it, every later module either duplicates bookkeeping or makes claims it cannot cite.

Recommended start: R2, then R4 to prove the store with real analysis, then R5.
