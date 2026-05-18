import uuid
import asyncio
import json
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session

from .models import Product, Run, RunItem
from .product_agent import ProductAgent
from .job_manager import init_job_log, append_log
from .config import settings


async def run_products(
    db: Session,
    product_ids: Optional[List[str]],
    dry_run: bool = False,
    override_dirty: bool = False,
) -> str:
    run_id = str(uuid.uuid4())
    job_id = run_id
    init_job_log(job_id)

    query = db.query(Product).filter(Product.updatable == True, Product.selected == True)
    if product_ids:
        query = query.filter(Product.id.in_(product_ids))
    products = query.all()

    run = Run(
        id=run_id,
        started_at=datetime.utcnow(),
        status="running",
        total_products=len(products),
    )
    db.add(run)

    run_items = []
    for p in products:
        ri = RunItem(
            id=str(uuid.uuid4()),
            run_id=run_id,
            product_id=p.id,
            status="pending",
            feature_title=p.proposed_feature,
            version_before=p.current_version,
        )
        db.add(ri)
        run_items.append((p, ri))

    db.commit()

    append_log(job_id, f"Starting run {run_id} — {len(products)} products")

    sem = asyncio.Semaphore(settings.max_concurrent_agents)

    async def run_one(product: Product, run_item: RunItem):
        async with sem:
            agent = ProductAgent(product, run_item, db, job_id, dry_run, override_dirty)
            await agent.run()

    tasks = [run_one(p, ri) for p, ri in run_items]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Tally results
    items = db.query(RunItem).filter(RunItem.run_id == run_id).all()
    run.updated_count = sum(1 for i in items if i.status == "updated")
    run.skipped_count = sum(1 for i in items if i.status in ("skipped", "dry_run_complete"))
    run.failed_count = sum(1 for i in items if i.status in ("failed", "timed_out"))
    run.total_tokens_used = sum(i.tokens_used for i in items)
    run.estimated_cost_usd = round(sum(i.estimated_cost_usd for i in items), 6)
    run.status = "completed"
    run.completed_at = datetime.utcnow()
    db.commit()

    append_log(job_id, f"Run complete: {run.updated_count} updated, {run.skipped_count} skipped, {run.failed_count} failed")

    _generate_report(db, run, items, products)

    return run_id


def _generate_report(db: Session, run: Run, items: list, products: list):
    from pathlib import Path
    import os

    reports_dir = Path(settings.data_dir) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    ts = run.started_at.strftime("%Y%m%d-%H%M")
    product_map = {p.id: p for p in products}

    rows = []
    for item in items:
        p = product_map.get(item.product_id)
        rows.append({
            "product": p.name if p else item.product_id,
            "status": item.status,
            "mode": p.mode if p else "",
            "feature_implemented": item.feature_title,
            "version_before": item.version_before,
            "version_after": item.version_after,
            "git_branch": item.git_branch,
            "commit": item.git_commit,
            "github_pr": item.github_pr_url,
            "why_it_matters": "",
            "tokens_used": item.tokens_used,
            "cost_usd": item.estimated_cost_usd,
        })

    report_data = {
        "run_id": run.id,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "total": run.total_products,
        "updated": run.updated_count,
        "skipped": run.skipped_count,
        "failed": run.failed_count,
        "total_tokens": run.total_tokens_used,
        "estimated_cost_usd": run.estimated_cost_usd,
        "products": rows,
    }

    json_path = reports_dir / f"run-{ts}.json"
    json_path.write_text(json.dumps(report_data, indent=2))

    # Markdown table
    header = "| Product | Status | Mode | Feature Implemented | Version Before | Version After | Git Branch | Commit | Why It Matters |"
    sep = "|---------|--------|------|---------------------|----------------|---------------|------------|--------|----------------|"
    table_rows = []
    for r in rows:
        table_rows.append(
            f"| {r['product']} | {r['status']} | {r['mode']} | {r['feature_implemented']} "
            f"| {r['version_before']} | {r['version_after']} "
            f"| {r['git_branch']} | {r['commit']} | {r['why_it_matters']} |"
        )

    md = f"""# ProdupOS Run Report

**Run ID:** {run.id}
**Started:** {run.started_at.strftime('%Y-%m-%d %H:%M UTC')}
**Completed:** {run.completed_at.strftime('%Y-%m-%d %H:%M UTC') if run.completed_at else 'N/A'}
**Tokens Used:** {run.total_tokens_used:,}
**Estimated Cost:** ${run.estimated_cost_usd:.4f}

## Summary

| Metric | Count |
|--------|-------|
| Total Products | {run.total_products} |
| Updated | {run.updated_count} |
| Skipped | {run.skipped_count} |
| Failed | {run.failed_count} |

## Product Update Table

{header}
{sep}
{chr(10).join(table_rows)}

---
_Generated by ProdupOS v2.1.0_
"""

    md_path = reports_dir / f"run-{ts}.md"
    md_path.write_text(md)

    run.report_path = str(json_path)
    db.commit()
