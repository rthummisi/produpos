import json
import difflib
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .config import settings, SKIP_DIRS
from .ai_clients import call_tool_with_fallback, call_json_with_fallback
from .schemas import FeatureProposal, FileChange
from .safety import is_never_touch, check_per_product_exclusions


def _read_repo_files(product_path: str, max_files: int = 20, max_chars: int = 40000) -> str:
    """Read key source files to give AI context about the repo."""
    path = Path(product_path)
    priority_files = ["README.md", "package.json", "pyproject.toml", "requirements.txt",
                      "main.py", "app.py", "server.py", "index.js", "index.ts",
                      "App.jsx", "App.tsx", "docker-compose.yml"]

    collected = []
    total_chars = 0

    for pf in priority_files:
        fp = path / pf
        if fp.exists():
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
                snippet = content[:3000]
                collected.append(f"=== {pf} ===\n{snippet}")
                total_chars += len(snippet)
                if total_chars > max_chars // 2:
                    break
            except Exception:
                pass

    count = 0
    for f in path.rglob("*"):
        if count >= max_files:
            break
        if not f.is_file():
            continue
        if any(s in str(f) for s in SKIP_DIRS):
            continue
        if f.name in [x.split("/")[-1] for x in priority_files]:
            continue
        if f.suffix not in {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".yaml", ".yml"}:
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            rel = str(f.relative_to(path))
            snippet = content[:2000]
            if total_chars + len(snippet) > max_chars:
                break
            collected.append(f"=== {rel} ===\n{snippet}")
            total_chars += len(snippet)
            count += 1
        except Exception:
            pass

    return "\n\n".join(collected)


def _list_repo_paths(product_path: str, max_files: int = 120) -> List[str]:
    path = Path(product_path)
    files = []
    for f in sorted(path.rglob("*")):
        if len(files) >= max_files:
            break
        if not f.is_file():
            continue
        if any(s in str(f) for s in SKIP_DIRS):
            continue
        if ".git" in f.parts:
            continue
        files.append(str(f.relative_to(path)))
    return files


def _validate_file_change(path: str, action: str, new_content: str, known_paths: set[str]) -> bool:
    if not path or path.startswith("/") or path in {"relative/path", "path/to/file"}:
        return False
    if ".." in Path(path).parts:
        return False
    if action not in {"create", "modify"}:
        return False
    if not new_content.strip():
        return False
    if "complete file contents" in new_content.lower():
        return False
    if action == "modify" and path not in known_paths:
        return False
    return True


def _build_file_changes(product_path: str, raw_changes: List[Dict]) -> List[FileChange]:
    known_paths = set(_list_repo_paths(product_path, max_files=500))
    if not raw_changes:
        raise RuntimeError("Model returned no file changes")
    changes = []
    for fc in raw_changes:
        path = fc["path"]
        action = fc["action"]
        new_content = fc["new_content"]
        if not _validate_file_change(path, action, new_content, known_paths):
            raise RuntimeError(f"Invalid file change returned for path '{path}'")
        old_content = None
        full_path = Path(product_path) / path
        if full_path.exists():
            try:
                old_content = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
        diff = generate_diff(path, old_content or "", new_content)
        changes.append(FileChange(
            path=path,
            action=action,
            old_content=old_content,
            new_content=new_content,
            diff=diff,
        ))
    if not changes:
        raise RuntimeError("Model returned no usable file changes")
    return changes


