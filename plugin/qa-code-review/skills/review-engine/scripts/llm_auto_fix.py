#!/usr/bin/env python3
"""
LLM auto-fix layer -- the ONLY place an LLM is involved in this engine.

Findings always come from deterministic_review.py (skill scripts +
qa-review-core, no LLM). This module takes those findings and the current
file contents, asks the LLM for corrected full-file contents (full-file
replacement is more reliable to apply than a unified diff), writes them,
commits as the bot identity, and pushes to the same PR/MR source branch. The
orchestrator (pr_mr_orchestrator.py) enforces the loop guardrails.

Provider selection: claude (ANTHROPIC_API_KEY) or github (GH_MODELS_TOKEN /
GITHUB_TOKEN) -- whichever the user has access to; see llm_client.choose_provider().
Standard library only, plus git via subprocess.
"""

import os
import json
import subprocess
from pathlib import Path
from typing import List, Optional

from llm_client import _extract_json_array, _http_post, _language_for  # reuse


FIX_SYSTEM_TEMPLATE = """You are fixing QA automation code review findings in a SINGLE pass.

Non-negotiable rules:
1. You MUST resolve EVERY finding listed for the file. Findings marked
   Critical and High are mandatory - none may remain after your change.
2. Return the COMPLETE corrected file (the whole file top to bottom), not a
   snippet or a diff.
3. Change only what the findings require. Do NOT reformat or rewrite unrelated
   code, and do NOT introduce any NEW violation of the standard below.

How to fix the common findings correctly:
- Missing await on an async action  -> add `await`.
- Hardcoded wait (waitForTimeout / sleep / Thread.sleep) -> remove it and rely
  on the following auto-waiting assertion, or use locator.waitFor(...).
- page.pause() / debugger / breakpoint -> delete the line.
- console.log / System.out.println (debug) -> delete the line.
- Locator used directly in a spec (POM violation) -> replace it with a call to
  the appropriate existing page-object method (page objects are already
  imported in the spec); do not invent locators in the spec.
- Index-based locator nth(0) / :first-child -> use the stable page-object method.
- Hardcoded credential/secret -> replace the literal with a value read from
  test data / config (e.g. an existing testData field), never a literal.
- Empty catch block -> never swallow: log via the logger, or remove the
  try/catch so the error propagates.

Review standard (condensed reference):
---
{standard}
---

Return ONLY a JSON array (no prose, no markdown fences):
[{{"file": "<path>", "content": "<full corrected file content>"}}]
After your change, every Critical and High finding for the file MUST be gone."""


def _fix_with_claude(system: str, user: str) -> List[dict]:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    # Use `or`: an unset repo var arrives as "" from Actions, not absent.
    model = os.environ.get("CLAUDE_MODEL") or "claude-sonnet-5"
    payload = {"model": model, "max_tokens": 8000, "temperature": 0,
               "system": system, "messages": [{"role": "user", "content": user}]}
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    data = _http_post("https://api.anthropic.com/v1/messages", headers, payload)
    text = "".join(b.get("text", "") for b in data.get("content", [])
                   if b.get("type") == "text")
    return _extract_json_array(text)


