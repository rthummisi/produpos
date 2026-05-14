import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from .config import settings
from .models import Product, RunItem, Snapshot
from .schemas import FeatureProposal, FileChange
from .safety import create_snapshot, restore_snapshot, pre_run_safety_check, get_git_status
from .feature_planner import propose_feature_with_ai
from .implementation_runner import generate_implementation_with_ai, apply_implementation, verify_implementation
from .git_manager import (
    create_branch, checkout_branch, stage_files, commit_changes,
    push_branch, create_github_pr, stash_dirty, pop_stash, commit_all_changes, cherry_pick_commit,
    get_current_branch, has_remote,
)
from .version_manager import get_current_version, bump_version
from .changelog_manager import update_changelog, write_product_update_doc
from .job_manager import append_log

# Cost per token (claude-sonnet-4-6, approximate)
COST_PER_INPUT_TOKEN = 3.0 / 1_000_000
COST_PER_OUTPUT_TOKEN = 15.0 / 1_000_000


class ProductAgent:
    def __init__(
        self,
        product: Product,
        run_item: RunItem,
        db: Session,
        job_id: str,
        dry_run: bool = False,
        override_dirty: bool = False,
    ):
        self.product = product
        self.run_item = run_item
        self.db = db
        self.job_id = job_id
        self.dry_run = dry_run
        self.override_dirty = override_dirty
        self.path = product.path
        self.logs: List[str] = []
        self.total_tokens = 0

    def log(self, msg: str):
        append_log(self.job_id, f"[{self.product.name}] {msg}")
        self.logs.append(msg)
        self.run_item.logs = "\n".join(self.logs)
        self.db.commit()

    def _get_readme(self) -> str:
        for fname in ["README.md", "README", "readme.md"]:
            fp = Path(self.path) / fname
            if fp.exists():
                try:
                    return fp.read_text(encoding="utf-8", errors="replace")[:3000]
                except Exception:
                    pass
        return ""

    def _get_file_summary(self) -> str:
        path = Path(self.path)
        skip = {"node_modules", ".git", "venv", ".venv", "__pycache__", "dist", "build"}
        lines = []
        try:
            for f in sorted(path.rglob("*"))[:60]:
                if any(s in str(f) for s in skip):
                    continue
                lines.append(str(f.relative_to(path)))
        except Exception:
            pass
        return "\n".join(lines)

    def _get_existing_features(self) -> List[str]:
        try:
            backlog = json.loads(self.product.feature_backlog or "[]")
            return [item.get("feature_title", "") for item in backlog]
        except Exception:
            return []

    async def run(self):
        self.run_item.started_at = datetime.utcnow()
        self.run_item.status = "running"
        self.db.commit()

        try:
            await asyncio.wait_for(self._execute(), timeout=settings.agent_timeout_seconds)
        except asyncio.TimeoutError:
            self.log("Agent timed out — marking as failed and restoring snapshot if available")
            self.run_item.status = "timed_out"
            self._restore_if_snapshot()
            self.run_item.completed_at = datetime.utcnow()
            self.db.commit()
        except Exception as e:
            self.log(f"Unexpected error: {e}")
            self.run_item.status = "failed"
            self.run_item.reason = str(e)
            self._restore_if_snapshot()
            self.run_item.completed_at = datetime.utcnow()
            self.db.commit()

    def _restore_if_snapshot(self):
        snap = self.db.query(Snapshot).filter(
            Snapshot.run_item_id == self.run_item.id
        ).first()
        if snap and not snap.restored:
            try:
                file_snap = json.loads(snap.files_snapshot)
                restore_snapshot(self.path, file_snap)
                snap.restored = True
                self.db.commit()
                self.log("Snapshot restored successfully")
            except Exception as e:
                self.log(f"Snapshot restore failed: {e}")

    async def _execute(self):
        self.log("Analyzing repository...")

        git_info = get_git_status(self.path)
        is_git = git_info.get("is_git", False)
        original_branch = git_info.get("branch", "main") if is_git else ""
        stash_ref = ""
        preexisting_commit_sha = ""

        # Stash any pre-existing dirty changes so we branch from clean HEAD
        if is_git and git_info.get("dirty"):
            dirty_count = len(git_info.get("modified", [])) + len(git_info.get("untracked", []))
            self.log(f"Repo is dirty ({dirty_count} files) — auto-saving local changes before update...")
            preexisting_commit_sha = commit_all_changes(
                self.path,
                "chore(guardian): auto-save pre-existing local changes before ProdupOS update",
            )
            if preexisting_commit_sha:
                self.log(f"Pre-existing changes committed to {original_branch}: {preexisting_commit_sha}")
                git_info = get_git_status(self.path)
            else:
                self.log("No dirty changes could be committed; proceeding with existing state")

        version_before = get_current_version(self.path)
        self.run_item.version_before = version_before

        # Load / generate proposal
        mode = self.product.mode
        if self.product.manual_feature:
            self.log("Using manual feature specification...")
            readme = self._get_readme()
            file_summary = self._get_file_summary()
            proposal, tokens, source, failure_reason = propose_feature_with_ai(
                self.product.name, self.path, self.product.detected_stack,
                readme, file_summary,
                self._get_existing_features(),
                manual_override=self.product.manual_feature,
            )
            self.total_tokens += tokens
        else:
            self.log("Loading auto-proposed feature...")
            try:
                proposal = FeatureProposal(**json.loads(self.product.proposed_feature_json))
            except Exception:
                readme = self._get_readme()
                file_summary = self._get_file_summary()
                proposal, tokens, source, failure_reason = propose_feature_with_ai(
                    self.product.name, self.path, self.product.detected_stack,
                    readme, file_summary,
                    self._get_existing_features(),
                )
                self.total_tokens += tokens

        self.run_item.feature_title = proposal.feature_title
        self.log(f"Feature: {proposal.feature_title}")

        # Generate implementation
        self.log("Generating implementation...")
        loop = asyncio.get_event_loop()
        file_changes, explanation, tokens, implementation_source = await loop.run_in_executor(
            None,
            generate_implementation_with_ai,
            self.product.name, self.path, self.product.detected_stack, proposal
        )
        self.total_tokens += tokens

        diffs = [{"path": fc.path, "diff": fc.diff, "action": fc.action} for fc in file_changes]
        self.run_item.diff_preview = json.dumps(diffs)
        self.run_item.file_changes = json.dumps([fc.model_dump() for fc in file_changes])
        self.db.commit()

        if implementation_source == "placeholder":
            if explanation:
                self.log(f"AI implementation unavailable: {explanation[:500]}")
            self.log("AI implementation unavailable — skipping write/version bump to avoid placeholder-only updates")
            self.run_item.status = "skipped"
            self.run_item.reason = explanation or "AI implementation unavailable; no code changes were applied"
            self.run_item.completed_at = datetime.utcnow()
            self._update_cost(self.total_tokens)
            self.db.commit()
            if stash_ref:
                self._restore_stash(original_branch, stash_ref)
            return

        if implementation_source == "scaffold":
            self.log("Using deterministic fallback scaffold implementation")

        if self.dry_run:
            self.log("Dry run — skipping writes")
            self.run_item.status = "dry_run_complete"
            self.run_item.completed_at = datetime.utcnow()
            self._update_cost(self.total_tokens)
            self.db.commit()
            return

        # Snapshot before writes
        snap_data = create_snapshot(self.path, [fc.model_dump() for fc in file_changes])
        snap = Snapshot(
            id=f"snap-{self.run_item.id}",
            product_id=self.product.id,
            run_item_id=self.run_item.id,
            files_snapshot=json.dumps(snap_data),
        )
        self.db.add(snap)
        self.db.commit()
        self.log(f"Snapshot saved for {len(snap_data)} files")

        # Apply implementation
        self.log("Writing files...")
        try:
            applied = apply_implementation(
                self.path, file_changes, self.product.per_product_exclusions
            )
            self.run_item.partial_state = True
            self.db.commit()
            self.log(f"Applied: {', '.join(applied)}")
        except Exception as e:
            self.log(f"Write failed: {e}")
            self.run_item.status = "failed"
            self.run_item.reason = str(e)
            self._restore_if_snapshot()
            self.run_item.completed_at = datetime.utcnow()
            self.db.commit()
            return

        # Verify
        self.log("Verifying...")
        verification = verify_implementation(self.path, file_changes)
        self.run_item.verification_result = json.dumps(verification)
        self.db.commit()

        if not verification["ok"]:
            self.log("Verification failed — restoring snapshot")
            self.run_item.status = "failed"
            failed_checks = [c for c in verification.get("checks", []) if not c.get("ok")]
            self.run_item.reason = failed_checks[0].get("error", "Verification failed") if failed_checks else "Verification failed"
            self._restore_if_snapshot()
            self.run_item.completed_at = datetime.utcnow()
            self.db.commit()
            return

        self.log("Verification passed")

        # Minor version bump
        self.log("Bumping minor version...")
        old_ver, new_ver = bump_version(self.path)
        self.run_item.version_before = old_ver
        self.run_item.version_after = new_ver
        self.db.commit()
        self.log(f"Version: {old_ver or 'none'} → {new_ver}")

        # Changelog + update doc
        update_changelog(self.path, new_ver, proposal)
        files_changed_names = [fc.path for fc in file_changes]
        write_product_update_doc(
            self.path, self.product.name,
            old_ver, new_ver, mode, proposal, files_changed_names
        )
        self.log("PRODUCT_UPDATE.md written")

        # Git: branch → stage → commit → push → return to original branch
        branch = ""
        commit_sha = ""
        pr_url = ""
        push_ok = False

        if is_git and settings.allow_git_commits:
            self.log("Creating update branch...")
            branch = create_branch(self.path, self.product.name)
            if branch:
                self.log(f"Branch: {branch}")

            all_changed = list(set(
                applied
                + ["CHANGELOG.md", "PRODUCT_UPDATE.md"]
                + [vf for vf in ["package.json", "pyproject.toml", "VERSION"]
                   if (Path(self.path) / vf).exists()]
            ))

            stage_files(self.path, all_changed)
            commit_sha = commit_changes(
                self.path, proposal.feature_title,
                self.product.name, old_ver, new_ver, all_changed
            )
            if commit_sha:
                self.log(f"Committed: {commit_sha}")

            # Push to remote
            if commit_sha:
                push_success, push_msg = push_branch(self.path, branch)
                push_ok = push_success
                self.log(f"Push: {push_msg}")

            # GitHub PR (optional)
            if settings.allow_github_pr and branch and commit_sha and push_ok:
                self.log("Opening GitHub PR...")
                pr_url = create_github_pr(
                    self.path, branch, original_branch,
                    proposal.feature_title, self.product.name,
                    proposal.why_this_matters,
                ) or ""
                if pr_url:
                    self.log(f"PR: {pr_url}")

            # Return to original branch and apply the verified commit there
            if branch and original_branch:
                checkout_branch(self.path, original_branch)
                self.log(f"Returned to {original_branch}")
                if commit_sha:
                    picked, pick_msg = cherry_pick_commit(self.path, commit_sha)
                    if picked:
                        self.log(f"Applied verified feature commit onto {original_branch}: {commit_sha}")
                    else:
                        self.log(f"Failed to apply verified feature commit onto {original_branch}: {pick_msg}")
                        self.run_item.status = "failed"
                        self.run_item.reason = f"Cherry-pick failed: {pick_msg}"
                        self.run_item.completed_at = datetime.utcnow()
                        self.db.commit()
                        return

        # Update product version in DB
        self.product.current_version = new_ver
        self._update_backlog(proposal)

        self.run_item.status = "updated"
        self.run_item.git_branch = branch
        self.run_item.git_commit = commit_sha
        self.run_item.github_pr_url = pr_url
        self.run_item.partial_state = False
        self.run_item.completed_at = datetime.utcnow()
        self._update_cost(self.total_tokens)
        self.db.commit()

        self.log(f"Feature built, verified, committed, and applied cleanly to {original_branch or 'current branch'}")
        self.log(f"Done ✓  v{old_ver or '?'} → v{new_ver} · {proposal.feature_title}")

    def _restore_stash(self, original_branch: str, stash_ref: str):
        if not stash_ref:
            return
        try:
            if original_branch:
                checkout_branch(self.path, original_branch)
            if pop_stash(self.path):
                self.log("Pre-existing changes restored (stash popped)")
            else:
                self.log("Warning: stash pop failed — check git stash list manually")
        except Exception as e:
            self.log(f"Stash restore error: {e}")

    def _update_cost(self, tokens: int):
        self.run_item.tokens_used = tokens
        cost = tokens * COST_PER_INPUT_TOKEN
        self.run_item.estimated_cost_usd = round(cost, 6)

    def _update_backlog(self, proposal: FeatureProposal):
        try:
            backlog = json.loads(self.product.feature_backlog or "[]")
        except Exception:
            backlog = []
        entry = proposal.model_dump()
        entry["status"] = "implemented"
        entry["implemented_at"] = datetime.utcnow().isoformat()
        backlog.append(entry)
        self.product.feature_backlog = json.dumps(backlog)
        self.db.commit()
