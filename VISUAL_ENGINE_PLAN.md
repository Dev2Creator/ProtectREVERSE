# Visual, DOM, CSS and Asset Reverse Engineering Engine

**Module codename:** `visual`
**Plan version:** 0.1 (architecture + roadmap, awaiting implementation approval)
**Parent plan:** MASTER_PLAN.md §3–§10 (Milestones R5, R7, R11)
**Date:** 2 November 2026

---

## 1. Repository inspection (done before writing this plan)

Facts about the current state, measured not assumed:

- Backend: 2,859 lines, 20 modules, 8 analyzers. Packages: `analyzers/`, `reporting/`, plus single-file `intake`, `evidence`, `explain`, `planner`, `agentmd`, `security`, `server`, `workspace`, `cli`, `config`.
- **No browser capability exists.** No Playwright, Selenium, CDP client, no `getComputedStyle`, no CSS parsing, no DOM model. The only two files mentioning DOM/CSS are `agentmd.py` (prose templating) and `security.py` (URL validation), neither of which inspects a page.
- **No frontend exists.** Zero `.html`, `.css`, `.js` files in the package. The only HTML is a generated report string in `reporting/html.py`.
- **No dependencies at all** (`dependencies = []`). A browser engine introduces the project's first runtime dependency, so it must be optional and lazy-loaded.
- 43 tests green before this plan was written. They must stay green through every milestone below.

**Conclusion:** this module is a genuine greenfield addition, but it must sit on foundations that do not exist yet: the SQLite store (R2) and evidence model v2 (R3). Building the browser inspector before those means every snapshot would live in ad-hoc JSON and could not be cited, compared or versioned.

---

## 2. Design principle: evidence in, IR out, code last

The one architectural decision that makes the rest tractable: **never generate code from a page directly.** Every step produces a normalised intermediate representation, and code generation is a separate, pure function of that IR.

```
page  →  snapshot (raw)  →  evidence  →  Visual IR  →  { HTML, CSS, JS, React, Next, Vue }
                                            ↓
                                     design tokens, component specs,
                                     responsive rules, asset manifest
```

Consequences:

1. The comparison workspace (part E) compares IR against IR, not pixels against pixels alone.
2. AGENT.md and the blueprint consume the IR, not the page.
3. Codegen targets are pluggable; adding Svelte or Astro later touches one emitter, not the collector.
4. Everything is deterministic and testable offline against saved snapshots.

---

## 3. Module architecture

```
backend/protectreverse/visual/
  __init__.py
  capability.py        # is a browser available? version probe, graceful degradation
  authorisation.py     # ownership/authorisation record, scope, robots, rate budget
  session.py           # Playwright lifecycle, viewport matrix, request interception rules
  snapshot.py          # full capture orchestration -> VisualSnapshot
  dom/
    tree.py            # node tree, landmarks, visibility, bounding boxes
    selector.py        # stable selector synthesis (id > data-* > nth-of-type path)
    semantics.py       # roles, headings, forms, links, interactions present
  css/
    stylesheets.py     # inline <style>, <link>, @import chains, cross-origin handling
    rules.py           # parse, specificity, cascade resolution, shorthand expansion
    computed.py        # batched getComputedStyle over sampled nodes
    tokens.py          # colour, spacing, radius, shadow, type scale, z-index derivation
    fonts.py           # @font-face, families, fallback stacks, licensing flags
    motion.py          # animations, transitions, keyframes, reduced-motion behaviour
    responsive.py      # viewport sweep -> breakpoint detection -> rule synthesis
  layout/
    flex.py            # flex container/item inference (direction, wrap, gaps, grow)
    grid.py            # grid template reconstruction, spans, auto-flow
    spacing.py         # margin/padding rhythm, scale fitting
    boxes.py           # dimensions, overflow, containment
  assets/
    discover.py        # img/srcset/picture/svg/icon-font/video/background/favicon
    probe.py           # HEAD/GET metadata: size, MIME, last-modified (no downloads by default)
    images.py          # dimensions, format, transparent/vector detection
    licensing.py       # licence status: owned / licensed / unknown / restricted
    manifest.py        # AssetManifest with usage locations
  components/
    cluster.py         # repeated subtree detection, landmark regions, slot inference
    spec.py            # ComponentSpec: hierarchy, styles, states, props, slots
    states.py          # hover/focus/active/open/disabled capture (bounded set)
  compare/
    screenshots.py     # reference vs reconstruction, perceptual diff with tolerance
    elements.py        # node-level matching, missing/extra/dimension deltas
    typography.py      # family, size, weight, line-height, letter-spacing deltas
    spacing.py         # margin/padding/gap deltas
    responsive.py      # per-viewport deltas
  ir/
    model.py           # VisualIR, PageIR, NodeIR, StyleIR, TokenIR, AssetIR, InteractionIR
    validate.py        # IR invariants; refuses to emit incomplete pages
    provenance.py      # every node/property tagged observed | inferred | unknown
  codegen/
    base.py            # Emitter protocol; deterministic ordering
    html.py            # semantic HTML from NodeIR
    css.py             # tokens -> custom properties, layout -> flex/grid rules
    js.py              # vanilla interactions from InteractionIR
    react.py           # component tree -> functional components + CSS modules
    next.py            # React emitter + app/router layout + metadata
    vue.py             # SFC emitter
  export/
    spec.py            # DESIGN_SYSTEM.md, COMPONENTS.md, ASSETS.md
    bundle.py          # zip: spec + code + manifest + evidence citations
```

