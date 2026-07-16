#!/usr/bin/env python3
"""
Shared HTTP/parsing helpers for the LLM auto-fix layer (llm_auto_fix.py).

There is no LLM review layer -- findings come only from deterministic_review.py
(the deterministic engine). The LLM is used exclusively to generate fixes for
those findings, per provider (Claude or GitHub Models / Copilot-family), based
on whichever the user has access to.
"""

import json
import os
import re
import urllib.request
import urllib.error
from typing import List


LANG_BY_EXT = {
    ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".mjs": "JavaScript", ".java": "Java",
    ".feature": "Gherkin", ".py": "Python", ".cs": "C#", ".rb": "Ruby",
}


def _language_for(file_path: str) -> str:
    _, ext = os.path.splitext(file_path)
    return LANG_BY_EXT.get(ext, "unknown")


def _extract_json_array(text: str) -> List[dict]:
    """Best-effort parse of a JSON array from a model response."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                return data if isinstance(data, list) else []
            except json.JSONDecodeError:
                return []
        return []


def _http_post(url: str, headers: dict, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="ignore")[:500]
        raise urllib.error.HTTPError(
            exc.url, exc.code, f"{exc.reason} :: {detail}", exc.headers, None)


def choose_provider() -> str:
    """Pick claude | github | none based on which credential the user has,
    unless LLM_PROVIDER is explicitly set."""
    forced = os.environ.get("LLM_PROVIDER", "").lower().strip()
    if forced:
        return forced
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    if os.environ.get("GH_MODELS_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        return "github"
    return "none"
