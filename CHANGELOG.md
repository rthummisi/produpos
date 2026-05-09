# ProdupOS Changelog

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
