import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from .models import ScheduledRun
from .db import SessionLocal


def _compute_next_run(schedule_type: str, schedule_value: str, from_dt: Optional[datetime] = None) -> datetime:
    now = from_dt or datetime.utcnow()
    if schedule_type == "interval":
        try:
            hours = float(schedule_value)
        except ValueError:
            hours = 24.0
        return now + timedelta(hours=hours)
    elif schedule_type == "daily":
        try:
            h, m = schedule_value.split(":")
            next_dt = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
            if next_dt <= now:
                next_dt += timedelta(days=1)
            return next_dt
        except Exception:
            return now + timedelta(days=1)
    elif schedule_type == "weekly":
        return now + timedelta(weeks=1)
    return now + timedelta(hours=24)


async def scheduler_loop():
    """Background task that checks for scheduled runs every 60 seconds."""
    while True:
        try:
            db: Session = SessionLocal()
            try:
                now = datetime.utcnow()
                schedules = db.query(ScheduledRun).filter(
                    ScheduledRun.enabled == True,
                    ScheduledRun.next_run <= now,
                ).all()

                for schedule in schedules:
                    from .agent_orchestrator import run_products
                    run_id = await run_products(
                        db, None,
                        dry_run=schedule.dry_run,
                    )
                    schedule.last_run = now
                    schedule.last_run_id = run_id
                    schedule.next_run = _compute_next_run(
                        schedule.schedule_type, schedule.schedule_value, now
                    )
                    db.commit()
            finally:
                db.close()
        except Exception:
            pass

        await asyncio.sleep(60)


def create_schedule(
    db: Session,
    name: str,
    schedule_type: str,
    schedule_value: str,
    mode: str = "auto",
    dry_run: bool = True,
) -> ScheduledRun:
    s = ScheduledRun(
        id=str(uuid.uuid4()),
        name=name,
        schedule_type=schedule_type,
        schedule_value=schedule_value,
        mode=mode,
        dry_run=dry_run,
        enabled=True,
        next_run=_compute_next_run(schedule_type, schedule_value),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s
