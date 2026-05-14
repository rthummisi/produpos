"""
Startup Guardian — runs automatically on every ProdupOS launch.

Responsibilities:
1. Scan for new product folders not yet in the DB
2. Sanitize versions: align version file with latest git tag
3. Create CHANGELOG.md if missing
4. Commit + push sanitization changes to each product repo
5. Write a guardian report to data/guardian/
"""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .config import settings
from .models import Product, Setting
from .repo_scanner import scan_projects
from .db import SessionLocal
import uuid


# ─── Version helpers ─────────────────────────────────────────────────────────

def _get_latest_tag(path: str) -> Optional[str]:
    try:
        r = subprocess.run(
            ["git", "tag", "--sort=-version:refname"],
            cwd=path, capture_output=True, text=True, timeout=10
        )
        tags = [t.strip() for t in r.stdout.splitlines() if t.strip()]
        return tags[0] if tags else None
    except Exception:
        return None


def _read_version_file(path: str) -> Tuple[str, str]:
    """Returns (version, source_file)."""
    p = Path(path)
    pkg = p / "package.json"
    if pkg.exists():
        try:
            d = json.loads(pkg.read_text())
            v = d.get("version", "")
            if v:
                return v, "package.json"
        except Exception:
            pass
    pyp = p / "pyproject.toml"
    if pyp.exists():
        try:
            m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', pyp.read_text())
            if m:
                return m.group(1), "pyproject.toml"
        except Exception:
            pass
    for fname in ["VERSION", "version.txt"]:
        fp = p / fname
        if fp.exists():
            v = fp.read_text().strip()
            if v:
                return v, fname
    return "", ""


def _write_version_to_files(path: str, version: str):
    p = Path(path)
    written = []
    pkg = p / "package.json"
    if pkg.exists():
        try:
            d = json.loads(pkg.read_text())
            if "version" in d or True:
                d["version"] = version
                pkg.write_text(json.dumps(d, indent=2) + "\n")
                written.append("package.json")
        except Exception:
            pass
    pyp = p / "pyproject.toml"
    if pyp.exists():
        try:
            content = pyp.read_text()
            new = re.sub(
                r'(version\s*=\s*["\'])([^"\']+)(["\'])',
                rf'\g<1>{version}\g<3>',
                content
            )
            if new != content:
                pyp.write_text(new)
                written.append("pyproject.toml")
        except Exception:
            pass
    for fname in ["VERSION", "version.txt"]:
        fp = p / fname
        if fp.exists():
            fp.write_text(version + "\n")
            written.append(fname)
    if not written:
        (p / "VERSION").write_text(version + "\n")
        written.append("VERSION")
    return written


def _compare_versions(a: str, b: str) -> int:
    """Returns -1 if a < b, 0 if equal, 1 if a > b."""
    try:
        from packaging.version import Version
        va, vb = Version(a), Version(b)
        if va < vb:
            return -1
        if va > vb:
            return 1
        return 0
    except Exception:
        return 0 if a == b else (1 if a > b else -1)


