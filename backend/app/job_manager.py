import asyncio
from typing import Dict, List, Callable, Any
from datetime import datetime

# In-memory log store for active jobs
_job_logs: Dict[str, List[str]] = {}
_job_callbacks: Dict[str, List[Callable]] = {}


def init_job_log(job_id: str):
    _job_logs[job_id] = []
    _job_callbacks[job_id] = []


def append_log(job_id: str, message: str):
    ts = datetime.utcnow().strftime("%H:%M:%S")
    entry = f"[{ts}] {message}"
    if job_id not in _job_logs:
        _job_logs[job_id] = []
    _job_logs[job_id].append(entry)

    for cb in _job_callbacks.get(job_id, []):
        try:
            cb(entry)
        except Exception:
            pass


def get_logs(job_id: str) -> List[str]:
    return _job_logs.get(job_id, [])


def subscribe(job_id: str, callback: Callable):
    if job_id not in _job_callbacks:
        _job_callbacks[job_id] = []
    _job_callbacks[job_id].append(callback)


def unsubscribe(job_id: str, callback: Callable):
    cbs = _job_callbacks.get(job_id, [])
    if callback in cbs:
        cbs.remove(callback)


def cleanup_job(job_id: str):
    _job_logs.pop(job_id, None)
    _job_callbacks.pop(job_id, None)
