# ProdupOS Architecture — v1.0.0

## System Overview

```
produpos (CLI)
    ├── uvicorn backend.app.main:app   (port 8091)
    └── vite dev                       (port 5179)
```

## Backend Module Map

```
backend/app/
├── main.py              FastAPI app, all REST endpoints, WebSocket log stream
├── config.py            Settings (pydantic-settings), constants, never-touch patterns
├── db.py                SQLAlchemy engine, session factory, init_db()
├── models.py            ORM: Product, Run, RunItem, Snapshot, FeatureBacklogItem,
│                              ScheduledRun, Setting
├── schemas.py           Pydantic in/out: FeatureProposal, FileChange, ProductOut, ...
├── safety.py            Snapshot create/restore, git status, never-touch guards,
│                              per-product exclusion check, pre-run safety check
├── repo_scanner.py      Scan roots → classify_product() → detect_stack() →
│                              confidence score → git status
├── dependency_checker.py PyPI + npm registry checks for outdated packages
├── health_scorer.py     Tests, README, CI, CHANGELOG, commit age, TODOs → 0-1 score
├── feature_planner.py   Claude tool-use → FeatureProposal; fallback by stack type;
│                              generate_multiple_proposals() for backlog
├── implementation_runner.py Claude tool-use → List[FileChange]; generate_diff();
│                              apply_implementation(); verify_implementation()
├── git_manager.py       create_branch(), stage_files(), commit_changes(),
│                              create_github_pr(), push_branch()
├── version_manager.py   get/bump patch version in package.json / pyproject.toml / VERSION
├── changelog_manager.py update CHANGELOG.md; write PRODUCT_UPDATE.md
├── job_manager.py       In-memory log store + subscriber callbacks (WebSocket push)
├── product_agent.py     ProductAgent class: analyze → propose → snapshot → implement
│                              → verify → version → changelog → git → report
├── agent_orchestrator.py asyncio Semaphore-based concurrent agent runner;
│                              run report generation (JSON + MD)
└── scheduler.py         Background asyncio task; interval/daily/weekly scheduling
```

## Frontend Component Map

```
frontend/src/
├── App.jsx              BrowserRouter, sidebar nav, dark mode toggle
├── api.js               Typed fetch wrapper; createWebSocket()
└── components/
    ├── Dashboard.jsx        Stats cards, scan trigger, product preview
    ├── ProductScanTable.jsx Full product table with filter, analyze, skip-always
    ├── FeatureReviewPanel.jsx Per-product: mode select, proposal, diff preview,
    │                           backlog drawer, exclusions, run single
    ├── RunConsole.jsx       Run selector + WebSocket log stream, color-coded output
    ├── ResultsSummary.jsx   Run history, product update table (version before/after),
    │                           rollback button, CSV/MD export
    ├── SchedulerPanel.jsx   Create/toggle/delete scheduled runs
    └── SettingsPanel.jsx    All settings with live save, safety info panel
```

## Data Flow

```
User: producos → scan
  → repo_scanner.scan_projects()
  → product_classifier.classify_product() per folder
  → DB: upsert Product rows
  → UI: ProductScanTable renders

User: propose feature
  → feature_planner.propose_feature_with_ai()
      → Claude API (tool: submit_feature_proposal)
      → fallback: FALLBACK_FEATURES by stack
  → DB: Product.proposed_feature_json updated

User: run all
  → agent_orchestrator.run_products()
  → asyncio.gather(agent.run() for each product, concurrency=Semaphore(N))
  → ProductAgent per product:
      1. safety check (git status, dirty check)
      2. load proposal from DB
      3. generate_implementation_with_ai()
             → read repo files
             → Claude API (tool: submit_implementation)
             → fallback: PRODUCT_UPDATE.md placeholder
      4. store diff_preview in RunItem
      5. create_snapshot() → Snapshot row
      6. apply_implementation() → write files
      7. verify_implementation() → py_compile / json.loads
      8. bump_version() → package.json / pyproject.toml
      9. update_changelog() + write_product_update_doc()
     10. git: create_branch() → stage_files() → commit_changes()
     11. (optional) create_github_pr()
     12. update RunItem status, tokens, cost
  → generate run reports (JSON + MD)
  → WebSocket: log lines streamed to RunConsole

User: rollback
  → GET /api/products/{id}/snapshots
  → POST /api/products/{id}/rollback {snapshot_id}
  → restore_snapshot() writes old_content back to each file
```

