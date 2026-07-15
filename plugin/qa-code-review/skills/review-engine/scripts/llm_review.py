#!/usr/bin/env python3
"""
Layer 2 -- LLM semantic review (provider-neutral).

Two interchangeable engines so a user with EITHER Claude or Copilot can run the
agent (not everyone has both):

  LLM_PROVIDER=claude   -> Anthropic Messages API   (ANTHROPIC_API_KEY)
  LLM_PROVIDER=github   -> GitHub Models / Copilot-family, OpenAI-compatible
                           chat completions endpoint (GH_MODELS_TOKEN / GITHUB_TOKEN)
  LLM_PROVIDER=none      -> skip Layer 2 (Layer 1 regex only)

Both engines receive the SAME composed skill standard from the dispatcher and
return findings in the SAME JSON schema, so scoring/formatting is unchanged:

  [{"severity","file","line","rule","rationale","suggestion"}]

Uses only the Python standard library.
"""

import os
import re
import json
import urllib.request
import urllib.error
from typing import List, Optional


SYSTEM_TEMPLATE = """You are a senior QA automation code reviewer.
Review ONLY the added/changed lines in the diff below against the review
standard. The file is `{file_path}` (language: {language}).

Review standard (authoritative):
---
{standard}
---

Return ONLY a JSON array (no prose, no markdown fences) where each element is:
{{"severity": "Critical|High|Medium|Low",
  "file": "<path>",
  "line": <int>,
  "rule": "<short rule name>",
  "rationale": "<why it is a problem, one sentence>",
  "suggestion": "<the concrete fix, one sentence>"}}
Only report issues you can tie to a specific changed line. Do not invent issues.
If there are no issues, return []."""


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
    # strip accidental markdown fences
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
        # Surface the API error body so failures (e.g. bad model id) are diagnosable.
        detail = exc.read().decode(errors="ignore")[:500]
        raise urllib.error.HTTPError(
            exc.url, exc.code, f"{exc.reason} :: {detail}", exc.headers, None)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

def _review_with_claude(system: str, user: str) -> List[dict]:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    # Use `or` (not get-default): an unset repo var is passed as "" by Actions.
    model = os.environ.get("CLAUDE_MODEL") or "claude-sonnet-5"
    payload = {
        "model": model,
        "max_tokens": 2000,
        "temperature": 0,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    data = _http_post("https://api.anthropic.com/v1/messages", headers, payload)
    text = "".join(block.get("text", "")
                    for block in data.get("content", [])
                    if block.get("type") == "text")
    return _extract_json_array(text)


def _review_with_github(system: str, user: str) -> List[dict]:
    # GitHub Models exposes an OpenAI-compatible endpoint usable with a token.
    # Secret/var names cannot start with GITHUB_ (reserved), so we use GH_*.
    # Falls back to the built-in GITHUB_TOKEN (auto-provided in Actions).
    token = os.environ.get("GH_MODELS_TOKEN") or os.environ["GITHUB_TOKEN"]
    model = os.environ.get("GH_MODEL") or "openai/gpt-4o"
    endpoint = (os.environ.get("GH_MODELS_ENDPOINT")
                or "https://models.github.ai/inference/chat/completions")
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = _http_post(endpoint, headers, payload)
    text = data["choices"][0]["message"]["content"]
    return _extract_json_array(text)


PROVIDERS = {"claude": _review_with_claude, "github": _review_with_github}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def llm_review_file(diff_text: str, file_path: str, standard: str,
                    provider: Optional[str] = None,
                    max_diff_chars: int = 12000) -> List[dict]:
    """Return LLM findings for one file's diff. Empty list on skip/failure."""
    provider = (provider or os.environ.get("LLM_PROVIDER", "none")).lower().strip()
    if provider == "none" or provider not in PROVIDERS:
        return []
    if not diff_text.strip():
        return []

    diff_text = diff_text[:max_diff_chars]
    system = SYSTEM_TEMPLATE.format(
        file_path=file_path, language=_language_for(file_path), standard=standard)
    user = f"Diff for `{file_path}`:\n```\n{diff_text}\n```"

    try:
        findings = PROVIDERS[provider](system, user)
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError, OSError) as exc:
        print(f"  [Layer 2] LLM review skipped for {file_path}: {exc}")
        return []

    normalized = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        sev = str(f.get("severity", "Medium")).capitalize()
        if sev not in ("Critical", "High", "Medium", "Low"):
            sev = "Medium"
        normalized.append({
            "severity": sev,
            "file": f.get("file", file_path),
            "line": int(f.get("line", 1) or 1),
            "rule": f.get("rule", "LLM finding"),
            "code": (f.get("rationale", "") + " -> " + f.get("suggestion", "")).strip(" ->"),
            "source": "llm",
        })
    return normalized
