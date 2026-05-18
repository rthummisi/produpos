"""E2E test runner — uses Playwright (agent-browser) for web products, httpx
for HTTP API products, and subprocess for existing test suites (pytest / npm test)."""

import asyncio
import json
import os
import re
import socket
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from .config import settings
from .job_manager import append_log, init_job_log
from .ai_clients import any_ai_provider_configured, call_tool_with_fallback


# ── Product start-info detection ─────────────────────────────────────────────

def _read_safe(path: Path, limit: int = 5000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception:
        return ""


def _detect_start_info(product_path: str, detected_stack: str) -> Dict:
    """Return {cmd, url, port} describing how to start and reach the product."""
    p = Path(product_path)
    cmd: Optional[str] = None
    url: Optional[str] = None
    port: Optional[int] = None

    # Vite-based frontend (React/Vue/Svelte)
    for cfg in ["vite.config.js", "vite.config.ts"]:
        if (p / cfg).exists():
            content = _read_safe(p / cfg)
            m = re.search(r"port[:\s]+(\d+)", content)
            port = int(m.group(1)) if m else 5173
            cmd = "npm run dev"
            url = f"http://localhost:{port}"
            return {"cmd": cmd, "url": url, "port": port}

    # package.json — pick first of dev / start / serve
    if (p / "package.json").exists():
        try:
            pkg = json.loads(_read_safe(p / "package.json"))
        except Exception:
            pkg = {}
        scripts = pkg.get("scripts", {})
        for s in ("dev", "start", "serve"):
            if s in scripts:
                script_val = scripts[s]
                m = re.search(r"PORT=(\d+)", script_val)
                if m:
                    port = int(m.group(1))
                else:
                    stk = detected_stack.lower()
                    port = 3000 if any(x in stk for x in ("react", "vue", "angular", "next")) else 8080
                cmd = f"npm run {s}"
                url = f"http://localhost:{port}"
                return {"cmd": cmd, "url": url, "port": port}

    # Django
    if (p / "manage.py").exists():
        return {"cmd": "python manage.py runserver 8000", "url": "http://localhost:8000", "port": 8000}

    # FastAPI / Flask / generic Python entry points
    for entry in ("main.py", "app.py", "server.py", "run.py"):
        if (p / entry).exists():
            content = _read_safe(p / entry)
            if "fastapi" in content.lower() or "uvicorn" in content.lower():
                app_var = "app"
                m = re.search(r"(\w+)\s*=\s*FastAPI\(", content)
                if m:
                    app_var = m.group(1)
                cmd = f"uvicorn {entry.replace('.py', '')}:{app_var} --port 8000"
            elif "flask" in content.lower():
                cmd = f"python {entry}"
            else:
                cmd = f"python {entry}"
            return {"cmd": cmd, "url": "http://localhost:8000", "port": 8000}

    # Go
    if (p / "go.mod").exists():
        return {"cmd": "go run .", "url": "http://localhost:8080", "port": 8080}

    # Rust / Cargo
    if (p / "Cargo.toml").exists():
        return {"cmd": "cargo run", "url": "http://localhost:8080", "port": 8080}

    return {"cmd": None, "url": None, "port": None}


def _is_port_open(port: int, host: str = "localhost") -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except Exception:
        return False


def _wait_for_port(port: int, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_port_open(port):
            return True
        time.sleep(0.5)
    return False


# ── AI test-plan generation ───────────────────────────────────────────────────

def _generate_test_plan(
    product_name: str, product_path: str, detected_stack: str, app_url: Optional[str]
) -> List[Dict]:
    """Use AI to generate URL checks; fall back to a basic root check."""
    p = Path(product_path)
    readme = ""
    for fname in ("README.md", "readme.md", "README"):
        fp = p / fname
        if fp.exists():
            readme = _read_safe(fp, 1500)
            break

    file_list = "\n".join(
        str(f.relative_to(p))
        for f in sorted(p.rglob("*"))[:25]
        if f.is_file() and ".git" not in str(f) and "node_modules" not in str(f)
    )

    if any_ai_provider_configured():
        try:
            result = call_tool_with_fallback(
                system=(
                    "You are an E2E test planner. Given a product, generate practical browser/HTTP "
                    "test checks that verify the app is running and its core features work."
                ),
                user_message=(
                    f"Product: {product_name}\nStack: {detected_stack}\nBase URL: {app_url or 'unknown'}\n"
                    f"README:\n{readme[:800]}\nFiles:\n{file_list[:400]}\n\n"
                    "Generate 3–5 check scenarios. Use absolute URLs (prefix relative paths with base URL)."
                ),
                tool_name="e2e_test_plan",
                tool_description="Produce a list of E2E test checks for the product",
                input_schema={
                    "type": "object",
                    "properties": {
                        "tests": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "url": {"type": "string"},
                                    "expect_text": {"type": "string"},
                                },
                                "required": ["name", "url"],
                            },
                        }
                    },
                    "required": ["tests"],
                },
                max_tokens=800,
                timeout=25,
            )
            tests = result.tool_input.get("tests", [])
            if tests and app_url:
                base = app_url.rstrip("/")
                for t in tests:
                    if t.get("url") and not t["url"].startswith("http"):
                        t["url"] = base + "/" + t["url"].lstrip("/")
            if tests:
                return tests
        except Exception:
            pass

    if app_url:
        return [
            {"name": "Homepage loads", "url": app_url, "expect_text": ""},
            {"name": "No 5xx on root", "url": app_url, "expect_text": ""},
        ]
    return []


