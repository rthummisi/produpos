import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from .config import settings


@dataclass
class ToolCallResult:
    provider: str
    tool_input: Dict[str, Any]
    tokens: int


def get_gemini_api_key() -> str:
    return settings.gemini_api_key or os.environ.get("GEMINI_API_KEY", "")


def get_moonshot_api_key() -> str:
    return settings.moonshot_api_key or os.environ.get("MOONSHOT_API_KEY", "")


def get_anthropic_api_key() -> str:
    return settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")


def get_groq_api_key() -> str:
    return settings.groq_api_key or os.environ.get("GROQ_API_KEY", "")


def get_ollama_base_url() -> str:
    return (settings.ollama_base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")


def get_provider_chain() -> List[str]:
    return ["gemini", "kimi", "ollama", "anthropic", "groq"]


def is_ollama_available() -> bool:
    try:
        resp = httpx.get(f"{get_ollama_base_url()}/v1/models", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


def get_ollama_model() -> str:
    preferred = [
        settings.ollama_model,
        "gemma3:4b",
        "qwen2.5-coder:7b",
        "qwen2.5:32b",
        "llama3.2:latest",
        "mistral:latest",
        "gemma2:9b",
    ]
    try:
        resp = httpx.get(f"{get_ollama_base_url()}/v1/models", timeout=2.0)
        resp.raise_for_status()
        installed = {item.get("id", "") for item in resp.json().get("data", [])}
        for model in preferred:
            if model in installed:
                return model
    except Exception:
        pass
    return settings.ollama_model


def any_ai_provider_configured() -> bool:
    return bool(
        get_gemini_api_key()
        or get_moonshot_api_key()
        or get_anthropic_api_key()
        or get_groq_api_key()
        or is_ollama_available()
    )


def provider_status() -> Dict[str, bool]:
    return {
        "gemini": bool(get_gemini_api_key()),
        "kimi": bool(get_moonshot_api_key()),
        "anthropic": bool(get_anthropic_api_key()),
        "groq": bool(get_groq_api_key()),
        "ollama": is_ollama_available(),
    }


def call_tool_with_fallback(
    *,
    system: Optional[str],
    user_message: str,
    tool_name: str,
    tool_description: str,
    input_schema: Dict[str, Any],
    max_tokens: int,
    timeout: int,
    model_overrides: Optional[Dict[str, str]] = None,
) -> ToolCallResult:
    errors = []
    model_overrides = model_overrides or {}

    for provider in get_provider_chain():
        try:
            if provider == "gemini":
                key = get_gemini_api_key()
                if not key:
                    continue
                return _call_openai_compatible(
                    provider="gemini",
                    api_key=key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                    model=model_overrides.get("gemini") or settings.gemini_model,
                    system=system,
                    user_message=user_message,
                    tool_name=tool_name,
                    tool_description=tool_description,
                    input_schema=input_schema,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )

            if provider == "kimi":
                key = get_moonshot_api_key()
                if not key:
                    continue
                return _call_openai_compatible(
                    provider="kimi",
                    api_key=key,
                    base_url="https://api.moonshot.ai/v1",
                    model=model_overrides.get("kimi") or settings.kimi_model,
                    system=system,
                    user_message=user_message,
                    tool_name=tool_name,
                    tool_description=tool_description,
                    input_schema=input_schema,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )

            if provider == "anthropic":
                key = get_anthropic_api_key()
                if not key:
                    continue
                return _call_anthropic(
                    api_key=key,
                    model=model_overrides.get("anthropic") or settings.ai_model,
                    system=system or "",
                    user_message=user_message,
                    tool_name=tool_name,
                    tool_description=tool_description,
                    input_schema=input_schema,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )

            if provider == "groq":
                key = get_groq_api_key()
                if not key:
                    continue
                return _call_openai_compatible(
                    provider="groq",
                    api_key=key,
                    base_url="https://api.groq.com/openai/v1",
                    model=model_overrides.get("groq") or settings.groq_model,
                    system=system,
                    user_message=user_message,
                    tool_name=tool_name,
                    tool_description=tool_description,
                    input_schema=input_schema,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )

            if provider == "ollama":
                return _call_openai_compatible(
                    provider="ollama",
                    api_key="ollama",
                    base_url=f"{get_ollama_base_url()}/v1",
                    model=model_overrides.get("ollama") or get_ollama_model(),
                    system=system,
                    user_message=user_message,
                    tool_name=tool_name,
                    tool_description=tool_description,
                    input_schema=input_schema,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
        except Exception as exc:
            errors.append(f"{provider}: {exc}")

    raise RuntimeError("; ".join(errors) if errors else "No AI providers available")


def call_json_with_fallback(
    *,
    system: Optional[str],
    user_message: str,
    output_schema: Dict[str, Any],
    max_tokens: int,
    timeout: int,
    provider_order: Optional[List[str]] = None,
    model_overrides: Optional[Dict[str, str]] = None,
) -> ToolCallResult:
    errors = []
    model_overrides = model_overrides or {}

    for provider in provider_order or get_provider_chain():
        try:
            if provider == "gemini":
                key = get_gemini_api_key()
                if not key:
                    continue
                return _call_openai_json(
                    provider="gemini",
                    api_key=key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                    model=model_overrides.get("gemini") or settings.gemini_model,
                    system=system,
                    user_message=user_message,
                    output_schema=output_schema,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )

            if provider == "kimi":
                key = get_moonshot_api_key()
                if not key:
                    continue
                return _call_openai_json(
                    provider="kimi",
                    api_key=key,
                    base_url="https://api.moonshot.ai/v1",
                    model=model_overrides.get("kimi") or settings.kimi_model,
                    system=system,
                    user_message=user_message,
                    output_schema=output_schema,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )

            if provider == "ollama":
                return _call_openai_json(
                    provider="ollama",
                    api_key="ollama",
                    base_url=f"{get_ollama_base_url()}/v1",
                    model=model_overrides.get("ollama") or get_ollama_model(),
                    system=system,
                    user_message=user_message,
                    output_schema=output_schema,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )

            if provider == "anthropic":
                key = get_anthropic_api_key()
                if not key:
                    continue
                return _call_anthropic_json(
                    api_key=key,
                    model=model_overrides.get("anthropic") or settings.ai_model,
                    system=system or "",
                    user_message=user_message,
                    output_schema=output_schema,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )

            if provider == "groq":
                key = get_groq_api_key()
                if not key:
                    continue
                return _call_openai_json(
                    provider="groq",
                    api_key=key,
                    base_url="https://api.groq.com/openai/v1",
                    model=model_overrides.get("groq") or settings.groq_model,
                    system=system,
                    user_message=user_message,
                    output_schema=output_schema,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
        except Exception as exc:
            errors.append(f"{provider}: {exc}")

    raise RuntimeError("; ".join(errors) if errors else "No AI providers available")


def _call_openai_compatible(
    *,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    system: Optional[str],
    user_message: str,
    tool_name: str,
    tool_description: str,
    input_schema: Dict[str, Any],
    max_tokens: int,
    timeout: int,
) -> ToolCallResult:
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": model,
        "messages": messages,
        "tools": [{
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_description,
                "parameters": input_schema,
            },
        }],
        "tool_choice": {"type": "function", "function": {"name": tool_name}},
        "max_tokens": max_tokens,
    }
    if provider == "ollama":
        payload["response_format"] = {"type": "json_object"}

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    resp = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()

    try:
        tool_args = data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
        parsed = json.loads(tool_args)
    except Exception:
        parsed = _parse_json_content_fallback(data, input_schema)
        if parsed is None:
            raise RuntimeError(f"{provider} returned no tool call")

    usage = data.get("usage") or {}
    tokens = int((usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0))
    return ToolCallResult(provider=provider, tool_input=parsed, tokens=tokens)


def _call_openai_json(
    *,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    system: Optional[str],
    user_message: str,
    output_schema: Dict[str, Any],
    max_tokens: int,
    timeout: int,
) -> ToolCallResult:
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    resp = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    parsed = _parse_json_content_fallback(data, output_schema)
    if parsed is None:
        raise RuntimeError(f"{provider} returned no valid JSON payload")
    usage = data.get("usage") or {}
    tokens = int((usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0))
    return ToolCallResult(provider=provider, tool_input=parsed, tokens=tokens)


def _parse_json_content_fallback(data: Dict[str, Any], input_schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        return None
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        return None

    parsed = _extract_json_object(content)
    if not isinstance(parsed, dict):
        return None

    required = input_schema.get("required") or []
    if all(key in parsed for key in required):
        return parsed

    # Some local models wrap the target object.
    for value in parsed.values():
        if isinstance(value, dict) and all(key in value for key in required):
            return value

    return None


def _extract_json_object(content: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(content)
    except Exception:
        pass

    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _call_anthropic(
    *,
    api_key: str,
    model: str,
    system: str,
    user_message: str,
    tool_name: str,
    tool_description: str,
    input_schema: Dict[str, Any],
    max_tokens: int,
    timeout: int,
) -> ToolCallResult:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}],
        tools=[{
            "name": tool_name,
            "description": tool_description,
            "input_schema": input_schema,
        }],
        tool_choice={"type": "any"},
        timeout=timeout,
    )

    tokens = response.usage.input_tokens + response.usage.output_tokens
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return ToolCallResult(provider="anthropic", tool_input=block.input, tokens=tokens)
    raise RuntimeError("anthropic returned no tool call")


def _call_anthropic_json(
    *,
    api_key: str,
    model: str,
    system: str,
    user_message: str,
    output_schema: Dict[str, Any],
    max_tokens: int,
    timeout: int,
) -> ToolCallResult:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}],
        timeout=timeout,
    )
    tokens = response.usage.input_tokens + response.usage.output_tokens
    text = "".join(getattr(block, "text", "") for block in response.content if getattr(block, "type", "") == "text")
    parsed = _extract_json_object(text)
    if not isinstance(parsed, dict):
        raise RuntimeError("anthropic returned no valid JSON payload")
    required = output_schema.get("required") or []
    if not all(key in parsed for key in required):
        raise RuntimeError("anthropic JSON payload missing required fields")
    return ToolCallResult(provider="anthropic", tool_input=parsed, tokens=tokens)


# ── OllamaClient: async text generation (gemma3:4b and other local models) ───

class OllamaClient:
    """Async LLM client that talks to a local Ollama server.

    Defaults to gemma3:4b but respects the OLLAMA_MODEL env var and
    settings.ollama_model.  Falls back gracefully when Ollama is offline.

    Usage::

        client = OllamaClient()
        text = await client.generate("Summarise this PR", system="You are a helpful assistant.")
    """

    def __init__(self):
        self.base_url = get_ollama_base_url() + "/v1"
        self.model = settings.ollama_model or os.environ.get("OLLAMA_MODEL", "gemma3:4b")

    async def generate(
        self, prompt: str, system: str = "", max_tokens: int = 4096
    ) -> str:
        """Send a chat completion request and return the response text.

        Returns an empty string on any error so callers can decide whether to
        fall back to a cloud provider.
        """
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                    },
                    headers={"Authorization": "Bearer ollama"},
                )
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        except Exception:
            return ""


def get_llm_client() -> OllamaClient:
    """Return an OllamaClient configured for the active local model.

    When LLM_PROVIDER=ollama (or no cloud API keys are set), this is the
    primary client.  Cloud providers are still used by call_tool_with_fallback
    for structured tool-call workflows.
    """
    return OllamaClient()
