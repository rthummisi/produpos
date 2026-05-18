# ProdupOS Changelog

## [2.1.0] — 2026-05-17

### Added — Per-Product E2E Testing (agent-browser)

#### Two new buttons on every product card (Feature Review page) and Products scan table:

- **"E2E Testing"** — runs an end-to-end test of the product in-place, immediately showing inline pass/fail results with per-check details. No navigation required; results appear directly in the product card.
- **"Run {Product} & Test E2E"** — builds the product via the AI agent *and* then immediately runs E2E tests against the newly built version. Streams combined build + test logs to the Run Console.

#### E2E test engine (`backend/app/e2e_tester.py`):
- **Agent-browser via Playwright** (`playwright>=1.48.0`) — launches a headless Chromium browser, navigates to the product's auto-detected URL, and verifies each AI-generated check scenario.
- **AI test-plan generation** — uses the configured AI provider (Gemini / Anthropic / Groq / Ollama) to generate 3–5 realistic browser/HTTP test scenarios from the product's README and file structure.
- **HTTP fallback** — if Playwright browsers are not installed, falls back to `httpx` HTTP checks automatically.
- **Existing test suite runner** — detects and runs `pytest` (Python) and `npm test` (Node) if present.
- **Auto start-command detection** — reads `vite.config.*`, `package.json`, `manage.py`, `main.py`, `go.mod`, etc. to determine how to start the product and which port/URL to test.
- **Graceful port detection** — if the app is already running on the expected port, skips starting it.
- Results stored in new `e2e_test_results` DB table; latest status cached on the `products` row as `last_e2e_status`.

#### New API endpoints:
- `POST /api/products/{id}/e2e-test` — trigger E2E test, returns `{job_id}` for WebSocket streaming.
- `POST /api/products/{id}/run-and-e2e` — build product then run E2E; E2E logs appended to the same run job so Console shows everything in one stream.
- `GET /api/products/{id}/e2e-results` — list recent E2E test results for a product.

#### UI changes:
- **Feature Review** — each `ProductCard` gains three action buttons, a live pulsing "Testing E2E…" state, and an inline result block showing per-check pass/fail with HTTP status codes.
- **E2E status badge** in the card header: green `E2E ✓ passed`, red `E2E ✗ failed`, gray `E2E · no_tests`.
- **Products scan table** — new "E2E" column shows cached last status badge; "E2E Testing" button in Actions column starts a test and updates the badge inline.

#### Schema changes:
- `products` table: new `last_e2e_status` (TEXT) and `last_e2e_at` (DATETIME) columns, migrated automatically at startup.
- New `e2e_test_results` table with full per-check JSON details.

---

## [1.1.0] — 2026-05-09

### Added — Startup Guardian
- `startup_guardian.py`: runs automatically on every `produpos` launch
- Scans `~/Downloads/Projects` for **new product folders** not yet in the DB — new products are added and appear in the UI with no manual scan needed
- **Version sanitization** for every product on startup:
  - Version file behind git tag → syncs file to match tag, commits, pushes
  - Git tag behind version file → creates annotated tag and pushes
  - No version anywhere → writes `0.1.0`, tags HEAD, pushes
  - Missing `CHANGELOG.md` → creates one automatically
- All fixes auto-committed with `chore(guardian): sanitize version` and pushed to each product's remote
- Guardian report saved to `data/guardian/guardian-YYYYMMDD-HHMMSS.json`
- `GET /api/guardian` — full guardian report
- `POST /api/guardian/run` — trigger manual re-run
- **Dashboard guardian panel**: colour-coded status bar (green = clean, blue = changes made, red = errors); auto-polls until ready; "Re-run" button
- **CLI output**: shows guardian summary after startup (`✓ Guardian: 2 version(s) synced, 1 new product(s) detected`)
- ProdupOS self-included in guardian sanity (version + tag + clean state)

### Added — Update All (Auto + Manual)
- Dashboard: "Update all N" button runs all products in their current mode without going to Review
- Breakdown shows `⚡ N auto · ✏️ N manual` before running
- Feature Review: bulk "⚡ All auto" / "✏️ All manual" buttons switch all products at once
- Per-product checkbox to include/exclude from a run; "Select: All / None" toggles
- Run button shows live breakdown: `Update 6 products · ⚡ 4 auto · ✏️ 2 manual`
- `POST /api/bulk/products/mode` — set mode for all updatable products in one call
- `POST /api/products/{id}/selected` — toggle per-product run inclusion

### Changed — Version Bumping
- Switched from **patch** bumps (`1.0.0 → 1.0.1`) to **minor** bumps (`1.0.0 → 1.1.0`) for all AI-implemented features
- Patch reset to 0 on minor bump: `2.3.5 → 2.4.0`
- No version → starts at `0.1.0`

### Added — Git Push on Update
- After every product update: push the `produpos/update-*` branch to `origin`
- `push_branch()` returns `(bool, message)` — push result visible in Run Console logs
- Gracefully skips push if no remote configured

