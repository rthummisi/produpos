import asyncio
import csv
import io
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from pydantic import BaseModel as _BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db, init_db
from .models import Product, Run, RunItem, Snapshot, FeatureBacklogItem, ScheduledRun, Setting
from .schemas import (
    ProductOut, RunOut, RunItemOut, SnapshotOut, FeatureBacklogItemOut, ScheduledRunOut,
    SetModeRequest, SetManualFeatureRequest, SetExclusionsRequest, SetSkipPersistentRequest,
    RunRequest, ScheduleCreateRequest, SettingsUpdateRequest, RollbackRequest,
)
from .repo_scanner import scan_projects
from .dependency_checker import check_dependencies
from .health_scorer import calculate_health_score
from .feature_planner import propose_feature_with_ai, generate_multiple_proposals
from .safety import get_git_status, restore_snapshot
from .job_manager import get_logs, subscribe, unsubscribe
from .scheduler import scheduler_loop, create_schedule

app = FastAPI(title="ProdupOS", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_scheduler_task = None


@app.on_event("startup")
async def startup():
    init_db()
    if settings.enable_scheduler:
        global _scheduler_task
        _scheduler_task = asyncio.create_task(scheduler_loop())


@app.on_event("shutdown")
async def shutdown():
    if _scheduler_task:
        _scheduler_task.cancel()


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "backend_port": settings.backend_port,
        "projects_root": settings.projects_root,
        "ai_enabled": bool(settings.anthropic_api_key),
        "dry_run": settings.dry_run,
    }


# ─── Scan ─────────────────────────────────────────────────────────────────────

@app.post("/api/scan")
def scan(db: Session = Depends(get_db)):
    roots = settings.get_all_roots()
    raw_products = scan_projects(roots)

    # Build set of current scanned paths so we can evict stale DB rows
    current_paths = {rp["path"] for rp in raw_products}

    # Remove products whose path no longer exists in the scan
    # (preserves products with run history or user-set skip_persistent)
    all_db_products = db.query(Product).all()
    for dbp in all_db_products:
        if dbp.path not in current_paths and not dbp.skip_persistent:
            has_runs = db.query(RunItem).filter(RunItem.product_id == dbp.id).first()
            if not has_runs:
                db.delete(dbp)
    db.commit()

    # Upsert current scan results
    result = []
    for rp in raw_products:
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, rp["path"]))
        existing = db.query(Product).filter(Product.id == pid).first()
        git_status_str = rp.get("repo_status", "unknown")

        if existing:
            if existing.skip_persistent:
                result.append(existing)
                continue
            existing.detected_stack = rp.get("detected_stack", "")
            existing.updatable = rp.get("updatable", False)
            existing.skip_reason = rp.get("skip_reason", "")
            existing.git_status = git_status_str
            existing.code_confidence_score = rp.get("code_confidence_score", 0.0)
            existing.updated_at = datetime.utcnow()
            db.commit()
            result.append(existing)
        else:
            p = Product(
                id=pid,
                name=rp["product_name"],
                path=rp["path"],
                detected_stack=rp.get("detected_stack", ""),
                updatable=rp.get("updatable", False),
                skip_reason=rp.get("skip_reason", ""),
                git_status=git_status_str,
                code_confidence_score=rp.get("code_confidence_score", 0.0),
                current_version="",
            )
            db.add(p)
            db.commit()
            db.refresh(p)
            result.append(p)

    return [ProductOut.model_validate(p) for p in result]


# ─── Products ─────────────────────────────────────────────────────────────────

@app.get("/api/products", response_model=List[ProductOut])
def list_products(db: Session = Depends(get_db)):
    return db.query(Product).all()


@app.get("/api/products/{product_id}", response_model=ProductOut)
def get_product(product_id: str, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404, "Product not found")
    return p


@app.post("/api/products/{product_id}/analyze")
def analyze_product(product_id: str, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404, "Product not found")

    # Dependency check
    dep_report = check_dependencies(p.path, p.detected_stack)
    p.dependency_report = json.dumps(dep_report)

    # Health score
    git_info = get_git_status(p.path)
    health = calculate_health_score(p.path, git_info, dep_report)
    p.health_score = health["score"]
    p.health_details = json.dumps(health["details"])

    # Current version
    from .version_manager import get_current_version
    p.current_version = get_current_version(p.path) or ""

    db.commit()
    return {"health": health, "dependencies": dep_report}