def generate_implementation_with_ai(
    product_name: str,
    product_path: str,
    detected_stack: str,
    proposal: FeatureProposal,
) -> Tuple[List[FileChange], str, int, str]:
    repo_context = _read_repo_files(product_path)
    repo_paths = _list_repo_paths(product_path)
    failure_reasons = []

    try:
        system = (
            "You are ProdupOS, an expert software engineer. "
            "Implement the given feature with minimal, production-quality changes. "
            "Preserve existing architecture. Do not break local startup. "
            "Never touch .env files or delete existing files. "
            "Return file changes using the submit_implementation tool. "
            "Each file must contain the complete new content (not just the diff)."
        )

        user_msg = f"""Implement this feature for {product_name} ({detected_stack}):

Feature: {proposal.feature_title}
Problem: {proposal.customer_problem}
Files likely to change: {', '.join(proposal.files_likely_to_change)}
Scope: {proposal.estimated_scope}

Current codebase:
{repo_context}

Existing repo file paths (use exact relative paths for modifications):
{chr(10).join(repo_paths[:120])}

Rules:
- Make minimal but real changes
- Preserve existing style and architecture
- Add UI if product has a frontend
- Add API if product has a backend
- Do not delete any existing files
- Never create or modify .env files
- Include complete file content in new_content
- Create new files if needed

Use the submit_implementation tool."""

        schema = {
            "type": "object",
            "properties": {
                "file_changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative path from product root"},
                            "action": {"type": "string", "enum": ["create", "modify"]},
                            "new_content": {"type": "string", "description": "Complete file content"},
                        },
                        "required": ["path", "action", "new_content"],
                    },
                    "minItems": 1,
                    "maxItems": 10,
                },
                "explanation": {"type": "string"},
            },
            "required": ["file_changes", "explanation"],
        }

        result = call_tool_with_fallback(
            system=system,
            user_message=user_msg,
            tool_name="submit_implementation",
            tool_description="Submit the implementation as file changes",
            input_schema=schema,
            max_tokens=settings.ai_max_tokens,
            timeout=settings.ai_timeout,
        )
        changes = _build_file_changes(product_path, result.tool_input["file_changes"])
        return changes, result.tool_input.get("explanation", ""), result.tokens, "ai"

    except Exception as e:
        failure_reasons.append(str(e))

    try:
        json_system = (
            "You are ProdupOS, an expert software engineer. "
            "Return strict JSON only. Implement the feature with minimal real code changes. "
            "Do not include markdown fences or commentary outside JSON."
        )
        json_user_msg = f"""Implement this feature for {product_name} ({detected_stack}).

Feature: {proposal.feature_title}
Problem: {proposal.customer_problem}
Files likely to change: {', '.join(proposal.files_likely_to_change)}
Scope: {proposal.estimated_scope}

Current codebase:
{repo_context}

Existing repo file paths (use exact relative paths for modifications):
{chr(10).join(repo_paths[:120])}

Return JSON with this exact shape:
{{
  "file_changes": [
    {{
      "path": "relative/path",
      "action": "create or modify",
      "new_content": "complete file contents"
    }}
  ],
  "explanation": "short explanation"
}}
"""
        json_schema = {
            "type": "object",
            "properties": {
                "file_changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "action": {"type": "string"},
                            "new_content": {"type": "string"},
                        },
                        "required": ["path", "action", "new_content"],
                    },
                },
                "explanation": {"type": "string"},
            },
            "required": ["file_changes", "explanation"],
        }
        result = call_json_with_fallback(
            system=json_system,
            user_message=json_user_msg,
            output_schema=json_schema,
            max_tokens=settings.ai_max_tokens,
            timeout=settings.ai_timeout,
            provider_order=["ollama", "kimi", "gemini", "anthropic", "groq"],
        )
        changes = _build_file_changes(product_path, result.tool_input["file_changes"])
        return changes, result.tool_input.get("explanation", ""), result.tokens, "ai"
    except Exception as e:
        failure_reasons.append(str(e))

    fallback_changes, fallback_kind = _generate_fallback_implementation(product_path, detected_stack, proposal)
    return fallback_changes, " | ".join(failure_reasons), 0, fallback_kind


