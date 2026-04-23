import json
import re
from typing import Dict, Any, Tuple, Optional

import requests

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _strip_json_comments(s: str) -> str:
    # remove //... and /* ... */ which models sometimes add
    s = re.sub(r"//.*?$", "", s, flags=re.MULTILINE)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
    return s


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    m = _JSON_RE.search(text)
    if not m:
        return None
    candidate = _strip_json_comments(m.group(0)).strip()
    try:
        return json.loads(candidate)
    except Exception:
        return None


class OllamaRouter:
    def __init__(self, cfg: dict):
        self.enabled = bool(cfg.get("enabled", False))
        self.model = cfg.get("model", "qwen2.5:3b")
        self.base_url = (cfg.get("base_url") or "http://localhost:11434").rstrip("/")
        self.timeout_s = int(cfg.get("timeout_seconds", 25))
        self.allowed_intents = cfg.get("allowed_intents") or []

    def is_ready(self) -> bool:
        if not self.enabled:
            return False
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def route(self, text: str, lang: str) -> Tuple[str, Dict[str, Any], str]:
        """
        Returns (intent, payload, debug).
        intent MUST be from whitelist.
        payload always dict (or {}).
        """
        if not self.is_ready():
            return "unknown", {}, "Ollama disabled or not reachable"

        allowed = self.allowed_intents
        if not allowed:
            return "unknown", {}, "No allowed intents configured"

        system = (
            "You are a strict intent router for an assistive voice assistant.\n"
            "Return ONLY a single JSON object, nothing else.\n"
            "The JSON must have keys: intent (string) and payload (object).\n"
            "intent MUST be one of the allowed intents list provided.\n"
            "payload MUST be a JSON object (dictionary).\n"
            "If you are not sure, return intent='unknown' and empty payload.\n"
            "Never include comments in JSON.\n"
        )

        user = (
            f"Language: {lang}\n"
            f"Allowed intents: {allowed}\n\n"
            f"User text: {text}\n\n"
            'Return JSON exactly like: {"intent":"time","payload":{}}\n'
        )

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "temperature": 0.0,
        }

        url = f"{self.base_url}/api/chat"
        try:
            r = requests.post(url, json=body, timeout=self.timeout_s)
        except Exception as e:
            return "unknown", {}, f"HTTP error: {e}"

        if r.status_code >= 400:
            return "unknown", {}, f"HTTP {r.status_code}: {r.text[:200]}"

        try:
            data = r.json()
            content = data["message"]["content"]
        except Exception as e:
            return "unknown", {}, f"Bad response: {e}"

        obj = _extract_json(content)
        if not obj:
            return "unknown", {}, "No JSON returned by Ollama"

        intent = str(obj.get("intent", "unknown"))
        payload = obj.get("payload", {})

        if intent not in allowed:
            return "unknown", {}, "Intent not allowed"

        if not isinstance(payload, dict):
            payload = {}

        return intent, payload, "ok"

    def chat(self, text: str, lang: str) -> Tuple[str, str]:
        """
        Free-form answer (chat).
        Returns (answer_text, debug).
        """
        if not self.is_ready():
            return "Ollama is not available.", "not ready"

        # IMPORTANT: reduce hallucinations
        system = (
            "You are a helpful voice assistant.\n"
            "Rules:\n"
            "1) Be concise.\n"
            "2) If Language is 'kz' answer in Kazakh. If 'ru' answer in Russian. Otherwise answer in English.\n"
            "3) For factual questions: if you are NOT sure, say you don't know (do NOT guess).\n"
            "4) If user asks about time/date, do not invent; answer only if explicitly asked.\n"
        )

        user = f"Language: {lang}\nUser text: {text}"

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "temperature": 0.0,  # lower = fewer hallucinations
        }

        url = f"{self.base_url}/api/chat"
        try:
            r = requests.post(url, json=body, timeout=self.timeout_s)
        except Exception as e:
            return "Connection error to Ollama.", f"HTTP error: {e}"

        if r.status_code >= 400:
            return "Ollama error.", f"HTTP {r.status_code}: {r.text[:200]}"

        try:
            data = r.json()
            content = data["message"]["content"]
            return content.strip(), "ok"
        except Exception as e:
            return "Failed to read response.", f"Bad response: {e}"