### Fixed — Dirty Repo Stash Flow
- Before implementation: `git stash push --include-untracked` saves user's WIP
- Implementation runs on clean HEAD → new branch → commit → push
- After push: `git checkout original-branch` → `git stash pop` (user's work restored)
- Snapshot restored on any failure at any step

### Fixed — Dashboard Versions
- Scan endpoint now reads `current_version` from filesystem for every product
- Versions displayed immediately after Scan (no separate "Analyze" step)
- Dashboard products table: Product | Stack | Version | Mode | Status columns

### Fixed — Nested Product Discovery
- Wrapper folders (e.g. `ARMORS/` containing `armors-repo/`) are now handled correctly
- When a top-level folder has no product indicators, scanner looks one level deeper
- `armors-repo` correctly detected as Docker + Full-Stack, updatable

### Fixed — Stale Product Eviction
- On every scan, DB products whose path no longer exists in the filesystem are deleted
- Prevents ghost entries from old scans appearing in the UI
- Preserves products with run history or `skip_persistent = true`

### Fixed — CLI Script
- `&>>` after `\` line continuation caused a bash syntax error — replaced with `>> file 2>&1 &`
- `PYTHONPATH` corrected from `backend/` to project root (required for `backend.app.main` import)
- `mkdir -p` added for logs directory to prevent startup failure on first run

---

## [1.0.0] — 2026-05-08

### Initial Major Release

This is the first production release of ProdupOS — a local-first AI product-update operating system.

#### Core Contract (Original Specification)

- **Global CLI command**: `produpos` launches the full system from any terminal path
- **Product scanning**: Scans all folders under `~/Downloads/Projects` and classifies each as updatable or skippable
- **Smart classification**: Detects stack (React, Next.js, FastAPI, Django, Flask, Node, Docker, Go, Rust, Full-Stack) with confidence scoring
- **Pre-run transparency**: Shows updatable/skipped products with reasons BEFORE any writes occur
- **Auto Update Mode**: ProdupOS proposes the single best feature per product using Claude AI
- **Manual Update Mode**: User specifies exact feature to implement per product
- **Mixed mode**: Some products on auto, others on manual
- **Concurrent agents**: Multiple ProductAgent instances run simultaneously (configurable max)
- **Feature implementation**: AI generates real file changes and writes them to target repos
- **Version management**: Bumps patch version in package.json, pyproject.toml, or VERSION file
- **PRODUCT_UPDATE.md**: Written to every updated product repo with full feature context
- **CHANGELOG.md update**: Appended with version entry per update
- **Git integration**: Creates `produpos/update-YYYYMMDD-HHMM-{product}` branches, stages relevant files, commits with structured message
- **Run reports**: JSON + Markdown reports saved to `data/reports/run-YYYYMMDD-HHMM.*`
- **Web UI**: Polished React + Tailwind dashboard with 7 pages
- **SQLite database**: Persistent product state, run history, settings
- **Backend**: FastAPI on port 8091
- **Frontend**: Vite/React on port 5179
- **Safety rules**: Never touches .env, secrets, node_modules, or deletes files

#### 17 Enhancements Added at v1.0.0

1. **Rollback / Snapshot Restore**: Pre-implementation snapshot of all files to be changed. Per-run rollback button in Results UI. Snapshot stored in SQLite.

2. **Diff Preview**: Before implementation approval, generates unified diff (old vs new) for every file. Visible in Feature Review panel.

3. **Post-Implementation Verification**: After writing files, runs py_compile on Python files and JSON/YAML parsers on config files. Restores snapshot automatically on verification failure.

4. **Agent Timeout**: Each agent wrapped in `asyncio.wait_for` with configurable timeout (default 300s). Timed-out agents restore their snapshot and mark status `timed_out`.

5. **Skip Persistence**: Per-product toggle to permanently exclude a product from all future runs. Stored in DB, respected by scanner on re-scan.

6. **Feature Backlog**: Generate 3-5 alternative feature proposals per product. Stored in DB. Backlog drawer in Review panel lets user select any backlog item as the active proposal.

7. **AI Token Cost Estimation**: Token usage tracked per agent and per run. Cost estimated at current Claude Sonnet pricing. Shown in Results summary and run detail.

8. **Dependency Health Check**: Checks PyPI (for Python repos) and npm registry (for Node repos) for outdated packages. Top 15 dependencies checked. Outdated count and per-package detail stored in DB.

9. **Version Before → After in Results Table**: Results Summary shows `Version Before` and `Version After` columns side-by-side in the product update table.

10. **Scheduled / Cron Mode**: Create interval, daily, or weekly schedules via the Scheduler page. Background asyncio task checks every 60 seconds and fires due schedules automatically.

11. **GitHub PR Creation**: Optional. When `allow_github_pr=true` and `GITHUB_TOKEN` is set, pushes branch to origin and opens a GitHub PR after commit.

12. **Product Health Score**: Composite score (0–100%) based on: has tests, has README, has CI, has CHANGELOG, git cleanliness, last commit age, TODO count, doc quality, dep freshness.

13. **Dark Mode**: Toggle in sidebar. Persists in localStorage. Full dark/light coverage across all 7 UI pages.

14. **Export Results**: CSV and Markdown export of any run report from the Results page.

15. **Multi-Root Scanning**: Settings field for comma-separated additional scan roots beyond `~/Downloads/Projects`.

16. **Partial Implementation Recovery**: `partial_state` flag in RunItem. Agent restores snapshot on any write failure mid-implementation — no half-written repos.

17. **Per-Product File Exclusions**: Per-product comma-separated file pattern list. Any matching file is skipped during implementation writes even if AI proposes it.

#### Skip Logic

Products are skipped (not modified, ever) if they match any:
- Folder is empty
- Folder contains only docs/PDFs/images (no code structure)
- No recognizable stack indicators
- `skip_persistent = true` (user-set)
- Git repo is dirty AND `require_approval_before_write = true`

Skipped: `ARMORS`, `honeycombe-ai`, `Payos`, `ProdUPOS` (self)

#### Files Created

- `backend/app/` — 19 Python modules
- `frontend/src/` — App.jsx + 7 component pages
- `cli/produpos` — Global bash launcher
- `data/` — SQLite DB, runs/, reports/
- `README.md`, `CHANGELOG.md`, `PRODUPOOS_ARCHITECTURE.md`

---

_Built by ProdupOS — first major version, 2026-05-08_
