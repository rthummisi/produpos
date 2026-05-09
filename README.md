# ProdupOS v1.0.0

**Local-first AI product-update operating system.**

ProdupOS scans every product folder in your projects directory, proposes one high-impact feature per product using Claude AI, implements it, bumps the version, updates the changelog, and commits to git — with full user approval before any write.

---

## Quick Start

```bash
produpos
```

Opens at: **http://localhost:5179**  
Backend API: **http://localhost:8091**

---

## What It Does

1. **Scan** — discovers all products under `~/Downloads/Projects`
2. **Classify** — marks each as updatable or skipped (with reason)
3. **Propose** — AI generates one feature per updatable product
4. **Review** — you approve, edit, or skip each product before anything is written
5. **Implement** — agents run concurrently, writing real code changes
6. **Version** — bumps patch version in package.json / pyproject.toml / VERSION
7. **Document** — writes PRODUCT_UPDATE.md and updates CHANGELOG.md
8. **Commit** — creates git branch + commit per product
9. **Report** — JSON + Markdown report saved to `data/reports/`

---

## Installation

```bash
# From the ProdupOS root:
cd ~/Downloads/Projects/ProdUPOS

# Install backend
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

# Install frontend
cd frontend && npm install && cd ..

# Make CLI global (already done if you ran the installer)
ln -sf ~/Downloads/Projects/ProdUPOS/cli/produpos ~/.local/bin/produpos
```

Set your Anthropic API key for full AI features (optional — fallback mode works without it):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## UI Pages

| Page | Purpose |
|------|---------|
| Dashboard | Overview stats, scan button, last run summary |
| Products | Full scan table with confidence scores and health |
| Review | Per-product feature approval, diff preview, backlog |
| Console | Real-time agent logs via WebSocket |
| Results | Run history with version before/after table, rollback |
| Schedule | Create interval/daily/weekly automated runs |
| Settings | All configuration with live save |

---

## Products Skipped (Never Modified)

- Empty folders
- Documentation/PDF/image-only folders
- No recognizable stack structure
- Persistently skipped by user
- Self (`ProdUPOS`)

---

## Safety Guarantees

- **No writes before approval** (require_approval_before_write = true by default)
- **Snapshot before every write** — rollback available in UI
- **Post-implementation verification** — restores snapshot if syntax check fails
- **Never touches**: `.env`, `.env.*`, secrets, `node_modules`, `venv`, `.git` internals
- **Dirty repo protection**: warns and blocks if repo has uncommitted user changes
- **No force push**, no remote push unless explicitly enabled

---

## Skip Logic

```
Empty folder          → "Empty folder"
Docs/PDFs only        → "Documentation/assets only"
No code structure     → "No recognizable product structure"
User set skip         → "Persistently skipped by user"
Dirty repo (blocked)  → "Repo is dirty..."
```

---

## Configuration

All settings available in the UI under **Settings** or via environment variables.

Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `PROJECTS_ROOT` | `~/Downloads/Projects` | Primary scan root |
| `MAX_CONCURRENT_AGENTS` | 3 | Parallel agent limit |
| `AGENT_TIMEOUT_SECONDS` | 300 | Per-agent timeout |
| `REQUIRE_APPROVAL_BEFORE_WRITE` | true | Block dirty repos |
| `ALLOW_GIT_COMMITS` | true | Commit changes |
| `ALLOW_GITHUB_PR` | false | Push + open PR |
| `DRY_RUN` | false | Plan only, no writes |
| `AI_MODEL` | claude-sonnet-4-6 | Claude model |

---

## Architecture

See `PRODUPOOS_ARCHITECTURE.md` for full system design.

---

## Ports

| Service | Port |
|---------|------|
| Backend (FastAPI) | 8091 |
| Frontend (Vite/React) | 5179 |

---

## Version History

See `CHANGELOG.md` for full release notes.

---

_ProdupOS v1.0.0 — Built 2026-05-08_
