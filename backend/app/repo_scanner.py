import os
from pathlib import Path
from typing import List, Dict
from .config import settings, SKIP_DIRS, PRODUCT_INDICATORS, PRODUCT_DIRS
from .safety import get_git_status


def _get_top_level_items(path: Path) -> Dict:
    try:
        items = list(path.iterdir())
    except PermissionError:
        return {"files": [], "dirs": []}
    files = [i.name for i in items if i.is_file()]
    dirs = [i.name for i in items if i.is_dir() and i.name not in SKIP_DIRS]
    return {"files": files, "dirs": dirs}


def detect_stack(path: Path) -> str:
    items = _get_top_level_items(path)
    files = set(items["files"])
    dirs = set(items["dirs"])
    stacks = []

    if "next.config.js" in files or "next.config.ts" in files:
        stacks.append("Next.js")
    if "vite.config.js" in files or "vite.config.ts" in files:
        stacks.append("Vite/React")
    if "package.json" in files:
        try:
            import json
            pkg = json.loads((path / "package.json").read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "react" in deps:
                if "Vite/React" not in stacks and "Next.js" not in stacks:
                    stacks.append("React")
            if "vue" in deps:
                stacks.append("Vue")
            if "svelte" in deps:
                stacks.append("Svelte")
            if "express" in deps or "fastify" in deps or "koa" in deps:
                stacks.append("Node API")
        except Exception:
            stacks.append("Node")

    if "pyproject.toml" in files or "setup.py" in files:
        try:
            content = ""
            if (path / "pyproject.toml").exists():
                content = (path / "pyproject.toml").read_text()
            if "fastapi" in content.lower():
                stacks.append("FastAPI")
            elif "django" in content.lower():
                stacks.append("Django")
            elif "flask" in content.lower():
                stacks.append("Flask")
            else:
                stacks.append("Python")
        except Exception:
            stacks.append("Python")
    elif "requirements.txt" in files:
        try:
            content = (path / "requirements.txt").read_text().lower()
            if "fastapi" in content:
                stacks.append("FastAPI")
            elif "django" in content:
                stacks.append("Django")
            elif "flask" in content:
                stacks.append("Flask")
            else:
                stacks.append("Python")
        except Exception:
            stacks.append("Python")

    if "Dockerfile" in files or "docker-compose.yml" in files or "docker-compose.yaml" in files:
        stacks.append("Docker")

    if "go.mod" in files:
        stacks.append("Go")
    if "Cargo.toml" in files:
        stacks.append("Rust")
    if "pom.xml" in files or "build.gradle" in files:
        stacks.append("Java/JVM")

    if "backend" in dirs and "frontend" in dirs:
        stacks.append("Full-Stack")

    if not stacks:
        return "Unknown"
    return " + ".join(dict.fromkeys(stacks))


def calculate_confidence_score(path: Path) -> float:
    items = _get_top_level_items(path)
    files = set(items["files"])
    dirs = set(items["dirs"])

    score = 0.0
    for indicator in PRODUCT_INDICATORS:
        if indicator in files:
            score += 0.15
    for d in PRODUCT_DIRS:
        if d in dirs:
            score += 0.1

    if (path / ".git").exists():
        score += 0.2

    all_files = sum(1 for _ in path.rglob("*") if _.is_file() and not any(s in str(_) for s in SKIP_DIRS))
    if all_files > 20:
        score += 0.2
    elif all_files > 5:
        score += 0.1

    return min(score, 1.0)


def is_docs_only(path: Path) -> bool:
    doc_exts = {".md", ".txt", ".pdf", ".docx", ".pptx", ".png", ".jpg", ".jpeg", ".svg", ".gif"}
    items = _get_top_level_items(path)
    all_files = items["files"]
    if not all_files and not items["dirs"]:
        return True
    non_doc = [f for f in all_files if Path(f).suffix.lower() not in doc_exts]
    return len(non_doc) == 0 and len(items["dirs"]) == 0


ASSET_DIRS = {"logos", "logo", "assets", "images", "icons", "fonts", "media", "static", "public", "docs"}


def classify_product(path: Path, name: str, skip_persistent: bool = False) -> Dict:
    result = {
        "product_name": name,
        "path": str(path),
        "detected_stack": "",
        "repo_status": "unknown",
        "code_confidence_score": 0.0,
        "updatable": False,
        "skip_reason": "",
        "git_status": {},
    }

    if skip_persistent:
        result["skip_reason"] = "Persistently skipped by user"
        return result

    items = _get_top_level_items(path)
    files = items["files"]
    dirs = items["dirs"]

    if not files and not dirs:
        result["skip_reason"] = "Empty folder"
        return result

    if is_docs_only(path):
        result["skip_reason"] = "Documentation/assets only — no product code"
        return result

    # Check if top-level has no code indicators (only asset dirs + doc files)
    has_indicators = any(f in files for f in PRODUCT_INDICATORS)
    has_code_dirs = any(d in dirs for d in PRODUCT_DIRS)
    has_git = (path / ".git").exists()
    non_asset_dirs = [d for d in dirs if d.lower() not in ASSET_DIRS]

    # If no indicators at top level and non-asset subdirs are not code dirs, skip
    if not has_indicators and not has_code_dirs and not has_git:
        if not non_asset_dirs:
            result["skip_reason"] = "Documentation/assets only — no product code"
            return result
        # All subdirs are nested products (like a monorepo wrapper without code at root)
        result["skip_reason"] = "No recognizable product structure at root — may be a wrapper folder"
        return result

    confidence = calculate_confidence_score(path)
    result["code_confidence_score"] = confidence
    result["detected_stack"] = detect_stack(path)

    git_info = get_git_status(str(path))
    result["git_status"] = git_info
    result["repo_status"] = git_info.get("status", "unknown")
    result["updatable"] = True
    return result


def _has_product_structure(path: Path) -> bool:
    """Quick check: does this dir have any product indicators at its root?"""
    items = _get_top_level_items(path)
    files = set(items["files"])
    dirs = set(items["dirs"])
    return (
        any(f in files for f in PRODUCT_INDICATORS)
        or any(d in dirs for d in PRODUCT_DIRS)
        or (path / ".git").exists()
    )


def _find_nested_products(wrapper: Path, seen_paths: set, self_name: str) -> List[Dict]:
    """When a top-level folder has no product structure, look one level deeper."""
    nested = []
    try:
        for subdir in sorted(wrapper.iterdir()):
            if not subdir.is_dir():
                continue
            if subdir.name.startswith("."):
                continue
            if subdir.name in SKIP_DIRS:
                continue
            if subdir.name.lower() in {self_name.lower(), "produpos", "produps"}:
                continue
            if str(subdir) in seen_paths:
                continue
            if _has_product_structure(subdir):
                seen_paths.add(str(subdir))
                product = classify_product(subdir, subdir.name)
                nested.append(product)
    except PermissionError:
        pass
    return nested


def scan_projects(roots: List[Path], self_name: str = "ProdUPOS") -> List[Dict]:
    products = []
    seen_paths = set()

    for root in roots:
        if not root.exists():
            continue
        try:
            entries = sorted(root.iterdir())
        except PermissionError:
            continue

        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue
            if entry.name in SKIP_DIRS:
                continue
            if entry.name.lower() in {self_name.lower(), "produpos", "produps"}:
                continue
            if str(entry) in seen_paths:
                continue
            seen_paths.add(str(entry))

            product = classify_product(entry, entry.name)

            if not product["updatable"] and "wrapper" in product.get("skip_reason", "").lower():
                # This is a wrapper folder — search one level deeper for real products
                nested = _find_nested_products(entry, seen_paths, self_name)
                if nested:
                    products.extend(nested)
                    continue  # don't add the wrapper itself

            products.append(product)

    return products