class BulkModeRequest(_BaseModel):
    product_ids: Optional[List[str]] = None
    mode: str

class SetSelectedRequest(_BaseModel):
    selected: bool

@app.post("/api/bulk/products/mode")
def bulk_set_mode(req: BulkModeRequest, db: Session = Depends(get_db)):
    query = db.query(Product).filter(Product.updatable == True)
    if req.product_ids:
        query = query.filter(Product.id.in_(req.product_ids))
    products = query.all()
    for p in products:
        p.mode = req.mode
    db.commit()
    return {"updated": len(products), "mode": req.mode}

@app.post("/api/products/{product_id}/selected")
def set_selected(product_id: str, req: SetSelectedRequest, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404)
    p.selected = req.selected
    db.commit()
    return {"selected": p.selected}

@app.post("/api/products/{product_id}/propose")
def propose_feature(product_id: str, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p or not p.updatable:
        raise HTTPException(404, "Product not found or not updatable")

    from pathlib import Path as PPath

    readme = ""
    for fname in ["README.md", "README", "readme.md"]:
        fp = PPath(p.path) / fname
        if fp.exists():
            readme = fp.read_text(encoding="utf-8", errors="replace")[:3000]
            break

    file_summary = "\n".join(
        str(f.relative_to(PPath(p.path)))
        for f in sorted(PPath(p.path).rglob("*"))[:50]
        if f.is_file() and ".git" not in str(f)
    )

    existing = [i.get("feature_title", "") for i in json.loads(p.feature_backlog or "[]")]
    proposal, tokens = propose_feature_with_ai(
        p.name, p.path, p.detected_stack, readme, file_summary, existing,
        manual_override=p.manual_feature if p.mode == "manual" else None,
    )

    p.proposed_feature = proposal.feature_title
    p.proposed_feature_json = proposal.model_dump_json()
    db.commit()

    # Also generate backlog proposals in background
    return {"proposal": proposal.model_dump(), "tokens_used": tokens}


@app.post("/api/products/{product_id}/propose-backlog")
def propose_backlog(product_id: str, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404, "Product not found")

    from pathlib import Path as PPath
    readme = ""
    for fname in ["README.md", "README"]:
        fp = PPath(p.path) / fname
        if fp.exists():
            readme = fp.read_text(errors="replace")[:2000]
            break
    file_summary = "\n".join(
        str(f.relative_to(PPath(p.path)))
        for f in sorted(PPath(p.path).rglob("*"))[:40]
        if f.is_file() and ".git" not in str(f)
    )

    proposals, tokens = generate_multiple_proposals(
        p.name, p.path, p.detected_stack, readme, file_summary
    )

    added = []
    for prop in proposals:
        bi = FeatureBacklogItem(
            id=str(uuid.uuid4()),
            product_id=p.id,
            feature_title=prop.feature_title,
            customer_problem=prop.customer_problem,
            why_this_matters=prop.why_this_matters,
            files_likely_to_change=", ".join(prop.files_likely_to_change),
            risk_level=prop.risk_level,
            estimated_scope=prop.estimated_scope,
            demo_instructions=prop.demo_instructions,
        )
        db.add(bi)
        added.append(prop.feature_title)
    db.commit()

    return {"added": added, "tokens_used": tokens}


@app.post("/api/products/{product_id}/mode")
def set_mode(product_id: str, req: SetModeRequest, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404)
    p.mode = req.mode
    db.commit()
    return {"mode": p.mode}


@app.post("/api/products/{product_id}/manual-feature")
def set_manual_feature(product_id: str, req: SetManualFeatureRequest, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404)
    p.manual_feature = req.feature
    p.mode = "manual"
    db.commit()
    return {"manual_feature": p.manual_feature}


@app.post("/api/products/{product_id}/exclude-files")
def set_exclusions(product_id: str, req: SetExclusionsRequest, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404)
    p.per_product_exclusions = req.patterns
    db.commit()
    return {"exclusions": p.per_product_exclusions}


@app.post("/api/products/{product_id}/skip-persistent")
def set_skip_persistent(product_id: str, req: SetSkipPersistentRequest, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404)
    p.skip_persistent = req.skip
    if req.skip:
        p.selected = False
    db.commit()
    return {"skip_persistent": p.skip_persistent}


@app.get("/api/products/{product_id}/diff")
def get_diff(product_id: str, run_item_id: Optional[str] = None, db: Session = Depends(get_db)):
    if run_item_id:
        ri = db.query(RunItem).filter(RunItem.id == run_item_id).first()
        if ri and ri.diff_preview:
            return json.loads(ri.diff_preview)
    return []


@app.get("/api/products/{product_id}/backlog", response_model=List[FeatureBacklogItemOut])
def get_backlog(product_id: str, db: Session = Depends(get_db)):
    return db.query(FeatureBacklogItem).filter(FeatureBacklogItem.product_id == product_id).all()


@app.post("/api/products/{product_id}/backlog/{backlog_id}/select")
def select_from_backlog(product_id: str, backlog_id: str, db: Session = Depends(get_db)):
    item = db.query(FeatureBacklogItem).filter(FeatureBacklogItem.id == backlog_id).first()
    if not item:
        raise HTTPException(404)
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404)
    p.proposed_feature = item.feature_title
    p.proposed_feature_json = json.dumps({
        "feature_title": item.feature_title,
        "customer_problem": item.customer_problem,
        "why_this_matters": item.why_this_matters,
        "files_likely_to_change": item.files_likely_to_change.split(", "),
        "risk_level": item.risk_level,
        "estimated_scope": item.estimated_scope,
        "demo_instructions": item.demo_instructions,
    })
    db.commit()
    return {"selected": item.feature_title}