def _generate_fallback_implementation(
    product_path: str,
    detected_stack: str,
    proposal: FeatureProposal,
) -> Tuple[List[FileChange], str]:
    """Generate a safe stack-aware scaffold when AI is unavailable."""
    path = Path(product_path)
    repo_paths = set(_list_repo_paths(product_path, max_files=500))
    slug = _slugify(proposal.feature_title)
    title = proposal.feature_title
    problem = proposal.customer_problem
    demo = proposal.demo_instructions
    why = proposal.why_this_matters

    changes = []

    frontend_root = _find_frontend_root(path)
    backend_root = _find_backend_root(path)

    if frontend_root:
        rel_root = frontend_root.relative_to(path)
        component_dir = _ensure_rel_dir(rel_root / "components")
        ext = _choose_frontend_ext(frontend_root)
        component_name = f"Produpos{_pascal_case(slug)}"
        component_path = str(component_dir / f"{component_name}.{ext}")
        component_content = _build_frontend_scaffold(component_name, title, problem, why, demo, ext)
        changes.append(_make_change(path, component_path, component_content))

    if backend_root:
        rel_root = backend_root.relative_to(path)
        backend_path, backend_content = _build_backend_scaffold(rel_root, backend_root, slug, title, problem, why, demo)
        changes.append(_make_change(path, backend_path, backend_content))

    if changes:
        return changes, "scaffold"

    content = f"""# {proposal.feature_title}

This feature was planned by ProdupOS in fallback mode (no AI API key).

## Customer Problem
{proposal.customer_problem}

## Why This Matters
{proposal.why_this_matters}

## Files To Update
{chr(10).join('- ' + f for f in proposal.files_likely_to_change)}

## Implementation Notes
AI implementation was not available. Please implement this feature manually.

## Demo Instructions
{proposal.demo_instructions}
"""
    old = None
    if (path / "PRODUCT_UPDATE.md").exists():
        old = (path / "PRODUCT_UPDATE.md").read_text()

    changes.append(FileChange(
        path="PRODUCT_UPDATE.md",
        action="create" if old is None else "modify",
        old_content=old,
        new_content=content,
        diff=generate_diff("PRODUCT_UPDATE.md", old or "", content),
    ))

    return changes, "placeholder"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "feature"


def _pascal_case(slug: str) -> str:
    return "".join(part.capitalize() for part in slug.split("-") if part)


def _ensure_rel_dir(path: Path) -> Path:
    return Path(str(path).strip("/"))


def _find_frontend_root(root: Path) -> Optional[Path]:
    candidates = [
        root / "frontend" / "src",
        root / "frontend",
        root / "src",
        root / "app",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _find_backend_root(root: Path) -> Optional[Path]:
    candidates = [
        root / "backend" / "app",
        root / "backend" / "src",
        root / "backend",
        root / "app",
        root,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _choose_frontend_ext(frontend_root: Path) -> str:
    ts_markers = ["App.tsx", "main.tsx", "vite-env.d.ts", "_layout.tsx"]
    if any((frontend_root / marker).exists() for marker in ts_markers):
        return "tsx"
    return "jsx"


def _build_frontend_scaffold(component_name: str, title: str, problem: str, why: str, demo: str, ext: str) -> str:
    if ext == "tsx":
        return f"""type {component_name}Props = {{
  onStart?: () => void
}}

export default function {component_name}({{ onStart }}: {component_name}Props) {{
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-3">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Generated Feature Scaffold</div>
        <h2 className="mt-2 text-xl font-semibold text-slate-900">{title}</h2>
      </div>
      <p className="text-sm text-slate-600">{problem}</p>
      <div className="mt-4 rounded-xl bg-slate-50 p-4">
        <div className="text-sm font-medium text-slate-900">Why this matters</div>
        <p className="mt-1 text-sm text-slate-600">{why}</p>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={{() => onStart?.()}}
          className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white"
        >
          Start flow
        </button>
        <span className="text-xs text-slate-500">{demo}</span>
      </div>
    </section>
  )
}}
"""
    return f"""export default function {component_name}({{ onStart }}) {{
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-3">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Generated Feature Scaffold</div>
        <h2 className="mt-2 text-xl font-semibold text-slate-900">{title}</h2>
      </div>
      <p className="text-sm text-slate-600">{problem}</p>
      <div className="mt-4 rounded-xl bg-slate-50 p-4">
        <div className="text-sm font-medium text-slate-900">Why this matters</div>
        <p className="mt-1 text-sm text-slate-600">{why}</p>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={{() => onStart?.()}}
          className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white"
        >
          Start flow
        </button>
        <span className="text-xs text-slate-500">{demo}</span>
      </div>
    </section>
  )
}}
"""


def _build_backend_scaffold(rel_root: Path, backend_root: Path, slug: str, title: str, problem: str, why: str, demo: str) -> Tuple[str, str]:
    if (backend_root / "__init__.py").exists() or rel_root.name == "app":
        rel_path = str(rel_root / f"produpos_{slug}.py")
        feature_spec = {
            "title": title,
            "customer_problem": problem,
            "why_this_matters": why,
            "demo_instructions": demo,
        }
        content = f'''"""Generated by ProdupOS as a safe fallback scaffold."""

from datetime import datetime


FEATURE_SPEC = {json.dumps(feature_spec, indent=4)}
FEATURE_SPEC["generated_at"] = datetime.utcnow().isoformat() + "Z"


def get_feature_spec() -> dict:
    return FEATURE_SPEC
'''
        return rel_path, content

    rel_path = str(rel_root / f"produpos-{slug}.js")
    content = f"""export const featureSpec = {{
  title: {json.dumps(title)},
  customerProblem: {json.dumps(problem)},
  whyThisMatters: {json.dumps(why)},
  demoInstructions: {json.dumps(demo)},
  generatedAt: new Date().toISOString(),
}}

export function getFeatureSpec() {{
  return featureSpec
}}
"""
    return rel_path, content


def _make_change(root: Path, rel_path: str, new_content: str) -> FileChange:
    full_path = root / rel_path
    old_content = None
    if full_path.exists():
        old_content = full_path.read_text(encoding="utf-8", errors="replace")
    return FileChange(
        path=rel_path,
        action="create" if old_content is None else "modify",
        old_content=old_content,
        new_content=new_content,
        diff=generate_diff(rel_path, old_content or "", new_content),
    )


def generate_diff(filename: str, old: str, new: str) -> str:
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm="",
    ))
    return "".join(diff)


