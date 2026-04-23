import json
import os
import re
from typing import Dict, Any, Tuple, Optional

import requests


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    m = _JSON_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


class LLMRouter:
    """
    LLM fallback router:
    - Используется только если rule-based команды не распознали речь
    - Возвращает только JSON: {"intent": "...", "payload": {...}}
    - intent обязан быть в списке allowed_intents (whitelist)

    Поддерживает OpenAI-compatible Chat Completions endpoint.
    """

    def __init__(self, cfg: dict):
        self.enabled = bool(cfg.get("enabled", False))
        self.model = cfg.get("model", "gpt-4o-mini")
        self.timeout_s = int(cfg.get("timeout_seconds", 15))

        self.api_base = (cfg.get("api_base") or "https://api.openai.com/v1").rstrip("/")
        self.api_key_env = cfg.get("api_key_env", "OPENAI_API_KEY")
        self.api_key = os.getenv(self.api_key_env, "")

        self.allow_no_key = bool(cfg.get("allow_no_key", False))
        self.allowed_intents = cfg.get("allowed_intents") or []

    def is_ready(self) -> bool:
        if not self.enabled:
            return False
        if self.api_key:
            return True
        return self.allow_no_key

    def route(self, text: str, lang: str) -> Tuple[str, Dict[str, Any], str]:
        """
        Returns: (intent, payload, debug_message)
        If fails: ("unknown", {}, reason)
        """
        if not self.is_ready():
            return "unknown", {}, "LLM disabled or API key missing"

        if not text or not text.strip():
            return "unknown", {}, "Empty text"

        allowed = self.allowed_intents
        if not allowed:
            return "unknown", {}, "No allowed intents configured"

        system = (
            "You are a strict intent router for an assistive voice assistant.\n"
            "Return ONLY a single JSON object, nothing else.\n"
            "The JSON must have keys: intent (string) and payload (object).\n"
            "intent MUST be one of the allowed intents list provided.\n"
            "payload MUST match the intent and contain only simple JSON types.\n"
            "If you are not sure, return intent='unknown' and empty payload.\n"
        )

        user = (
            f"Language: {lang}\n"
            f"Allowed intents: {allowed}\n\n"
            f"User text: {text}\n\n"
            "Return JSON like:\n"
            '{"intent":"time","payload":{}}\n'
        )

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.api_base}/chat/completions"

        try:
            r = requests.post(url, headers=headers, json=body, timeout=self.timeout_s)
        except Exception as e:
            return "unknown", {}, f"HTTP error: {e}"

        if r.status_code >= 400:
            return "unknown", {}, f"HTTP {r.status_code}: {r.text[:200]}"

        try:
            data = r.json()
            content = data["choices"][0]["message"]["content"]
        except Exception as e:
            return "unknown", {}, f"Bad response: {e}"

        obj = _extract_json(content)
        if not obj:
            return "unknown", {}, "No JSON returned by LLM"

        intent = str(obj.get("intent", "unknown"))
        payload = obj.get("payload", {})

        if intent not in allowed:
            return "unknown", {}, "Intent not allowed"

        if not isinstance(payload, dict):
            return "unknown", {}, "Payload is not an object"

        return intent, payload, "ok"