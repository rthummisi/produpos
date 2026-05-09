import os
import json
import difflib
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .config import settings, SKIP_DIRS
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


def generate_implementation_with_ai(
    product_name: str,
    product_path: str,
    detected_stack: str,
    proposal: FeatureProposal,
) -> Tuple[List[FileChange], str, int]:
    api_key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    repo_context = _read_repo_files(product_path)

    if not api_key:
        return _generate_fallback_implementation(product_path, detected_stack, proposal), "", 0

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

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

        tools = [{
            "name": "submit_implementation",
            "description": "Submit the implementation as file changes",
            "input_schema": {
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
            },
        }]

        response = client.messages.create(
            model=settings.ai_model,
            max_tokens=settings.ai_max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            tools=tools,
            tool_choice={"type": "any"},
            timeout=settings.ai_timeout,
        )

        tokens = response.usage.input_tokens + response.usage.output_tokens

        for block in response.content:
            if block.type == "tool_use" and block.name == "submit_implementation":
                changes = []
                for fc in block.input["file_changes"]:
                    path = fc["path"]
                    old_content = None
                    full_path = Path(product_path) / path
                    if full_path.exists():
                        try:
                            old_content = full_path.read_text(encoding="utf-8", errors="replace")
                        except Exception:
                            pass
                    diff = generate_diff(path, old_content or "", fc["new_content"])
                    changes.append(FileChange(
                        path=path,
                        action=fc["action"],
                        old_content=old_content,
                        new_content=fc["new_content"],
                        diff=diff,
                    ))
                return changes, block.input.get("explanation", ""), tokens

    except Exception as e:
        pass

    return _generate_fallback_implementation(product_path, detected_stack, proposal), "", 0


def _generate_fallback_implementation(
    product_path: str,
    detected_stack: str,
    proposal: FeatureProposal,
) -> List[FileChange]:
    """Generate a minimal placeholder implementation when AI is unavailable."""
    path = Path(product_path)
    stack = detected_stack.lower()

    changes = []

    # Always create PRODUCT_UPDATE.md as minimum
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

    return changes


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