def apply_implementation(
    product_path: str,
    file_changes: List[FileChange],
    exclusions: str = "",
) -> List[str]:
    """Write file changes to disk. Returns list of applied paths."""
    applied = []
    path = Path(product_path)

    for change in file_changes:
        if is_never_touch(change.path):
            continue
        if check_per_product_exclusions(product_path, change.path, exclusions):
            continue

        full_path = path / change.path
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(change.new_content, encoding="utf-8")
            applied.append(change.path)
        except Exception as e:
            pass

    return applied


def verify_implementation(product_path: str, file_changes: List[FileChange]) -> Dict:
    """Run quick syntax/compile checks on modified files."""
    results = []
    overall_ok = True

    for change in file_changes:
        full_path = Path(product_path) / change.path
        if not full_path.exists():
            continue

        ext = full_path.suffix.lower()
        ok = True
        error = ""

        if ext == ".py":
            try:
                import py_compile
                py_compile.compile(str(full_path), doraise=True)
            except Exception as e:
                ok = False
                error = str(e)
                overall_ok = False

        elif ext == ".json":
            try:
                json.loads(full_path.read_text())
            except Exception as e:
                ok = False
                error = str(e)
                overall_ok = False

        elif ext in {".yml", ".yaml"}:
            try:
                import yaml
                yaml.safe_load(full_path.read_text())
            except Exception as e:
                ok = False
                error = str(e)
                # yaml errors are non-critical

        results.append({"path": change.path, "ok": ok, "error": error})

    # Try to detect if main entry still importable for Python
    main_candidates = ["main.py", "app.py", "app/__init__.py"]
    for candidate in main_candidates:
        cp = Path(product_path) / candidate
        if cp.exists():
            try:
                result = subprocess.run(
                    ["python", "-c", f"import ast; ast.parse(open('{cp}').read())"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode != 0:
                    overall_ok = False
                    results.append({"path": candidate, "ok": False, "error": result.stderr[:200]})
            except Exception:
                pass
            break

    return {"ok": overall_ok, "checks": results}
