from pathlib import Path
from typing import List
try:
    from pydantic_settings import BaseSettings
    from pydantic import field_validator
except ImportError:
    from pydantic import BaseSettings, validator as field_validator

import os


class Settings(BaseSettings):
    # Core paths
    projects_root: str = str(Path.home() / "Downloads" / "Projects")
    additional_roots: str = ""  # comma-separated extra scan roots
    data_dir: str = str(Path.home() / "Downloads" / "Projects" / "ProdUPOS" / "data")
    produpOS_root: str = str(Path.home() / "Downloads" / "Projects" / "ProdUPOS")

    # Ports
    backend_port: int = 8091
    frontend_port: int = 5179

    # AI
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"
    ai_max_tokens: int = 8192
    ai_timeout: int = 120

    # Agent runtime
    max_concurrent_agents: int = 3
    agent_timeout_seconds: int = 300
    require_approval_before_write: bool = True

    # Git
    allow_git_commits: bool = True
    allow_git_branch_creation: bool = True
    allow_non_git_updates: bool = True
    allow_auto_create_git_repo: bool = False
    allow_github_pr: bool = False
    github_token: str = ""

    # Safety
    dry_run: bool = False

    # Scheduler
    enable_scheduler: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def get_all_roots(self) -> List[Path]:
        roots = [Path(self.projects_root)]
        if self.additional_roots:
            for r in self.additional_roots.split(","):
                r = r.strip()
                if r:
                    roots.append(Path(r))
        return roots

    def get_data_dir(self) -> Path:
        return Path(self.data_dir)

    def get_produpOS_root(self) -> Path:
        return Path(self.produpOS_root)


settings = Settings()

NEVER_TOUCH_PATTERNS = {
    ".env", ".env.local", ".env.production", ".env.development",
    "node_modules", ".git", "venv", ".venv", "__pycache__",
    "dist", "build", ".DS_Store", "*.pem", "*.key", "*.cert",
    "secrets.json", "credentials.json", ".aws", ".ssh",
}

SKIP_DIRS = {
    "node_modules", ".git", "venv", ".venv", "__pycache__",
    "dist", "build", ".next", ".nuxt", "coverage", ".cache",
    "target", "out", ".gradle", ".mvn",
}

PRODUCT_INDICATORS = {
    "package.json", "pyproject.toml", "requirements.txt",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "main.py", "app.py", "server.py", "index.js", "index.ts",
    "vite.config.js", "vite.config.ts", "next.config.js", "next.config.ts",
    "manage.py", "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
}

PRODUCT_DIRS = {
    "backend", "frontend", "src", "app", "server", "api",
    "lib", "pkg", "cmd", "routes", "controllers", "models",
}