def _git(args: List[str], cwd: str) -> Tuple[bool, str]:
    try:
        r = subprocess.run(
            ["git"] + args, cwd=cwd,
            capture_output=True, text=True, timeout=30
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


def _push(path: str, branch: str):
    ok, msg = _git(["remote"], path)
    if not ok or not msg.strip():
        return False, "no remote"
    ok, msg = _git(["push", "origin", branch, "--tags"], path)
    return ok, msg


def _commit_dirty_repo(path: str) -> Tuple[bool, str]:
    ok, status = _git(["status", "--porcelain"], path)
    if not ok or not status.strip():
        return True, ""
    _git(["add", "-A"], path)
    ok, msg = _git(["commit", "-m", "chore(guardian): auto-clean dirty repo on startup"], path)
    if not ok:
        return False, msg
    ok_sha, sha = _git(["rev-parse", "--short", "HEAD"], path)
    return ok_sha, sha if ok_sha else ""


# ─── CHANGELOG helper ────────────────────────────────────────────────────────

def _ensure_changelog(path: str, product_name: str, version: str) -> bool:
    cl = Path(path) / "CHANGELOG.md"
    if cl.exists():
        return False
    date = datetime.utcnow().strftime("%Y-%m-%d")
    cl.write_text(
        f"# Changelog — {product_name}\n\n"
        "All notable changes are documented here.  \n"
        "Versioning follows [Semantic Versioning](https://semver.org): MAJOR.MINOR.PATCH.\n\n---\n\n"
        f"## [{version}] — {date}\n\n"
        "### Current Release\n"
        "- Added to ProdupOS guardian tracking.\n\n"
        "---\n\n_Maintained by ProdupOS guardian_\n"
    )
    return True


# ─── Per-product sanitization ────────────────────────────────────────────────

def sanitize_product(path: str, name: str) -> Dict:
    result = {
        "product": name,
        "path": path,
        "version_before": "",
        "version_after": "",
        "tag": "",
        "action": "ok",
        "changelog_created": False,
        "committed": False,
        "pushed": False,
        "dirty_repo_cleaned": False,
        "message": "",
    }

    is_git = (Path(path) / ".git").exists()
    if is_git:
        cleaned, dirty_msg = _commit_dirty_repo(path)
        if dirty_msg:
            result["dirty_repo_cleaned"] = cleaned
            if cleaned:
                result["message"] = f"Dirty repo auto-cleaned in commit {dirty_msg}"
            else:
                result["message"] = f"Dirty repo cleanup failed: {dirty_msg}"

    file_ver, ver_source = _read_version_file(path)
    tag = _get_latest_tag(path) if is_git else None
    tag_ver = tag.lstrip("v") if tag else ""

    result["version_before"] = file_ver
    result["tag"] = tag or ""

    changed_files = []

    # ── Determine correct version ─────────────────────────────────────────
    if not file_ver and not tag_ver:
        # Nothing — establish 0.1.0
        written = _write_version_to_files(path, "0.1.0")
        changed_files.extend(written)
        result["version_after"] = "0.1.0"
        result["action"] = "version_created"
        result["message"] = f"No version found — initialised to 0.1.0 ({', '.join(written)})"

    elif not file_ver and tag_ver:
        # Tag exists, file missing — sync file from tag
        written = _write_version_to_files(path, tag_ver)
        changed_files.extend(written)
        result["version_after"] = tag_ver
        result["action"] = "synced_from_tag"
        result["message"] = f"Version file missing — synced {tag_ver} from tag {tag}"

    elif file_ver and not tag_ver:
        # File exists, no tag — create tag (no file change)
        result["version_after"] = file_ver
        result["action"] = "tag_created"
        result["message"] = f"No git tag — will tag HEAD as v{file_ver}"
        if is_git:
            ok, msg = _git(
                ["tag", "-a", f"v{file_ver}", "-m", f"Release v{file_ver} (auto-tagged by ProdupOS guardian)"],
                path
            )
            if not ok:
                result["action"] = "tag_failed"
                result["message"] = f"Could not create tag v{file_ver}: {msg}"

    elif file_ver and tag_ver and file_ver != tag_ver:
        cmp = _compare_versions(file_ver, tag_ver)
        if cmp < 0:
            # Tag is ahead of file — sync file up
            written = _write_version_to_files(path, tag_ver)
            changed_files.extend(written)
            result["version_after"] = tag_ver
            result["action"] = "synced_from_tag"
            result["message"] = f"Version file {file_ver} behind tag {tag} — synced to {tag_ver}"
        else:
            # File is ahead of tag — create new tag
            result["version_after"] = file_ver
            result["action"] = "tag_created"
            result["message"] = f"Tag {tag} behind version file {file_ver} — tagged HEAD as v{file_ver}"
            if is_git:
                ok, msg = _git(
                    ["tag", "-a", f"v{file_ver}", "-m", f"Release v{file_ver} (auto-tagged by ProdupOS guardian)"],
                    path
                )
                if not ok and "already exists" not in msg:
                    result["action"] = "tag_failed"
                    result["message"] += f" — tag failed: {msg}"
    else:
        result["version_after"] = file_ver
        result["action"] = "ok"
        result["message"] = f"v{file_ver} ✓"

    # ── CHANGELOG ──────────────────────────────────────────────────────────
    ver_for_cl = result["version_after"] or file_ver or "0.1.0"
    created = _ensure_changelog(path, name, ver_for_cl)
    result["changelog_created"] = created
    if created:
        changed_files.append("CHANGELOG.md")

    # ── Commit + push any file changes ─────────────────────────────────────
    if changed_files and is_git:
        ok_branch, branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], path)
        branch = branch.strip() if ok_branch else "main"

        # Check if there's anything to commit
        _git(["add"] + changed_files, path)
        ok_st, st = _git(["diff", "--cached", "--name-only"], path)
        if ok_st and st.strip():
            commit_msg = (
                f"chore(guardian): sanitize version to {result['version_after']}"
                + (" + add CHANGELOG.md" if created else "")
                + "\n\nAuto-committed by ProdupOS startup guardian."
            )
            ok_c, c_msg = _git(["commit", "-m", commit_msg], path)
            result["committed"] = ok_c
            if ok_c:
                ok_p, p_msg = _push(path, branch)
                result["pushed"] = ok_p
        else:
            # Only tag was created — push tags
            if result["action"] in ("tag_created",):
                ok_p, _ = _push(path, branch)
                result["pushed"] = ok_p

    elif result["action"] == "tag_created" and is_git:
        ok_branch, branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], path)
        branch = branch.strip() if ok_branch else "main"
        ok_p, _ = _push(path, branch)
        result["pushed"] = ok_p

    return result


