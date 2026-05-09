from pathlib import Path
from datetime import datetime
from .schemas import FeatureProposal


def _find_changelog(path: Path) -> Path:
    for name in ["CHANGELOG.md", "CHANGELOG", "HISTORY.md", "CHANGES.md"]:
        fp = path / name
        if fp.exists():
            return fp
    return path / "CHANGELOG.md"


def update_changelog(product_path: str, version: str, proposal: FeatureProposal) -> str:
    path = Path(product_path)
    cl_path = _find_changelog(path)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")

    entry = (
        f"\n## [{version}] - {date_str}\n\n"
        f"### Added — {proposal.feature_title}\n"
        f"- {proposal.customer_problem}\n"
        f"- Why: {proposal.why_this_matters}\n"
        f"- Files: {', '.join(proposal.files_likely_to_change)}\n"
        f"- Demo: {proposal.demo_instructions}\n"
        f"\n_Added by ProdupOS auto-update_\n"
    )

    if cl_path.exists():
        existing = cl_path.read_text(encoding="utf-8")
        # Insert after first heading line if present
        if existing.startswith("# "):
            lines = existing.split("\n")
            lines.insert(1, entry)
            new_content = "\n".join(lines)
        else:
            new_content = entry + existing
    else:
        new_content = f"# Changelog\n\nAll notable changes to this project are documented here.\n{entry}"

    cl_path.write_text(new_content, encoding="utf-8")
    return cl_path.name


def write_product_update_doc(
    product_path: str,
    product_name: str,
    version_before: str,
    version_after: str,
    mode: str,
    proposal: FeatureProposal,
    files_changed: list,
) -> None:
    path = Path(product_path)
    date_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    content = f"""# Product Update

**Product:** {product_name}
**Previous Version:** {version_before or "N/A"}
**New Version:** {version_after}
**Date:** {date_str}
**Mode:** {mode.capitalize()}

---

## Feature Implemented

**{proposal.feature_title}**

## Customer Problem

{proposal.customer_problem}

## Why This Feature

{proposal.why_this_matters}

## Files Changed

{chr(10).join(f"- `{f}`" for f in files_changed)}

## Risk Level

{proposal.risk_level.capitalize()}

## How To Run

Refer to the existing README for startup instructions. No new dependencies unless specified above.

## How To Demo

{proposal.demo_instructions}

## Estimated Scope

{proposal.estimated_scope}

---

_Generated automatically by [ProdupOS](https://github.com/produpos)_
"""
    (path / "PRODUCT_UPDATE.md").write_text(content, encoding="utf-8")