@app.post("/api/products/{product_id}/rollback")
def rollback_product(product_id: str, req: RollbackRequest, db: Session = Depends(get_db)):
    snap = db.query(Snapshot).filter(
        Snapshot.id == req.snapshot_id,
        Snapshot.product_id == product_id,
    ).first()
    if not snap:
        raise HTTPException(404, "Snapshot not found")

    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404)

    try:
        file_snap = json.loads(snap.files_snapshot)
        messages = restore_snapshot(p.path, file_snap)
        snap.restored = True
        db.commit()
        return {"restored": True, "messages": messages}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/products/{product_id}/snapshots", response_model=List[SnapshotOut])
def get_snapshots(product_id: str, db: Session = Depends(get_db)):
    return db.query(Snapshot).filter(Snapshot.product_id == product_id).all()


# ─── Runs ─────────────────────────────────────────────────────────────────────

@app.post("/api/run")
async def start_run(req: RunRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from .agent_orchestrator import run_products

    async def _run():
        await run_products(db, req.product_ids, req.dry_run)

    background_tasks.add_task(_run)
    return {"status": "started", "message": "Run initiated in background"}


@app.post("/api/run/{product_id}")
async def run_single(product_id: str, dry_run: bool = False, background_tasks: BackgroundTasks = None, db: Session = Depends(get_db)):
    from .agent_orchestrator import run_products

    async def _run():
        await run_products(db, [product_id], dry_run)

    background_tasks.add_task(_run)
    return {"status": "started", "product_id": product_id}


@app.get("/api/runs", response_model=List[RunOut])
def list_runs(db: Session = Depends(get_db)):
    return db.query(Run).order_by(Run.started_at.desc()).limit(50).all()


@app.get("/api/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404)
    return run


@app.get("/api/jobs/{job_id}/logs")
def get_job_logs(job_id: str):
    return {"logs": get_logs(job_id)}


# ─── Reports ──────────────────────────────────────────────────────────────────

@app.get("/api/reports")
def list_reports():
    reports_dir = Path(settings.data_dir) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(reports_dir.glob("run-*.json"), reverse=True)
    return [{"name": f.name, "path": str(f)} for f in files[:20]]


@app.get("/api/reports/{report_name}")
def get_report(report_name: str):
    reports_dir = Path(settings.data_dir) / "reports"
    fp = reports_dir / report_name
    if not fp.exists() or not str(fp).startswith(str(reports_dir)):
        raise HTTPException(404)
    return json.loads(fp.read_text())


@app.get("/api/reports/{report_name}/export")
def export_report(report_name: str, format: str = "csv"):
    reports_dir = Path(settings.data_dir) / "reports"
    fp = reports_dir / report_name
    if not fp.exists():
        raise HTTPException(404)

    data = json.loads(fp.read_text())

    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "product", "status", "mode", "feature_implemented",
            "version_before", "version_after", "git_branch", "commit",
            "tokens_used", "cost_usd"
        ])
        writer.writeheader()
        for row in data.get("products", []):
            writer.writerow(row)
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.read().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={report_name.replace('.json', '.csv')}"},
        )

    md_path = reports_dir / report_name.replace(".json", ".md")
    if md_path.exists():
        return StreamingResponse(
            io.BytesIO(md_path.read_bytes()),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={md_path.name}"},
        )

    return data