def _fix_with_github(system: str, user: str) -> List[dict]:
    token = os.environ.get("GH_MODELS_TOKEN") or os.environ["GITHUB_TOKEN"]
    model = os.environ.get("GH_MODEL") or "openai/gpt-4o"
    endpoint = (os.environ.get("GH_MODELS_ENDPOINT")
                or "https://models.github.ai/inference/chat/completions")
    payload = {"model": model, "temperature": 0, "max_tokens": 4096,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = _http_post(endpoint, headers, payload)
    return _extract_json_array(data["choices"][0]["message"]["content"])


PROVIDERS = {"claude": _fix_with_claude, "github": _fix_with_github}


def _run(cmd: List[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def build_fixes(findings: List[dict], repo_root: str, standard: str,
                provider: Optional[str] = None) -> List[dict]:
    """Ask the LLM for corrected contents of each file that has findings.

    One request PER FILE (not batched): small-context engines such as GitHub
    Models cap the request at ~8000 tokens, so batching several full files
    overflows it (HTTP 413). Per-file keeps each request small, and the fix
    prompt sends a trimmed standard since the findings already say what to fix.
    """
    provider = (provider or os.environ.get("LLM_PROVIDER", "none")).lower().strip()
    if provider not in PROVIDERS or not findings:
        return []

    brief_standard = standard[:2000]
    system = FIX_SYSTEM_TEMPLATE.format(standard=brief_standard)
    sev_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    files = sorted({f["file"] for f in findings})
    fixes: List[dict] = []
    for rel in files:
        p = Path(repo_root) / rel
        if not p.is_file():
            continue
        file_findings = sorted(
            (f for f in findings if f["file"] == rel),
            key=lambda f: sev_rank.get(f["severity"], 4),
        )
        must = sum(1 for f in file_findings if f["severity"] in ("Critical", "High"))
        payload = {
            "file": rel,
            "language": _language_for(rel),
            "must_fix_critical_high": must,
            "findings": [
                {"severity": f["severity"], "line": f["line"],
                 "rule": f["rule"], "detail": f.get("code", "")}
                for f in file_findings
            ],
            "content": p.read_text(encoding="utf-8", errors="ignore"),
        }
        user = (f"Fix this file. It has {must} Critical/High finding(s) that MUST "
                f"all be resolved in this single pass:\n" + json.dumps(payload, indent=2))
        try:
            fixes.extend(PROVIDERS[provider](system, user))
        except Exception as exc:  # noqa: BLE001 - fix is best-effort, per file
            print(f"  [Layer 3] LLM fix generation failed for {rel}: {exc}")
    return fixes


def apply_fixes(fixes: List[dict], repo_root: str) -> List[str]:
    """Write corrected contents to disk. Returns the list of changed paths."""
    changed = []
    for fix in fixes:
        rel = fix.get("file")
        content = fix.get("content")
        if not rel or content is None:
            continue
        target = Path(repo_root) / rel
        if not target.is_file():
            continue
        if target.read_text(encoding="utf-8", errors="ignore") == content:
            continue
        target.write_text(content, encoding="utf-8")
        changed.append(rel)
    return changed


def commit_and_push(changed: List[str], repo_root: str, branch: str,
                    iteration: int, max_retries: int = 3) -> bool:
    """Commit the changed files as the bot and push to the PR source branch.

    Push can fail transiently (e.g. the branch moved, a network blip) --
    retry up to max_retries times, re-fetching + rebasing between attempts,
    before giving up. This is the PR-level push-retry guardrail (max 3)."""
    if not changed:
        return False
    bot_name = os.environ.get("BOT_NAME", "qa-review-bot")
    bot_email = os.environ.get("BOT_EMAIL", "qa-review-bot@users.noreply.github.com")
    for rel in changed:
        _run(["git", "add", rel], repo_root)
    msg = f"fix(review): auto-fix review findings (iteration {iteration}) [bot]"
    commit = _run(["git",
                   "-c", f"user.name={bot_name}",
                   "-c", f"user.email={bot_email}",
                   "commit", "-m", msg], repo_root)
    if commit.returncode != 0:
        print(f"  [fix] commit failed: {commit.stderr.strip()}")
        return False

    for attempt in range(1, max_retries + 1):
        push = _run(["git", "push", "origin", f"HEAD:{branch}"], repo_root)
        if push.returncode == 0:
            print(f"  [fix] pushed auto-fix commit to {branch}: {', '.join(changed)}")
            return True
        print(f"  [fix] push attempt {attempt}/{max_retries} failed: {push.stderr.strip()}")
        if attempt < max_retries:
            _run(["git", "fetch", "origin", branch], repo_root)
            _run(["git", "rebase", f"origin/{branch}"], repo_root)
    print(f"  [fix] push failed after {max_retries} attempts; giving up for this iteration.")
    return False


def last_commit_is_bot(repo_root: str) -> bool:
    """Bot-author guard: True if HEAD was authored by the fix bot."""
    bot_email = os.environ.get("BOT_EMAIL", "qa-review-bot@users.noreply.github.com")
    res = _run(["git", "log", "-1", "--format=%ae"], repo_root)
    return res.returncode == 0 and res.stdout.strip() == bot_email
