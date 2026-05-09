import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from .config import NEVER_TOUCH_PATTERNS, settings


def is_never_touch(path: str) -> bool:
    p = Path(path)
    name = p.name
    for pattern in NEVER_TOUCH_PATTERNS:
        if pattern.startswith("*."):
            if name.endswith(pattern[1:]):
                return True
        elif name == pattern or str(p).endswith(pattern):
            return True
    return False


def get_git_status(product_path: str) -> Dict:
    path = Path(product_path)
    if not (path / ".git").exists():
        return {"is_git": False, "dirty": False, "branch": None, "status": "not a git repo"}
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=product_path, capture_output=True, text=True, timeout=10
        )
        dirty = bool(result.stdout.strip())
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=product_path, capture_output=True, text=True, timeout=10
        )
        branch = branch_result.stdout.strip()
        return {
            "is_git": True,
            "dirty": dirty,
            "branch": branch,
            "status": "dirty" if dirty else "clean",
            "untracked": [l[3:] for l in result.stdout.splitlines() if l.startswith("?? ")],
            "modified": [l[3:] for l in result.stdout.splitlines() if not l.startswith("?? ")],
        }
    except Exception as e:
        return {"is_git": True, "dirty": False, "branch": None, "status": f"error: {e}"}


def create_snapshot(product_path: str, file_changes: List[Dict]) -> Dict:
    """Read current content of all files about to be changed and return snapshot."""
    snapshot = {}
    for change in file_changes:
        fpath = Path(product_path) / change["path"]
        if fpath.exists():
            try:
                snapshot[change["path"]] = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                snapshot[change["path"]] = None
        else:
            snapshot[change["path"]] = None
    return snapshot


def restore_snapshot(product_path: str, snapshot: Dict) -> List[str]:
    """Restore files to their pre-implementation state."""
    restored = []
    errors = []
    for rel_path, content in snapshot.items():
        fpath = Path(product_path) / rel_path
        try:
            if content is None:
                if fpath.exists():
                    fpath.unlink()
                    restored.append(f"deleted (restored): {rel_path}")
            else:
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(content, encoding="utf-8")
                restored.append(f"restored: {rel_path}")
        except Exception as e:
            errors.append(f"failed to restore {rel_path}: {e}")
    return restored + errors


def check_per_product_exclusions(product_path: str, file_path: str, exclusions: str) -> bool:
    """Returns True if file_path matches any per-product exclusion pattern."""
    if not exclusions:
        return False
    patterns = [p.strip() for p in exclusions.split(",") if p.strip()]
    p = Path(file_path)
    for pattern in patterns:
        if pattern in str(p) or p.name == pattern:
            return True
    return False


def pre_run_safety_check(product_path: str, git_info: Dict, require_approval: bool) -> Dict:
    result = {
        "ok": True,
        "warnings": [],
        "blockers": [],
    }
    if not Path(product_path).exists():
        result["ok"] = False
        result["blockers"].append("Product path does not exist")
        return result

    if git_info.get("dirty"):
        result["warnings"].append(
            "Repository has uncommitted changes. Proceeding may mix user work with generated changes."
        )
        if require_approval:
            result["ok"] = False
            result["blockers"].append(
                "Repo is dirty. User must choose: skip, commit existing work first, or override safety."
            )

    return result
