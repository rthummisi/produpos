from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class FeatureProposal(BaseModel):
    feature_title: str
    customer_problem: str
    why_this_matters: str
    files_likely_to_change: List[str] = []
    risk_level: str = "low"
    estimated_scope: str = ""
    demo_instructions: str = ""


class FileChange(BaseModel):
    path: str
    action: str  # create | modify
    old_content: Optional[str] = None
    new_content: str = ""
    diff: Optional[str] = None


class DependencyInfo(BaseModel):
    name: str
    current_version: str
    latest_version: str
    outdated: bool
    security_advisory: bool = False


class DependencyReport(BaseModel):
    ecosystem: str  # pip | npm
    total: int
    outdated: int
    secure: bool
    packages: List[DependencyInfo] = []
    checked_at: str = ""


class HealthDetail(BaseModel):
    has_tests: bool = False
    has_readme: bool = False
    has_changelog: bool = False
    has_ci: bool = False
    last_commit_days_ago: Optional[int] = None
    todo_count: int = 0
    doc_quality: str = "none"
    test_coverage_estimate: str = "unknown"
    dependency_health: str = "unknown"


class ProductOut(BaseModel):
    id: str
    name: str
    path: str
    detected_stack: str
    updatable: bool
    skip_reason: str
    git_status: str
    current_version: str
    proposed_feature: str
    proposed_feature_json: Optional[str] = None
    manual_feature: str
    mode: str
    selected: bool
    skip_persistent: bool
    per_product_exclusions: str
    health_score: float
    health_details: Optional[str] = None
    dependency_report: Optional[str] = None
    feature_backlog: Optional[str] = None
    code_confidence_score: float
    last_update_at: Optional[datetime] = None
    last_built_feature_title: Optional[str] = None
    last_built_feature_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RunItemOut(BaseModel):
    id: str
    run_id: str
    product_id: str
    status: str
    feature_title: str
    version_before: str
    version_after: str
    git_branch: str
    git_commit: str
    github_pr_url: str
    reason: str
    logs: str
    diff_preview: Optional[str] = None
    file_changes: Optional[str] = None
    verification_result: Optional[str] = None
    tokens_used: int
    estimated_cost_usd: float
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RunOut(BaseModel):
    id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    total_products: int
    updated_count: int
    skipped_count: int
    failed_count: int
    total_tokens_used: int
    estimated_cost_usd: float
    report_path: str
    items: List[RunItemOut] = []

    class Config:
        from_attributes = True


class SnapshotOut(BaseModel):
    id: str
    product_id: str
    run_item_id: Optional[str] = None
    created_at: datetime
    restored: bool

    class Config:
        from_attributes = True


class FeatureBacklogItemOut(BaseModel):
    id: str
    product_id: str
    feature_title: str
    customer_problem: str
    why_this_matters: str
    files_likely_to_change: str
    risk_level: str
    estimated_scope: str
    demo_instructions: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ScheduledRunOut(BaseModel):
    id: str
    name: str
    schedule_type: str
    schedule_value: str
    mode: str
    dry_run: bool
    enabled: bool
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    last_run_id: str
    created_at: datetime

    class Config:
        from_attributes = True


# Request bodies
class SetModeRequest(BaseModel):
    mode: str  # auto | manual


class SetManualFeatureRequest(BaseModel):
    feature: str


class SetExclusionsRequest(BaseModel):
    patterns: str  # comma-separated


class SetSkipPersistentRequest(BaseModel):
    skip: bool


class RunRequest(BaseModel):
    product_ids: Optional[List[str]] = None  # None = all selected
    dry_run: bool = False


class ScheduleCreateRequest(BaseModel):
    name: str
    schedule_type: str = "interval"
    schedule_value: str = "24"
    mode: str = "auto"
    dry_run: bool = True


class SettingsUpdateRequest(BaseModel):
    key: str
    value: str


class RollbackRequest(BaseModel):
    snapshot_id: str


class ExportRequest(BaseModel):
    format: str = "json"  # json | md | csv
