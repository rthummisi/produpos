import json
import subprocess
from pathlib import Path
from typing import Dict, List
from datetime import datetime

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


def _check_pypi_version(package: str) -> str:
    if not HAS_HTTPX:
        return ""
    try:
        resp = httpx.get(f"https://pypi.org/pypi/{package}/json", timeout=5)
        if resp.status_code == 200:
            return resp.json()["info"]["version"]
    except Exception:
        pass
    return ""


def _check_npm_version(package: str) -> str:
    if not HAS_HTTPX:
        return ""
    try:
        resp = httpx.get(f"https://registry.npmjs.org/{package}/latest", timeout=5)
        if resp.status_code == 200:
            return resp.json().get("version", "")
    except Exception:
        pass
    return ""


def check_python_deps(product_path: str) -> Dict:
    path = Path(product_path)
    packages = []

    req_files = []
    if (path / "requirements.txt").exists():
        req_files.append(path / "requirements.txt")
    if (path / "requirements-dev.txt").exists():
        req_files.append(path / "requirements-dev.txt")

    raw_deps = []
    for rf in req_files:
        try:
            for line in rf.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    raw_deps.append(line)
        except Exception:
            pass

    if (path / "pyproject.toml").exists():
        try:
            import toml
            data = toml.loads((path / "pyproject.toml").read_text())
            deps = data.get("project", {}).get("dependencies", [])
            raw_deps.extend(deps)
        except Exception:
            pass

    outdated = 0
    for dep in raw_deps[:15]:  # limit API calls
        name = dep.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip()
        current = ""
        if "==" in dep:
            current = dep.split("==")[1].split(";")[0].strip()
        latest = _check_pypi_version(name)
        is_outdated = bool(latest and current and latest != current)
        if is_outdated:
            outdated += 1
        packages.append({
            "name": name,
            "current_version": current or "unknown",
            "latest_version": latest or "unknown",
            "outdated": is_outdated,
            "security_advisory": False,
        })

    return {
        "ecosystem": "pip",
        "total": len(packages),
        "outdated": outdated,
        "secure": True,
        "packages": packages,
        "checked_at": datetime.utcnow().isoformat(),
    }


def check_node_deps(product_path: str) -> Dict:
    path = Path(product_path)
    pkg_json = path / "package.json"
    if not pkg_json.exists():
        return {"ecosystem": "npm", "total": 0, "outdated": 0, "secure": True, "packages": [], "checked_at": ""}

    try:
        data = json.loads(pkg_json.read_text())
    except Exception:
        return {"ecosystem": "npm", "total": 0, "outdated": 0, "secure": True, "packages": [], "checked_at": ""}

    all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    packages = []
    outdated = 0

    for name, version_spec in list(all_deps.items())[:15]:
        current = version_spec.lstrip("^~>=")
        latest = _check_npm_version(name)
        is_outdated = bool(latest and current and latest != current)
        if is_outdated:
            outdated += 1
        packages.append({
            "name": name,
            "current_version": current or "unknown",
            "latest_version": latest or "unknown",
            "outdated": is_outdated,
            "security_advisory": False,
        })

    return {
        "ecosystem": "npm",
        "total": len(packages),
        "outdated": outdated,
        "secure": True,
        "packages": packages,
        "checked_at": datetime.utcnow().isoformat(),
    }


def check_dependencies(product_path: str, detected_stack: str) -> Dict:
    stack = detected_stack.lower()
    if "python" in stack or "fastapi" in stack or "django" in stack or "flask" in stack:
        return check_python_deps(product_path)
    elif "node" in stack or "react" in stack or "next" in stack or "vite" in stack or "vue" in stack:
        return check_node_deps(product_path)
    elif "full" in stack:
        py = check_python_deps(product_path)
        npm = check_node_deps(product_path)
        if npm["total"] > 0:
            return npm
        return py
    return {"ecosystem": "unknown", "total": 0, "outdated": 0, "secure": True, "packages": [], "checked_at": ""}