# ── Browser (Playwright) checks ───────────────────────────────────────────────

def _run_playwright_checks(tests: List[Dict], app_url: str, log) -> List[Dict]:
    results: List[Dict] = []
    try:
        from playwright.sync_api import sync_playwright, Error as PWError
    except ImportError:
        log("Playwright not installed — falling back to HTTP checks (pip install playwright && playwright install chromium)")
        return _run_http_checks(tests, app_url, log)

    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(headless=True)
            except Exception as e:
                msg = str(e).lower()
                if "executable" in msg or "not found" in msg or "please run" in msg:
                    log("Chromium binary not installed — run 'playwright install chromium'. Falling back to HTTP.")
                    return _run_http_checks(tests, app_url, log)
                raise

            page = browser.new_page()
            page.set_default_timeout(15_000)
            try:
                for test in tests or [{"name": "Homepage", "url": app_url}]:
                    name = test.get("name", "check")
                    url = test.get("url", app_url)
                    expect_text = test.get("expect_text", "")
                    try:
                        resp = page.goto(url, wait_until="domcontentloaded")
                        ok = resp is not None and resp.status < 500
                        if ok and expect_text:
                            ok = expect_text.lower() in page.content().lower()
                        results.append({"name": name, "passed": ok,
                                        "status_code": resp.status if resp else None})
                        log(f"{'PASS' if ok else 'FAIL'}  {name}  (HTTP {resp.status if resp else '?'})")
                    except PWError as e:
                        results.append({"name": name, "passed": False, "error": str(e)[:200]})
                        log(f"FAIL  {name}  — {str(e)[:100]}")
                    except Exception as e:
                        results.append({"name": name, "passed": False, "error": str(e)[:200]})
                        log(f"FAIL  {name}  — {str(e)[:100]}")
            finally:
                page.close()
                browser.close()
    except Exception as e:
        log(f"Browser init error: {e}")
        results.append({"name": "Browser init", "passed": False, "error": str(e)[:300]})

    return results


# ── HTTP-only checks (fallback) ───────────────────────────────────────────────

def _run_http_checks(tests: List[Dict], app_url: str, log) -> List[Dict]:
    checks = tests or [{"name": "App health check", "url": app_url}]
    results: List[Dict] = []
    for check in checks:
        name = check.get("name", check.get("url", "check"))
        url = check.get("url", app_url)
        try:
            with httpx.Client(timeout=10, follow_redirects=True) as client:
                r = client.get(url)
                ok = r.status_code < 500
                results.append({"name": name, "passed": ok, "status_code": r.status_code})
                log(f"{'PASS' if ok else 'FAIL'}  {name}  (HTTP {r.status_code})")
        except Exception as e:
            results.append({"name": name, "passed": False, "error": str(e)[:200]})
            log(f"FAIL  {name}  — {str(e)[:120]}")
    return results


# ── Existing test-suite runner ────────────────────────────────────────────────

