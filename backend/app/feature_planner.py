import json
from typing import Dict, List, Optional
from .config import settings
from .ai_clients import call_tool_with_fallback
from .schemas import FeatureProposal

FALLBACK_FEATURES: Dict[str, List[Dict]] = {
    "next.js": [
        {"feature_title": "Add SEO metadata management panel",
         "customer_problem": "Pages lack consistent meta tags, hurting search visibility.",
         "why_this_matters": "SEO is a top acquisition channel; automated meta management reduces dev toil.",
         "files_likely_to_change": ["app/layout.tsx", "app/page.tsx"],
         "risk_level": "low", "estimated_scope": "2-4 hours",
         "demo_instructions": "Open any page and inspect <head> for og: and twitter: meta tags."},
    ],
    "vite/react": [
        {"feature_title": "Add user preferences panel with theme toggle",
         "customer_problem": "No way to persist UI preferences across sessions.",
         "why_this_matters": "Personalization increases retention and reduces friction.",
         "files_likely_to_change": ["src/App.jsx", "src/components/PreferencesPanel.jsx"],
         "risk_level": "low", "estimated_scope": "2-3 hours",
         "demo_instructions": "Click settings icon, toggle dark mode, refresh — preference persists."},
    ],
    "react": [
        {"feature_title": "Add export/download report view as CSV",
         "customer_problem": "Users cannot share or archive data outside the app.",
         "why_this_matters": "Data portability is a core user expectation for any dashboard.",
         "files_likely_to_change": ["src/App.jsx", "src/components/ExportButton.jsx"],
         "risk_level": "low", "estimated_scope": "2 hours",
         "demo_instructions": "Click Export → Downloads a CSV of current table data."},
    ],
    "fastapi": [
        {"feature_title": "Add /metrics endpoint with system and usage stats",
         "customer_problem": "No visibility into API usage, uptime, or error rates.",
         "why_this_matters": "Observability is critical for production ops and customer SLAs.",
         "files_likely_to_change": ["app/main.py", "app/routers/metrics.py"],
         "risk_level": "low", "estimated_scope": "2-3 hours",
         "demo_instructions": "GET /metrics returns JSON with uptime, request counts, error rate."},
    ],
    "django": [
        {"feature_title": "Add audit log middleware for all write operations",
         "customer_problem": "No record of who changed what or when in the system.",
         "why_this_matters": "Audit logs are required for compliance and debugging data issues.",
         "files_likely_to_change": ["middleware.py", "models.py", "admin.py"],
         "risk_level": "medium", "estimated_scope": "3-5 hours",
         "demo_instructions": "Make any POST/PUT/DELETE — check AuditLog model in admin."},
    ],
    "flask": [
        {"feature_title": "Add rate limiting and request logging middleware",
         "customer_problem": "API is unprotected from abuse and has no request visibility.",
         "why_this_matters": "Rate limiting prevents DoS; logging enables debugging.",
         "files_likely_to_change": ["app/__init__.py", "middleware.py"],
         "risk_level": "low", "estimated_scope": "2 hours",
         "demo_instructions": "Exceed rate limit → 429 response. Check logs for request trace."},
    ],
    "node api": [
        {"feature_title": "Add structured audit log for all mutating API calls",
         "customer_problem": "No trail of changes made through the API.",
         "why_this_matters": "Debugging and compliance both require who-did-what-when.",
         "files_likely_to_change": ["middleware/auditLog.js", "routes/index.js"],
         "risk_level": "low", "estimated_scope": "2-3 hours",
         "demo_instructions": "Make a POST request — check audit_logs table or log file."},
    ],
    "full-stack": [
        {"feature_title": "Add real-time activity timeline with WebSocket updates",
         "customer_problem": "Users must refresh to see changes made by others.",
         "why_this_matters": "Real-time UX is a competitive differentiator and reduces support load.",
         "files_likely_to_change": ["backend/app/main.py", "frontend/src/components/Timeline.jsx"],
         "risk_level": "medium", "estimated_scope": "4-6 hours",
         "demo_instructions": "Open app in two tabs — actions in one reflect instantly in the other."},
    ],
    "docker": [
        {"feature_title": "Add health-check endpoint and Docker HEALTHCHECK directive",
         "customer_problem": "Container orchestrators cannot determine if the service is healthy.",
         "why_this_matters": "Missing health checks cause silent failures in Kubernetes/ECS.",
         "files_likely_to_change": ["Dockerfile", "app/main.py"],
         "risk_level": "low", "estimated_scope": "1-2 hours",
         "demo_instructions": "docker inspect <container> shows health status 'healthy'."},
    ],
    "default": [
        {"feature_title": "Add comprehensive README with architecture and quickstart",
         "customer_problem": "New contributors cannot onboard without oral knowledge transfer.",
         "why_this_matters": "Documentation velocity multiplier — cuts onboarding from days to hours.",
         "files_likely_to_change": ["README.md"],
         "risk_level": "low", "estimated_scope": "1-2 hours",
         "demo_instructions": "Open README.md — read quickstart and run locally in under 5 minutes."},
    ],
}