### Data model additions (SQLite, after R2)

`visual_snapshot` (url, viewport, timestamp, authorisation_id, browser_version), `dom_node` (snapshot_id, parent_id, selector, tag, role, box, visible), `computed_style` (node_id, property, value, source), `stylesheet_rule` (snapshot_id, origin, selector, declarations, specificity, media), `design_token` (investigation_id, kind, name, value, usage_count, confidence), `asset` (investigation_id, url, mime, bytes, width, height, licence_status, source_page), `asset_usage` (asset_id, node_id, property), `component_spec` (investigation_id, name, node_root, variants, states), `comparison_run` (reference_id, candidate_id, tolerance, result_json), `codegen_bundle` (investigation_id, target, ir_hash, files).

Every row carries `provenance` and `confidence`, consistent with the existing evidence discipline.

---

## 4. Pipelines mapped to the request

### A. Browser inspector
`session.py` opens one browser, iterates a viewport matrix (mobile 390×844, tablet 834×1112, desktop 1440×900, wide 1920×1080, all DPR 1 unless overridden). Per viewport: wait for network idle with a hard timeout, snapshot the accessibility and DOM trees, sample computed styles (all nodes up to a node budget, not a random subset), record visibility and boxes, then a second pass for states on a bounded set of interactive elements (first N per role). Navigation is recorded as discovered links and observed URLs only, never by submitting forms or logging in.

**Hard rule:** only same-origin public resources, `robots.txt` honoured, request rate capped, no auth bypass, no cookie manipulation. JavaScript is inspected only where it is publicly served; source maps only when referenced and public. The report never claims server-side source access.

### B. CSS intelligence
Stylesheet chain with `@import` resolution, rule extraction with specificity, cascade resolution to the computed value actually observed, variable and token derivation with usage counts, typography scale fitting, spacing rhythm fitting, motion inventory, and per-breakpoint rule synthesis from the viewport sweep. Output: `DESIGN_SYSTEM.md` plus a machine-readable `DesignTokens.json`.

### C. Asset intelligence
Discovery across `img`, `srcset`, `picture`, inline SVG, SVG files, icon fonts, `@font-face`, video, poster frames, CSS `background-image`, favicons, and manifests. Metadata via a single HEAD per asset (size, MIME) plus image dimension probing for raster formats; fonts and video are not downloaded by default. Each asset records URL, type, dimensions, size, MIME, source page, usage locations and licence status.

**Licensing gate:** `licensing.py` classifies every asset as `owned`, `licensed`, `unknown` or `restricted` based on the scope record, declared licence metadata and the host's terms. Export of an `unknown` or `restricted` asset is refused with a reason; the manifest still lists it as evidence. No access control is bypassed to obtain anything.

### D. Component reconstruction
Repeated-subtree clustering with structural hashing, landmark and semantic grouping, slot and prop inference from varying text, links and image sources, variant detection across pages, state capture, and responsive behaviour described per breakpoint. Each `ComponentSpec` carries the evidence node IDs it was derived from and a confidence level.

### E. Visual comparison
Reference snapshot vs reconstruction snapshot, rendered locally. Screenshot comparison uses a perceptual diff with an explicit tolerance and reports the diff percentage per region. Element comparison matches by selector path and text similarity, then reports missing, extra, moved and resized elements. Typography and spacing deltas are reported numerically, not as adjectives. Responsive comparison repeats per viewport. A difference is reported as a difference, never as a pass or fail without a stated threshold.

### F. Code generation
The IR is stack-agnostic; emitters are pure and deterministic. Supported targets: HTML, CSS, vanilla JS, React, Next.js, Vue. Stack choice is independent of the reference site, and the user's choice is recorded in the output. Generated code is original work derived from observed structure, not copied source.

**Fidelity rule:** every generated file states which parts are observed (structure, tokens, spacing), which are inferred (component naming, state logic) and which are unimplemented (server behaviour, data fetching).

### G. Integration with the blueprint and AGENT.md
The IR feeds `blueprint/` and `generate/agentmd.py` as a page and component source. AGENT.md gains: page inventory, component hierarchy, design tokens, CSS specifications, asset manifest summary, responsive rules, interaction inventory, implementation sequence, acceptance criteria and visual validation requirements. Each of those sections is tagged `evidence`, `proposal` or `assumption`, and the existing validator refuses to render a proposal in an evidence section.

---

## 5. Safety, authorisation and honesty