def _run_test_suite(product_path: str, detected_stack: str, log) -> List[Dict]:
    """Run pytest or npm test if detected; return result list."""
    p = Path(product_path)
    results: List[Dict] = []

    # pytest detection
    has_pytest = any([
        (p / "pytest.ini").exists(),
        (p / "tests").is_dir(),
        (p / "test").is_dir(),
        (p / "pyproject.toml").exists() and "pytest" in _read_safe(p / "pyproject.toml"),
        (p / "setup.cfg").exists() and "pytest" in _read_safe(p / "setup.cfg"),
    ])
    is_python = "python" in detected_stack.lower() or (p / "requirements.txt").exists() or (p / "pyproject.toml").exists()
    if has_pytest and is_python:
        log("Running pytest...")
        try:
            proc = subprocess.run(
                ["python", "-m", "pytest", "--tb=short", "-q", "--no-header"],
                cwd=product_path, capture_output=True, text=True, timeout=90,
            )
            ok = proc.returncode == 0
            out = (proc.stdout + proc.stderr).strip()[:500]
            results.append({"name": "pytest suite", "passed": ok, "output": out})
            log(f"{'PASS' if ok else 'FAIL'}  pytest  — {out[:120]}")
        except Exception as e:
            results.append({"name": "pytest suite", "passed": False, "error": str(e)})

    # npm test detection
    if (p / "package.json").exists():
        try:
            pkg = json.loads(_read_safe(p / "package.json"))
            if "test" in pkg.get("scripts", {}):
                log("Running npm test...")
                env = {**os.environ, "CI": "true"}
                proc = subprocess.run(
                    ["npm", "test", "--", "--watchAll=false", "--passWithNoTests"],
                    cwd=product_path, capture_output=True, text=True,
                    timeout=120, env=env,
                )
                ok = proc.returncode == 0
                out = (proc.stdout + proc.stderr).strip()[:500]
                results.append({"name": "npm test", "passed": ok, "output": out})
                log(f"{'PASS' if ok else 'FAIL'}  npm test  — {out[:120]}")
        except Exception as e:
            results.append({"name": "npm test", "passed": False, "error": str(e)})

    return results


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_e2e_test(
    *,
    product_id: str,
    product_name: str,
    product_path: str,
    detected_stack: str,
    job_id: str,
    db,
    triggered_by: str = "manual",
) -> Dict:
    """Run E2E tests for one product.  Streams logs via job_manager under job_id."""
    from .models import E2ETestResult, Product

    result_id = f"e2e-{uuid.uuid4().hex[:12]}"
    record = E2ETestResult(
        id=result_id,
        product_id=product_id,
        job_id=job_id,
        status="running",
        triggered_by=triggered_by,
        started_at=datetime.utcnow(),
        details="",
    )
    db.add(record)
    db.commit()

    def log(msg: str):
        append_log(job_id, f"[E2E:{product_name}] {msg}")

    log("=== E2E Test started ===")

    start_info = _detect_start_info(product_path, detected_stack)
    app_url: Optional[str] = start_info["url"]
    start_cmd: Optional[str] = start_info["cmd"]
    port: Optional[int] = start_info["port"]

    proc = None
    all_results: List[Dict] = []
    loop = asyncio.get_event_loop()

    try:
        # Start the product if not already running
        already_running = bool(port and _is_port_open(port))
        if already_running:
            log(f"App already running on port {port}")
        elif start_cmd:
            log(f"Starting: {start_cmd}")
            proc = subprocess.Popen(
                start_cmd, shell=True, cwd=product_path,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if port:
                log(f"Waiting for port {port} (up to 30 s)...")
                ready = await loop.run_in_executor(None, _wait_for_port, port, 30)
                log(f"Port {port} {'ready' if ready else 'not ready — proceeding anyway'}")
        else:
            log("No start command detected — will run test suite only")

        # Browser / HTTP checks
        if app_url:
            log(f"Building AI test plan for {app_url}...")
            test_plan = await loop.run_in_executor(
                None, _generate_test_plan, product_name, product_path, detected_stack, app_url,
            )
            log(f"{len(test_plan)} scenario(s) — launching agent-browser (Playwright)")
            check_results = await loop.run_in_executor(
                None, _run_playwright_checks, test_plan, app_url, log,
            )
            all_results.extend(check_results)

        # Existing test suites
        suite_results = await loop.run_in_executor(
            None, _run_test_suite, product_path, detected_stack, log,
        )
        all_results.extend(suite_results)

    except Exception as e:
        log(f"Runner error: {e}")
        all_results.append({"name": "E2E runner", "passed": False, "error": str(e)[:300]})
    finally:
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=5)
                log("Product process stopped")
            except Exception:
                pass

    # Tally
    total = len(all_results)
    n_passed = sum(1 for r in all_results if r.get("passed"))
    n_failed = total - n_passed

    if total == 0:
        status = "no_tests"
        summary = "No testable surface found (no URL detected and no test suite)"
    elif n_failed == 0:
        status = "passed"
        summary = f"All {total} check(s) passed"
    else:
        status = "failed"
        summary = f"{n_passed}/{total} check(s) passed  ·  {n_failed} failed"

    record.status = status
    record.summary = summary
    record.details = json.dumps(all_results)
    record.completed_at = datetime.utcnow()

    # Cache last result on the Product row
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        product.last_e2e_status = status
        product.last_e2e_at = datetime.utcnow()

    db.commit()
    log(f"=== E2E complete: {summary} [{status}] ===")

    return {"id": result_id, "status": status, "summary": summary, "results": all_results}
