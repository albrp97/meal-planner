from __future__ import annotations

import json
import os
import re

DEFAULT_ENDPOINT = "https://api.business.githubcopilot.com"
DEFAULT_MODEL = "gpt-5.4"
DEFAULT_TIMEOUT_S = 60
CONFIG_PATH = os.path.expanduser("~/.copilot/config.json")
_CHAT_ONLY_PREFIXES = ("claude-",)


def _load_oauth_token() -> str:
    with open(CONFIG_PATH, encoding="utf-8") as config_file:
        raw = config_file.read()
    raw = re.sub(r"^\s*//.*$", "", raw, flags=re.M)
    tokens = json.loads(raw).get("copilotTokens") or {}
    if not tokens:
        raise RuntimeError(f"No Copilot OAuth token found in {CONFIG_PATH}. Run `copilot login` first.")
    return next(iter(tokens.values()))


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Copilot-Integration-Id": "copilot-developer-cli",
        "Editor-Version": "copilot/1.0.48",
        "User-Agent": "copilot/1.0.48",
    }


def _responses_body(prompt: str, context: str, model: str) -> dict:
    items = []
    if context.strip():
        items.append({"role": "system", "content": [{"type": "input_text", "text": context.strip()}]})
    items.append({"role": "user", "content": [{"type": "input_text", "text": prompt}]})
    return {"model": model, "stream": False, "input": items}


def _chat_body(prompt: str, context: str, model: str) -> dict:
    messages = []
    if context.strip():
        messages.append({"role": "system", "content": context.strip()})
    messages.append({"role": "user", "content": prompt})
    return {"model": model, "stream": False, "messages": messages}


def _path_for(model: str) -> str:
    return "/chat/completions" if model.startswith(_CHAT_ONLY_PREFIXES) else "/responses"


def _extract_text(model: str, data: dict) -> str:
    if model.startswith(_CHAT_ONLY_PREFIXES):
        return ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
    out = []
    for item in data.get("output", []):
        for content in item.get("content", []) or []:
            if content.get("type") in ("output_text", "text"):
                out.append(content.get("text", ""))
    return "".join(out).strip()


class CopilotClient:
    def __init__(
        self, endpoint: str = DEFAULT_ENDPOINT, model: str = DEFAULT_MODEL, timeout: float = DEFAULT_TIMEOUT_S
    ) -> None:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("Install the LLM extras first: pip install -e '.[llm]'") from exc
        self._httpx = httpx
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self._client = httpx.Client(timeout=timeout, headers=_headers(_load_oauth_token()), http2=False)

    def ask(self, prompt: str, context: str = "", model: str | None = None) -> str:
        selected_model = model or self.model
        body = (
            _chat_body(prompt, context, selected_model)
            if selected_model.startswith(_CHAT_ONLY_PREFIXES)
            else _responses_body(prompt, context, selected_model)
        )
        response = self._client.post(self.endpoint + _path_for(selected_model), json=body)
        response.raise_for_status()
        return _extract_text(selected_model, response.json())

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CopilotClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


_default_client: CopilotClient | None = None


def ask(prompt: str, context: str = "", model: str = DEFAULT_MODEL) -> str:
    global _default_client
    if _default_client is None:
        _default_client = CopilotClient(model=model)
    return _default_client.ask(prompt, context=context, model=model)