# ─── Schedules ────────────────────────────────────────────────────────────────

@app.get("/api/schedules", response_model=List[ScheduledRunOut])
def list_schedules(db: Session = Depends(get_db)):
    return db.query(ScheduledRun).all()


@app.post("/api/schedules", response_model=ScheduledRunOut)
def create_scheduled_run(req: ScheduleCreateRequest, db: Session = Depends(get_db)):
    return create_schedule(db, req.name, req.schedule_type, req.schedule_value, req.mode, req.dry_run)


@app.delete("/api/schedules/{schedule_id}")
def delete_schedule(schedule_id: str, db: Session = Depends(get_db)):
    s = db.query(ScheduledRun).filter(ScheduledRun.id == schedule_id).first()
    if not s:
        raise HTTPException(404)
    db.delete(s)
    db.commit()
    return {"deleted": True}


@app.patch("/api/schedules/{schedule_id}/toggle")
def toggle_schedule(schedule_id: str, db: Session = Depends(get_db)):
    s = db.query(ScheduledRun).filter(ScheduledRun.id == schedule_id).first()
    if not s:
        raise HTTPException(404)
    s.enabled = not s.enabled
    db.commit()
    return {"enabled": s.enabled}


# ─── Settings ─────────────────────────────────────────────────────────────────

@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db)):
    rows = db.query(Setting).all()
    base = {
        "projects_root": settings.projects_root,
        "additional_roots": settings.additional_roots,
        "max_concurrent_agents": settings.max_concurrent_agents,
        "agent_timeout_seconds": settings.agent_timeout_seconds,
        "require_approval_before_write": settings.require_approval_before_write,
        "allow_git_commits": settings.allow_git_commits,
        "allow_git_branch_creation": settings.allow_git_branch_creation,
        "allow_non_git_updates": settings.allow_non_git_updates,
        "allow_auto_create_git_repo": settings.allow_auto_create_git_repo,
        "allow_github_pr": settings.allow_github_pr,
        "dry_run": settings.dry_run,
        "ai_model": settings.ai_model,
        "ai_enabled": bool(settings.anthropic_api_key),
    }
    overrides = {r.key: r.value for r in rows}
    return {**base, **overrides}


@app.post("/api/settings")
def update_setting(req: SettingsUpdateRequest, db: Session = Depends(get_db)):
    s = db.query(Setting).filter(Setting.key == req.key).first()
    if s:
        s.value = req.value
    else:
        s = Setting(key=req.key, value=req.value)
        db.add(s)
    db.commit()
    return {"key": req.key, "value": req.value}


# ─── WebSocket log streaming ──────────────────────────────────────────────────

@app.websocket("/ws/logs/{job_id}")
async def websocket_logs(websocket: WebSocket, job_id: str):
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue()

    def on_log(msg: str):
        asyncio.get_event_loop().call_soon_threadsafe(queue.put_nowait, msg)

    subscribe(job_id, on_log)

    # Replay existing logs
    for log in get_logs(job_id):
        await websocket.send_text(log)

    try:
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_text(msg)
            except asyncio.TimeoutError:
                await websocket.send_text("ping")
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe(job_id, on_log)
