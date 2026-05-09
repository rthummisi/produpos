import subprocess
from pathlib import Path
from typing import Dict
from datetime import datetime
from .config import SKIP_DIRS


def _count_todos(product_path: str) -> int:
    count = 0
    try:
        result = subprocess.run(
            ["grep", "-r", "--include=*.py", "--include=*.js", "--include=*.ts",
             "--include=*.jsx", "--include=*.tsx", "-i", r"TODO\|FIXME\|HACK\|XXX",
             "--count", "."],
            cwd=product_path, capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            try:
                count += int(line.split(":")[-1])
            except ValueError:
                pass
    except Exception:
        pass
    return count


def _has_tests(product_path: str) -> bool:
    path = Path(product_path)
    test_indicators = ["tests", "test", "__tests__", "spec", "cypress", "jest.config.js",
                       "pytest.ini", "conftest.py", "vitest.config.js"]
    for indicator in test_indicators:
        if (path / indicator).exists():
            return True
    return False


def _has_ci(product_path: str) -> bool:
    path = Path(product_path)
    ci_paths = [
        ".github/workflows", ".gitlab-ci.yml", ".circleci/config.yml",
        "Jenkinsfile", ".travis.yml", "azure-pipelines.yml"
    ]
    for ci in ci_paths:
        if (path / ci).exists():
            return True
    return False


def _last_commit_days(product_path: str) -> int | None:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            cwd=product_path, capture_output=True, text=True, timeout=10
        )
        ts = result.stdout.strip()
        if ts:
            import time
            days = (time.time() - int(ts)) / 86400
            return int(days)
    except Exception:
        pass
    return None


def _doc_quality(product_path: str) -> str:
    path = Path(product_path)
    readme = path / "README.md"
    if not readme.exists():
        return "none"
    try:
        content = readme.read_text()
        if len(content) > 2000:
            return "good"
        elif len(content) > 500:
            return "basic"
        else:
            return "minimal"
    except Exception:
        return "none"


def calculate_health_score(product_path: str, git_status: Dict, dependency_report: Dict) -> Dict:
    has_tests = _has_tests(product_path)
    has_readme = (Path(product_path) / "README.md").exists()
    has_changelog = any(
        (Path(product_path) / f).exists()
        for f in ["CHANGELOG.md", "CHANGELOG", "HISTORY.md", "RELEASES.md"]
    )
    has_ci = _has_ci(product_path)
    last_commit = _last_commit_days(product_path)
    todo_count = _count_todos(product_path)
    doc_quality = _doc_quality(product_path)

    dep_outdated = dependency_report.get("outdated", 0)
    dep_total = dependency_report.get("total", 0)
    dep_health = "unknown"
    if dep_total > 0:
        pct = dep_outdated / dep_total
        dep_health = "good" if pct < 0.1 else ("fair" if pct < 0.3 else "poor")

    score = 0.0
    if has_tests:
        score += 0.25
    if has_readme:
        score += 0.15
    if has_changelog:
        score += 0.10
    if has_ci:
        score += 0.15
    if git_status.get("is_git"):
        score += 0.10
    if not git_status.get("dirty"):
        score += 0.05
    if last_commit is not None and last_commit < 30:
        score += 0.10
    if todo_count < 10:
        score += 0.05
    if doc_quality in ("good", "basic"):
        score += 0.05

    details = {
        "has_tests": has_tests,
        "has_readme": has_readme,
        "has_changelog": has_changelog,
        "has_ci": has_ci,
        "last_commit_days_ago": last_commit,
        "todo_count": todo_count,
        "doc_quality": doc_quality,
        "test_coverage_estimate": "present" if has_tests else "absent",
        "dependency_health": dep_health,
    }

    return {"score": round(min(score, 1.0), 3), "details": details}
