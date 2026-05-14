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
    gemini_api_key: str = ""
    moonshot_api_key: str = ""
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"
    gemini_model: str = "gemini-3-flash-preview"
    kimi_model: str = "kimi-k2-0905-preview"
    groq_model: str = "llama-3.3-70b-versatile"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_base_url: str = "http://localhost:11434"
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


def get_anthropic_api_key() -> str:
    return settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")


def apply_setting_override(key: str, value: str):
    """Apply selected persisted settings to the live process."""
    env_key_map = {
        "gemini_api_key": "GEMINI_API_KEY",
        "moonshot_api_key": "MOONSHOT_API_KEY",
        "anthropic_api_key": "ANTHROPIC_API_KEY",
        "groq_api_key": "GROQ_API_KEY",
    }
    if key in env_key_map:
        setattr(settings, key, value)
        if value:
            os.environ[env_key_map[key]] = value
        else:
            os.environ.pop(env_key_map[key], None)
        return

    cast_map = {
        "projects_root": str,
        "additional_roots": str,
        "max_concurrent_agents": int,
        "agent_timeout_seconds": int,
        "require_approval_before_write": lambda v: str(v).lower() == "true",
        "allow_git_commits": lambda v: str(v).lower() == "true",
        "allow_git_branch_creation": lambda v: str(v).lower() == "true",
        "allow_non_git_updates": lambda v: str(v).lower() == "true",
        "allow_auto_create_git_repo": lambda v: str(v).lower() == "true",
        "allow_github_pr": lambda v: str(v).lower() == "true",
        "dry_run": lambda v: str(v).lower() == "true",
        "ai_model": str,
        "gemini_model": str,
        "kimi_model": str,
        "groq_model": str,
        "ollama_model": str,
        "ollama_base_url": str,
    }
    caster = cast_map.get(key)
    if not caster or not hasattr(settings, key):
        return
    try:
        setattr(settings, key, caster(value))
    except Exception:
        pass

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