## Database Schema

```
products          id, name, path, detected_stack, updatable, skip_reason,
                  git_status, current_version, proposed_feature, proposed_feature_json,
                  manual_feature, mode, selected, skip_persistent,
                  per_product_exclusions, health_score, health_details,
                  dependency_report, feature_backlog, code_confidence_score

runs              id, started_at, completed_at, status, total/updated/skipped/failed,
                  total_tokens_used, estimated_cost_usd, report_path

run_items         id, run_id, product_id, status, feature_title,
                  version_before, version_after, git_branch, git_commit,
                  github_pr_url, reason, logs, diff_preview, file_changes,
                  verification_result, partial_state, tokens_used, estimated_cost_usd

snapshots         id, product_id, run_item_id, files_snapshot (JSON),
                  git_stash_ref, restored

feature_backlog   id, product_id, feature_title, customer_problem,
                  why_this_matters, files_likely_to_change, risk_level,
                  estimated_scope, demo_instructions, status

scheduled_runs    id, name, schedule_type, schedule_value, mode, dry_run,
                  enabled, next_run, last_run, last_run_id

settings          key, value
```

## API Endpoints

```
GET  /health
POST /api/scan
GET  /api/products
GET  /api/products/{id}
POST /api/products/{id}/analyze
POST /api/products/{id}/propose
POST /api/products/{id}/propose-backlog
POST /api/products/{id}/mode
POST /api/products/{id}/manual-feature
POST /api/products/{id}/exclude-files
POST /api/products/{id}/skip-persistent
GET  /api/products/{id}/diff
GET  /api/products/{id}/backlog
POST /api/products/{id}/backlog/{bid}/select
GET  /api/products/{id}/snapshots
POST /api/products/{id}/rollback
POST /api/run
POST /api/run/{id}
GET  /api/runs
GET  /api/runs/{id}
GET  /api/jobs/{id}/logs
GET  /api/reports
GET  /api/reports/{name}
GET  /api/reports/{name}/export?format=csv|md
GET  /api/schedules
POST /api/schedules
DELETE /api/schedules/{id}
PATCH  /api/schedules/{id}/toggle
GET  /api/settings
POST /api/settings
WS   /ws/logs/{job_id}
```

## Concurrency Model

- FastAPI + uvicorn: async event loop
- Agents: asyncio tasks behind `asyncio.Semaphore(max_concurrent_agents)`
- DB: SQLAlchemy sync (thread-safe via connection pool)
- WebSocket: per-job subscriber list; logs pushed via callback on `asyncio.call_soon_threadsafe`
- Scheduler: single asyncio background task checking every 60s

## AI Integration

- Model: configurable (default `claude-sonnet-4-6`)
- Feature proposal: Claude tool-use → `submit_feature_proposal`
- Backlog: Claude tool-use → `submit_backlog` (3-5 proposals)
- Implementation: Claude tool-use → `submit_implementation` (file changes)
- Fallback: deterministic by detected_stack when `ANTHROPIC_API_KEY` not set
- Token tracking: input + output tokens per call, stored in RunItem

## Safety Architecture

```
Never touch: .env, *.key, *.pem, secrets.json, node_modules, .git
Pre-run: git status check → warn/block on dirty
Snapshot: read all files-to-change before first write
Verify: py_compile + json.loads after writes
Partial recovery: restore snapshot on any write/verify failure
Timeout recovery: restore snapshot on asyncio.TimeoutError
User exclusions: per-product pattern list respected at write time
Dry run: full pipeline without any file writes
```
