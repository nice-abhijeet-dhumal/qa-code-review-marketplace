---
name: review-engine
description: The QA code-review engine. Standalone Python scripts that detect the framework, run a deterministic regex review (Layer 1), run an LLM semantic review (Layer 2, Claude or GitHub Models), generate gated auto-fixes, and orchestrate the full PR review→comment→fix→push→re-review loop. No MCP server required.
---

# Review Engine

## When to Use This Skill

Use these scripts to review and auto-fix a QA automation PR/MR. The
`pr_review.py` orchestrator is the main entry point; the others are used
individually for detection or a quick deterministic scan.

## Scripts

| Script | Purpose |
|--------|---------|
| `pr_review.py` | Full loop for a GitHub PR: detect → Layer 1 + Layer 2 review → post comment → gated auto-fix → push → re-review. |
| `detect_framework.py` | Detect the framework(s) and print the composed skill list + standard size (JSON). |
| `regex_review.py` | Layer-1 deterministic regex review. Modes: `pr` (GitHub/GitLab), `commit`, `repo`. |
| `llm_review.py` | Layer-2 semantic review library (Claude or GitHub Models). Called by `pr_review.py`. |
| `llm_fix.py` | Fix generation + verify-before-commit gate + commit/push. Called by `pr_review.py`. |

## How to Execute

**Full PR review + auto-fix (GitHub):**
```bash
GITHUB_REPOSITORY="owner/repo" PR_NUMBER="123" REPO_ROOT="$(pwd)" \
LLM_PROVIDER="github" AUTO_FIX="true" \
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr_review.py"
```

**Detect applicable standards:**
```bash
REPO_ROOT="$(pwd)" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_framework.py"
```

**Deterministic Layer-1 scan of the whole repo:**
```bash
REVIEW_MODE=repo REPO_ROOT="$(pwd)" \
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/regex_review.py"
```

## Output

`pr_review.py` posts one comment per review iteration and writes
`review_report.md`. It exits non-zero when Critical/High findings remain
(CI gate). `detect_framework.py` prints JSON: `{skills, repo_root, standard_chars}`.

## Design notes

- **Standards** are loaded from this plugin's `skills/` folder (sibling to
  `review-engine`), independent of `REPO_ROOT` (the repo under review).
- **Deterministic Layer 1 is authoritative**; the LLM layer is advisory. A
  **verify-before-commit gate** re-runs Layer 1 on each candidate fix and rejects
  any that would not reduce Critical/High — so findings are monotonic.

## Requirements

- Python 3.9+. Standard library only — no `pip install` needed.