1. A snapshot cannot run without an authorisation record naming the owner or granting permission, plus the scope (host, path prefix, page budget).
2. Same-origin by default; cross-origin assets are recorded as references, not fetched, unless explicitly allowed.
3. `robots.txt` and rate limits are enforced by the session, not by the caller.
4. No credential use, no session fixation, no form submission, no authenticated scraping of private pages.
5. Assets are downloaded only when licence status permits; otherwise only metadata is kept.
6. Every claim of "private source" is refused in the output model: there is no field for it, only `observed` for what the browser saw.
7. Screenshots and snapshots stay local; nothing is uploaded anywhere.

---

## 6. Roadmap

Dependencies: **V1 requires R2 (store), V2 requires R3 (evidence v2).** V0 can start immediately because it is offline and depends only on the IR contract.

| ID | Milestone | Scope | Acceptance criteria |
|---|---|---|---|
| V0 | IR contract + fixtures | `ir/model.py`, `ir/validate.py`, two static fixture sites, golden token expectations | IR validates both fixtures; golden JSON matches; no browser needed; tests run in CI without Playwright |
| V1 | Browser inspector | `capability`, `authorisation`, `session`, `snapshot`, `dom/*` | Three viewports captured from fixture site; selectors stable across runs; node budget respected; authorisation refusal test green |
| V2 | CSS intelligence | `css/*` | Token extraction matches golden values within 1px tolerance; specificity and cascade tests; `@font-face` and motion detected on fixture |
| V3 | Asset intelligence | `assets/*` | Every asset on fixture discovered with correct MIME and dimensions; licence gate blocks export of `unknown`; no download when restricted |
| V4 | Component reconstruction | `components/*` | Repeated header, card and footer correctly clustered; variants separated; each spec cites node IDs |
| V5 | Visual comparison | `compare/*` | Screenshot diff percentage within 0.5% on identical renders; element delta report catches a deliberately moved button |
| V6 | Code generation | `codegen/*` | Six targets emit from one IR; rendered HTML structurally matches reference (node count and tokens); output deterministic across runs |
| V7 | Blueprint/AGENT.md integration | `export/spec`, `generate/*` hook | Generated AGENT.md contains page/component/token/asset sections, each provenance-tagged; validator passes |
| V8 | Workspace screens | `app/` + frontend | Visual, Components, Assets, Compare, Codegen screens operate on real snapshots; no placeholder panels |

Estimated shape: V0 is small and offline; V1–V2 carry most of the difficulty; V3 and V5 are moderate; V6 is large because six emitters is six contracts; V7 is glue; V8 depends on R11 shell.

---

## 7. Testing strategy

1. **Offline golden tests.** Saved snapshots and expected IR JSON, so the suite runs without a browser.
2. **Live fixture tests.** A local fixture site served by the test harness, marked optional in CI when Playwright is absent, never skipped silently: the suite reports "browser tests not run".
3. **Determinism.** Two runs over the same snapshot produce byte-identical IR and codegen output.
4. **Tolerance tests.** Spacing and typography comparisons assert numeric thresholds, not vague similarity.
5. **Safety tests.** Authorisation refusal, cross-origin block, restricted-asset export refusal, `robots.txt` compliance, rate-limit enforcement.
6. **Regression.** Existing 43 tests must stay green in every milestone; the suite asserts the count grows, never shrinks.

---

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Playwright dependency bloats a currently zero-dependency project | Install friction, CI weight | Optional extra `[visual]`, lazy import, capability probe, clear message when absent |
| Browser snapshots are slow and flaky | Unreliable tests | Small viewport matrix, network-idle budgets, offline golden snapshots as the default path |
| CSS cascade reconstruction is genuinely hard | Token drift, wrong values | Prefer computed values from the browser over reconstructed rules; mark reconstructed rules INFERRED |
| Codegen fidelity overclaimed | Users trust broken output | Fidelity header in every file; structural comparison cited, not aesthetic judgement |
| Asset copyright misuse | Legal exposure | Licence gate defaults to `unknown`; export refused without a stated basis |
| Scope creep into "scrape any site" | Abuse and reputational harm | Authorisation record required, same-origin default, robots enforcement, no auth bypass |

---

## 9. Decisions needed

1. **Browser engine:** Playwright (recommended, best cross-browser support and network control) or Selenium. Playwright adds ~300MB of browser binaries; that is the main cost.
2. **Where V0/V1 sit in the queue:** immediately (before R2), or after R2 store and R3 evidence v2 as the dependency analysis suggests. My recommendation is R2 first, then V0–V1, because snapshots without provenance become unverifiable data.
3. **Default asset policy:** metadata-only unless licence is declared (recommended), or metadata plus thumbnails for all.
4. **Codegen priority order:** HTML/CSS/JS first (fastest to verify), then React, then Next and Vue.

---

## 10. What this plan deliberately does not do

No form submission, no login flows, no cookie or session reuse, no scraping behind paywalls, no bulk asset harvesting, no pixel-perfect piracy of protected designs, and no claim of server-side source access. The engine reconstructs structure and produces original implementations; it does not clone someone else's protected work wholesale.
