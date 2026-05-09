import json
import re
from pathlib import Path
from typing import Optional


def _bump_patch(version: str) -> str:
    try:
        parts = version.strip().lstrip("v").split(".")
        parts = [p for p in parts if p.isdigit()]
        if len(parts) == 3:
            parts[2] = str(int(parts[2]) + 1)
            return ".".join(parts)
        elif len(parts) == 2:
            return f"{parts[0]}.{parts[1]}.1"
        elif len(parts) == 1:
            return f"{parts[0]}.0.1"
    except Exception:
        pass
    return "0.1.1"


def get_version_from_package_json(path: Path) -> Optional[str]:
    try:
        data = json.loads((path / "package.json").read_text())
        return data.get("version")
    except Exception:
        return None


def get_version_from_pyproject(path: Path) -> Optional[str]:
    try:
        import toml
        data = toml.loads((path / "pyproject.toml").read_text())
        return (
            data.get("project", {}).get("version")
            or data.get("tool", {}).get("poetry", {}).get("version")
        )
    except Exception:
        return None


def get_version_from_file(path: Path) -> Optional[str]:
    for fname in ["VERSION", "version.txt", "VERSION.txt"]:
        fp = path / fname
        if fp.exists():
            try:
                return fp.read_text().strip()
            except Exception:
                pass
    return None


def get_current_version(product_path: str) -> str:
    path = Path(product_path)
    return (
        get_version_from_package_json(path)
        or get_version_from_pyproject(path)
        or get_version_from_file(path)
        or ""
    )


def update_version_files(product_path: str, old_version: str, new_version: str) -> list:
    path = Path(product_path)
    updated = []

    pkg = path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            if "version" in data:
                data["version"] = new_version
                pkg.write_text(json.dumps(data, indent=2) + "\n")
                updated.append("package.json")
        except Exception:
            pass

    pyp = path / "pyproject.toml"
    if pyp.exists():
        try:
            content = pyp.read_text()
            new_content = re.sub(
                r'(version\s*=\s*["\'])' + re.escape(old_version) + r'(["\'])',
                rf'\g<1>{new_version}\g<2>',
                content
            )
            if new_content != content:
                pyp.write_text(new_content)
                updated.append("pyproject.toml")
        except Exception:
            pass

    for fname in ["VERSION", "version.txt", "VERSION.txt"]:
        fp = path / fname
        if fp.exists():
            try:
                fp.write_text(new_version + "\n")
                updated.append(fname)
            except Exception:
                pass

    return updated


def bump_version(product_path: str) -> tuple[str, str]:
    """Returns (old_version, new_version)."""
    old = get_current_version(product_path)
    if not old:
        new = "0.1.0"
    else:
        new = _bump_patch(old)

    update_version_files(product_path, old, new)
    return old, new
