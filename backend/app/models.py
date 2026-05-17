from sqlalchemy import Column, String, Integer, Boolean, Float, Text, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False)
    detected_stack = Column(String, default="")
    updatable = Column(Boolean, default=False)
    skip_reason = Column(String, default="")
    git_status = Column(String, default="unknown")
    current_version = Column(String, default="")
    proposed_feature = Column(Text, default="")
    proposed_feature_json = Column(Text, default="")  # JSON blob of full FeatureProposal
    manual_feature = Column(Text, default="")
    mode = Column(String, default="auto")  # auto | manual
    selected = Column(Boolean, default=True)
    skip_persistent = Column(Boolean, default=False)
    per_product_exclusions = Column(Text, default="")  # comma-separated file patterns
    health_score = Column(Float, default=0.0)
    health_details = Column(Text, default="")  # JSON
    dependency_report = Column(Text, default="")  # JSON
    feature_backlog = Column(Text, default="")  # JSON array of past proposals
    code_confidence_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    run_items = relationship("RunItem", back_populates="product")
    snapshots = relationship("Snapshot", back_populates="product")


class Run(Base):
    __tablename__ = "runs"

    id = Column(String, primary_key=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, default="pending")  # pending | running | completed | failed
    total_products = Column(Integer, default=0)
    updated_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    total_tokens_used = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    report_path = Column(String, default="")

    items = relationship("RunItem", back_populates="run")


class RunItem(Base):
    __tablename__ = "run_items"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("runs.id"))
    product_id = Column(String, ForeignKey("products.id"))
    status = Column(String, default="pending")
    feature_title = Column(String, default="")
    version_before = Column(String, default="")
    version_after = Column(String, default="")
    git_branch = Column(String, default="")
    git_commit = Column(String, default="")
    github_pr_url = Column(String, default="")
    reason = Column(Text, default="")
    logs = Column(Text, default="")
    diff_preview = Column(Text, default="")  # JSON
    file_changes = Column(Text, default="")  # JSON
    verification_result = Column(Text, default="")  # JSON
    partial_state = Column(Boolean, default=False)
    tokens_used = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    run = relationship("Run", back_populates="items")
    product = relationship("Product", back_populates="run_items")


class Snapshot(Base):
    __tablename__ = "snapshots"

    id = Column(String, primary_key=True)
    product_id = Column(String, ForeignKey("products.id"))
    run_item_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    files_snapshot = Column(Text, default="")  # JSON: {path: content}
    git_stash_ref = Column(String, default="")
    restored = Column(Boolean, default=False)

    product = relationship("Product", back_populates="snapshots")


class FeatureBacklogItem(Base):
    __tablename__ = "feature_backlog"

    id = Column(String, primary_key=True)
    product_id = Column(String, ForeignKey("products.id"))
    feature_title = Column(String, default="")
    customer_problem = Column(Text, default="")
    why_this_matters = Column(Text, default="")
    files_likely_to_change = Column(Text, default="")
    risk_level = Column(String, default="low")
    estimated_scope = Column(String, default="")
    demo_instructions = Column(Text, default="")
    status = Column(String, default="proposed")  # proposed | implemented | dismissed
    created_at = Column(DateTime, default=datetime.utcnow)


class ScheduledRun(Base):
    __tablename__ = "scheduled_runs"

    id = Column(String, primary_key=True)
    name = Column(String, default="")
    schedule_type = Column(String, default="interval")  # interval | daily | weekly
    schedule_value = Column(String, default="24")  # hours / "HH:MM" / "MON HH:MM"
    mode = Column(String, default="auto")
    dry_run = Column(Boolean, default=True)
    enabled = Column(Boolean, default=True)
    next_run = Column(DateTime, nullable=True)
    last_run = Column(DateTime, nullable=True)
    last_run_id = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CodeChunk(Base):
    """Stores embedded code chunks for RAG-based feature planning.

    The embedding vector is serialised as a JSON string (embedding_json) so
    that no pgvector extension is required — cosine similarity is computed in
    Python by rag_service.retrieve_relevant_code().
    """

    __tablename__ = "code_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String, nullable=False, index=True)
    file_path = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    content_hash = Column(String(32))
    # JSON-serialised list[float] — no pgvector needed for SQLite
    embedding_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("product_id", "file_path", "chunk_index", name="uq_code_chunk"),
    )