def get_fallback_feature(detected_stack: str, existing_features: List[str]) -> FeatureProposal:
    stack_lower = detected_stack.lower()
    candidates = []

    for key, features in FALLBACK_FEATURES.items():
        if key in stack_lower:
            candidates.extend(features)

    if not candidates:
        candidates = FALLBACK_FEATURES["default"]

    for candidate in candidates:
        if candidate["feature_title"] not in existing_features:
            return FeatureProposal(**candidate)

    return FeatureProposal(**candidates[0])


def propose_feature_with_ai(
    product_name: str,
    product_path: str,
    detected_stack: str,
    readme_content: str,
    file_summary: str,
    existing_features: List[str],
    manual_override: Optional[str] = None,
) -> tuple[FeatureProposal, int, str, Optional[str]]:
    try:
        system = (
            "You are ProdupOS, an AI product engineer. "
            "Analyze the given product and propose exactly one high-impact feature. "
            "The feature must be unique to this product, feasible in the current codebase, "
            "demoable locally, and aligned with the product's direction. "
            "Always respond using the submit_feature_proposal tool."
        )

        user_msg = f"""Product: {product_name}
Stack: {detected_stack}
Path: {product_path}

README (first 2000 chars):
{readme_content[:2000]}

File structure:
{file_summary[:3000]}

Already implemented features (do NOT repeat):
{chr(10).join(existing_features) if existing_features else 'None'}

{'User manual override request: ' + manual_override if manual_override else 'Choose the best feature based on your analysis.'}

Propose one feature using the tool."""

        schema = {
            "type": "object",
            "properties": {
                "feature_title": {"type": "string"},
                "customer_problem": {"type": "string"},
                "why_this_matters": {"type": "string"},
                "files_likely_to_change": {"type": "array", "items": {"type": "string"}},
                "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                "estimated_scope": {"type": "string"},
                "demo_instructions": {"type": "string"},
            },
            "required": ["feature_title", "customer_problem", "why_this_matters",
                         "files_likely_to_change", "risk_level", "estimated_scope",
                         "demo_instructions"],
        }

        result = call_tool_with_fallback(
            system=system,
            user_message=user_msg,
            tool_name="submit_feature_proposal",
            tool_description="Submit the single best feature proposal for this product",
            input_schema=schema,
            max_tokens=2048,
            timeout=settings.ai_timeout,
        )
        return FeatureProposal(**result.tool_input), result.tokens, result.provider, None

    except Exception as e:
        return get_fallback_feature(detected_stack, existing_features), 0, "fallback", str(e)


def generate_multiple_proposals(
    product_name: str,
    product_path: str,
    detected_stack: str,
    readme_content: str,
    file_summary: str,
) -> tuple[List[FeatureProposal], int]:
    """Generate backlog of 3-5 feature proposals for this product."""
    try:
        user_msg = f"""Product: {product_name} | Stack: {detected_stack}

README: {readme_content[:1500]}
Files: {file_summary[:2000]}

Generate exactly 4 distinct feature proposals for the backlog. Use the tool."""

        schema = {
            "type": "object",
            "properties": {
                "proposals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "feature_title": {"type": "string"},
                            "customer_problem": {"type": "string"},
                            "why_this_matters": {"type": "string"},
                            "files_likely_to_change": {"type": "array", "items": {"type": "string"}},
                            "risk_level": {"type": "string"},
                            "estimated_scope": {"type": "string"},
                            "demo_instructions": {"type": "string"},
                        },
                        "required": ["feature_title", "customer_problem", "why_this_matters",
                                     "files_likely_to_change", "risk_level", "estimated_scope",
                                     "demo_instructions"],
                    },
                    "minItems": 3,
                    "maxItems": 5,
                }
            },
            "required": ["proposals"],
        }

        result = call_tool_with_fallback(
            system=None,
            user_message=user_msg,
            tool_name="submit_backlog",
            tool_description="Submit 4 feature proposals for the backlog",
            input_schema=schema,
            max_tokens=4096,
            timeout=settings.ai_timeout,
        )
        return [FeatureProposal(**p) for p in result.tool_input["proposals"]], result.tokens

    except Exception:
        pass

    stacks = ["default", "react", "fastapi"]
    proposals = []
    seen = []
    for s in stacks:
        p = get_fallback_feature(s if s in detected_stack.lower() else detected_stack, seen)
        seen.append(p.feature_title)
        proposals.append(p)
    return proposals, 0
