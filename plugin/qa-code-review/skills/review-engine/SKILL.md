---
name: review-engine
description: The QA code-review engine. Standalone Python scripts that detect the framework, run a deterministic script + SKILL.md review (no LLM), generate gated LLM auto-fixes, and orchestrate the full PR (GitHub) / MR (GitLab) review→comment→fix→push→re-review loop.
---

# Review Engine

## When to Use This Skill

Use these scripts to review and auto-fix a QA automation PR/MR, on **either
GitHub or GitLab**. `pr_mr_orchestrator.py` is the main entry point for CI; the others
are used individually for detection or a local/one-off deterministic scan.

**Review is script + SKILL.md only — no LLM is ever involved in finding
issues.** The LLM is used exclusively by `llm_auto_fix.py`, to fix findings this
engine already reported.

## Scripts

| Script | Purpose |
|--------|---------|
| `pr_mr_orchestrator.py` | Full loop for a GitHub PR or GitLab MR (auto-detected): detect → deterministic review (via each active skill's `scripts/review.py`) → post one comment → gated LLM auto-fix → push → re-review. |
| `detect_framework.py` | Detect the framework(s) (root **and** immediate subdirectories, so monorepo layouts like `ui/`, `api/` are found) and print the composed skill list + standard size (JSON). |
| `deterministic_review.py` | The deterministic engine: loads each active skill's `scripts/review.py`, merges patterns, and runs the review. Modes: `repo` (whole working tree), `commit` (GitHub or GitLab, by SHA), `local` (staged + unstaged working-tree changes — use this for a specific file that is already `git add`-staged, where a plain `git diff` would show nothing). |
| `llm_auto_fix.py` | The ONLY LLM touchpoint: fix generation from deterministic findings + verify-before-commit gate + commit/push (with push retry). |
| `llm_client.py` | Shared HTTP/JSON helpers for `llm_auto_fix.py` (Claude and GitHub Models providers) + `choose_provider()`. |

## How to Execute

**Full PR (GitHub) or MR (GitLab) review + auto-fix — same command, platform auto-detected:**
```bash
# GitHub
GITHUB_REPOSITORY="owner/repo" PR_NUMBER="123" GITHUB_TOKEN="..." REPO_ROOT="$(pwd)" \
AUTO_FIX="true" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr_mr_orchestrator.py"

# GitLab
CI_PROJECT_ID="456" CI_MERGE_REQUEST_IID="7" GITLAB_API_URL="https://gitlab.example.com/api/v4" \
GITLAB_PERSONAL_ACCESS_TOKEN="..." REPO_ROOT="$(pwd)" \
AUTO_FIX="true" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr_mr_orchestrator.py"
```
`LLM_PROVIDER` is optional — if unset it is auto-chosen from whichever
credential is present (`ANTHROPIC_API_KEY` -> claude, else `GH_MODELS_TOKEN`/
`GITHUB_TOKEN` -> github, else `none` -> review only, no fix).

**Detect applicable standards:**
```bash
REPO_ROOT="$(pwd)" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_framework.py"
```

**Deterministic scan of the whole repo (no CI, no LLM):**
```bash
REVIEW_MODE=repo REPO_ROOT="$(pwd)" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deterministic_review.py"
```

**Deterministic scan of local staged/unstaged changes (no CI, no LLM):**
```bash
REVIEW_MODE=local REPO_ROOT="$(pwd)" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deterministic_review.py"
```

**Deterministic scan of a specific commit (GitHub or GitLab, auto-detected):**
```bash
REVIEW_MODE=commit COMMIT_SHA="<sha>" REPO_ROOT="$(pwd)" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deterministic_review.py"
```

## Output

`pr_mr_orchestrator.py` posts one comment per review iteration and writes
`review_report.md`. It exits non-zero when Critical/High findings remain (CI
gate). `detect_framework.py` prints JSON: `{skills, repo_root, standard_chars}`.

## Retry guardrails (max 3 each)

- **PR-level:** `MAX_FIX_ITERATIONS` (default 3) — review→fix→re-review rounds.
- **API/push:** `API_MAX_RETRIES` (default 3) — transient GitHub/GitLab API
  calls and the fix-commit push, via `deterministic_review.with_retries()`.
- **Agent-level:** the local Claude Code agent flow retries the whole
  detect→review→fix→push attempt up to 3 times on non-guardrail failures
  (script/environment errors) — see `agents/qa-code-review.agent.md`.

## Design notes

- **Standards** are loaded from this plugin's `skills/` folder (sibling to
  `review-engine`), independent of `REPO_ROOT` (the repo under review). In CI,
  this plugin repo is checked out alongside the repo under review (see the
  code repo's workflow), so `SKILLS_DIR` points at the checked-out plugin's
  `skills/` — no vendored copy needed in the repo being reviewed.
- **Deterministic review is authoritative and exclusive** — `deterministic_review.py` never
  calls an LLM. The **verify-before-commit gate** re-runs `deterministic_review.py` on each
  candidate fix and rejects any that would not reduce Critical/High, so
  findings are monotonic across fix iterations.

## Requirements

- Python 3.9+. Standard library only — no `pip install` needed.