# ─── DB upsert for new products ──────────────────────────────────────────────

def _upsert_products(db: Session, scanned: List[Dict]):
    from .version_manager import get_current_version as _gv
    from .safety import get_git_status
    now = datetime.utcnow()
    added = []
    for rp in scanned:
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, rp["path"]))
        existing = db.query(Product).filter(Product.id == pid).first()
        live_ver = _gv(rp["path"]) or ""
        git_str = rp.get("repo_status", "unknown")
        if not existing:
            p = Product(
                id=pid,
                name=rp["product_name"],
                path=rp["path"],
                detected_stack=rp.get("detected_stack", ""),
                updatable=rp.get("updatable", False),
                skip_reason=rp.get("skip_reason", ""),
                git_status=git_str,
                code_confidence_score=rp.get("code_confidence_score", 0.0),
                current_version=live_ver,
                updated_at=now,
            )
            db.add(p)
            added.append(rp["product_name"])
        else:
            existing.detected_stack = rp.get("detected_stack", "") or existing.detected_stack
            existing.updatable = rp.get("updatable", False)
            existing.skip_reason = rp.get("skip_reason", "")
            existing.git_status = git_str
            existing.code_confidence_score = rp.get("code_confidence_score", 0.0)
            existing.current_version = live_ver
            existing.updated_at = now
    db.commit()
    return added


# ─── Main guardian entry point ───────────────────────────────────────────────

def run_startup_guardian() -> Dict:
    db: Session = SessionLocal()
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "new_products": [],
        "sanitization": [],
        "errors": [],
        "summary": {},
    }

    try:
        roots = settings.get_all_roots()
        scanned = scan_projects(roots)

        # Upsert and detect new products
        new = _upsert_products(db, scanned)
        report["new_products"] = new

        # Always sanitize ProdupOS itself first
        self_path = settings.get_produpOS_root()
        try:
            self_result = sanitize_product(str(self_path), "ProdupOS")
            self_result["is_self"] = True
            report["sanitization"].insert(0, self_result)
        except Exception as e:
            report["errors"].append({"product": "ProdupOS", "error": str(e)})

        # Sanitize versions for all updatable products
        for rp in scanned:
            if not rp.get("updatable"):
                continue
            try:
                s = sanitize_product(rp["path"], rp["product_name"])
                report["sanitization"].append(s)
            except Exception as e:
                report["errors"].append({"product": rp["product_name"], "error": str(e)})

        # Summary
        actions = [s["action"] for s in report["sanitization"]]
        report["summary"] = {
            "total_scanned": len(scanned),
            "new_detected": len(new),
            "versions_ok": actions.count("ok"),
            "versions_synced": actions.count("synced_from_tag"),
            "versions_created": actions.count("version_created"),
            "tags_created": actions.count("tag_created"),
            "changelogs_created": sum(1 for s in report["sanitization"] if s.get("changelog_created")),
            "committed": sum(1 for s in report["sanitization"] if s.get("committed")),
            "pushed": sum(1 for s in report["sanitization"] if s.get("pushed")),
            "errors": len(report["errors"]),
        }

        # Persist report to disk
        guardian_dir = Path(settings.data_dir) / "guardian"
        guardian_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        report_path = guardian_dir / f"guardian-{ts}.json"
        report_path.write_text(json.dumps(report, indent=2))

        # Store latest path in settings table
        latest = db.query(Setting).filter(Setting.key == "guardian_latest_report").first()
        if latest:
            latest.value = str(report_path)
        else:
            db.add(Setting(key="guardian_latest_report", value=str(report_path)))
        db.commit()

    except Exception as e:
        report["errors"].append({"product": "guardian", "error": str(e)})
    finally:
        db.close()

    return report
