# qa-code-review

Framework-agnostic QA automation **code review + auto-fix** agent, for
**GitHub and GitLab**. Reviews a PR/MR against composable framework
standards, posts a scored feedback comment, fixes the findings with an LLM,
pushes to the same branch, and re-reviews — with a deterministic, monotonic
guarantee.

## Overview

**Review has no LLM involvement at all.** Every skill (`qa-review-core` +
one driver overlay + `bdd-cucumber` when applicable) owns its own
`scripts/review.py`; the engine loads and merges them, and that is the
entire review step — deterministic, reproducible, and the sole source of
findings and the score.

1. **Detect** the framework(s) (root + immediate subdirectories, so `ui/`,
   `api/`-style monorepos are found) and compose the applicable skills.
2. **Review** — each active skill's `scripts/review.py`, merged. No LLM.
3. **Comment** — one scored review comment on the PR/MR.
4. **Fix** (the ONLY LLM step) — generate a fix, pass it through a
   **verify-before-commit gate** (rejects any fix that would not reduce
   Critical/High), commit as the bot, push to the same branch.
5. **Re-review** — repeat until the score clears the threshold or the
   iteration cap (max 3) is hit. Findings never increase between iterations.

## Files in `skills/review-engine/scripts/`

Each file name says exactly what it does — no generic `engine.py`/`utils.py`:

| File | What it does |
|------|---------------|
| `detect_framework.py` | **Detection only.** Scans the repo root + immediate subdirectories for `package.json`/`tsconfig.json`/`playwright.config.*`/Maven-Gradle files and returns the ordered skill list (e.g. `["qa-review-core", "playwright-js"]`). Also loads each skill's `SKILL.md` text — used only as fix-context later, never to produce findings. |
| `deterministic_review.py` | **The review itself — no LLM.** Dynamically imports every active skill's `scripts/review.py`, merges their pattern lists, and runs them against file content (`analyze_file_content`/`analyze_diff`). Owns scoring, report formatting, the GitHub/GitLab API helpers, the retry wrapper, and a standalone CLI (`REVIEW_MODE=repo\|local\|commit`) for scans that don't need the fix loop. |
| `llm_client.py` | **Shared plumbing only — no review or fix logic.** HTTP POST helper, JSON-array response parser, file-extension → language lookup, and `choose_provider()` (picks `claude`/`github`/`none` from whichever credential is set). Used only by `llm_auto_fix.py`. |
| `llm_auto_fix.py` | **The only file that calls an LLM.** Takes the findings `deterministic_review.py` produced and asks Claude or GitHub Models for a corrected full-file version per file (`build_fixes`), then commits/pushes as the bot (`commit_and_push`, with push retry). It never decides what's wrong — only how to fix what it's told is wrong. |
| `pr_mr_orchestrator.py` | **The CI entrypoint** — ties the four files above together for a GitHub PR or GitLab MR: detect → review → post comment → (if enabled) fix → push → re-review, looped up to `MAX_FIX_ITERATIONS`. `GitHubAdapter`/`GitLabAdapter` inside this file are the only platform-specific code in the whole engine. |

## Execution flow — file by file

### PR/MR flow (CI — GitHub or GitLab)

Entrypoint: `python3 pr_mr_orchestrator.py`

```
pr_mr_orchestrator.py                                    (entrypoint)
  │
  ├─ detect_framework.py      .resolve(repo_root)
  │     → scans repo root + subdirs → e.g. ["qa-review-core", "playwright-js"]
  │
  ├─ deterministic_review.py  .load_patterns(skills, skills_dir)
  │     → imports qa-review-core/scripts/review.py
  │     → imports playwright-js/scripts/review.py  (the detected driver overlay)
  │     → imports bdd-cucumber/scripts/review.py   (only if .feature files exist)
  │     → merges all pattern lists into one dict
  │
  ├─ GitHubAdapter / GitLabAdapter   .changed_files() / .head_branch()
  │     → deterministic_review.github_api() or .gitlab_api(), via .with_retries()
  │
  ├─ deterministic_review.py  .analyze_file_content(content, path, patterns)   [per file]
  │     → runs the merged patterns — THIS is the review. No LLM call.
  │
  ├─ deterministic_review.py  .compute_score() + .format_report()
  ├─ adapter.post_comment(report)             → one PR/MR comment posted
  │
  │   ── loop while AUTO_FIX and score < SCORE_THRESHOLD, max 3 (MAX_FIX_ITERATIONS) ──
  │
  ├─ llm_client.py  .choose_provider()         → claude | github | none
  ├─ llm_auto_fix.py  .build_fixes(findings, repo_root, standard, provider)
  │     → THE ONLY LLM CALL — sends findings + file content to Claude/GitHub Models
  │
  ├─ pr_mr_orchestrator.py  .apply_fixes_gated(fixes, repo_root, patterns)
  │     → re-runs deterministic_review.analyze_file_content() on the CANDIDATE fix
  │     → accepts only if Critical/High did not regress (verify-before-commit gate)
  │
  ├─ llm_auto_fix.py  .commit_and_push(accepted, repo_root, branch, iteration)
  │     → commits as bot, pushes; retries push up to API_MAX_RETRIES (3) with rebase
  │
  └─ back to .analyze_file_content() (re-review) → post follow-up comment → repeat
```

### Agent flow (local Claude Code session)

No `pr_mr_orchestrator.py` here — there's no PR/MR to fetch files from or
comment on, so the agent calls the other four scripts directly:

```
1. detect_framework.py       (python3 detect_framework.py, REPO_ROOT=<repo>)
     → prints the resolved skill list

2. deterministic_review.py   (REVIEW_MODE=local python3 deterministic_review.py, REPO_ROOT=<repo>)
     → calls detect_framework.resolve() internally
     → calls .load_patterns() → imports each skill's scripts/review.py
     → reads git staged + unstaged + untracked changed files directly
       (not `git diff`, so a fully staged file with no unstaged delta is
       still reviewed)
     → .analyze_file_content() per file → findings, score, review_report.md
     → NO LLM here — this is the entire "find flaws" step

3. (findings reviewed; if Critical/High findings exist, proceed to fix)

4. llm_auto_fix.py + llm_client.py
     → THE ONLY LLM STEP — fixes the findings from step 2

5. git commit + push to the current branch (llm_auto_fix.commit_and_push,
   or the agent's own git commands)
```

**Key difference between the two flows:** `pr_mr_orchestrator.py` is the only
file that knows about GitHub/GitLab (adapters, comment posting, the
iteration loop). `detect_framework.py`, `deterministic_review.py`,
`llm_auto_fix.py`, and `llm_client.py` are shared by both flows — the local
agent just calls them directly instead of through the orchestrator.

## Frameworks (composable, auto-detected)

| Standard skill | Applies when |
|----------------|--------------|
| `qa-review-core` | always — universal rules + severity/scoring model |
| `playwright-ts` | `@playwright/test` + `tsconfig.json` |
| `playwright-js` | `@playwright/test`, no TypeScript |
| `selenium-java` | Maven/Gradle project with selenium |
| `bdd-cucumber` | any `*.feature` present (added on top of the driver overlay) |

## GitHub and GitLab, same entrypoint

`pr_mr_orchestrator.py` auto-detects the platform (`GITHUB_ACTIONS`/`GITLAB_CI`/env
vars present) and uses the matching API for fetching changed files, the
head/source branch, and posting the comment.

## Dual fix engine (Claude or Copilot-family)

Set whichever you have — auto-chosen if `LLM_PROVIDER` is unset:

| Engine | Env | `LLM_PROVIDER` |
|--------|-----|----------------|
| Claude | `ANTHROPIC_API_KEY` | `claude` |
| GitHub Models (Copilot-family) | `GH_MODELS_TOKEN` | `github` |

With neither, the agent still runs the full deterministic review and
comments — it just cannot fix. Review quality is completely unaffected.

## Install

**Claude Code:**
```
/plugin marketplace add NiCE-AI-Marketplace/agentic-platform
/plugin install qa-code-review
```
Then invoke: `/plugin:qa-code-review`

**GitHub Copilot / OpenCode, or a TUI browser — via unagi:**
```bash
cd utils/unagi && ./install.sh
```

## How to use

### Local (Agent flow — review your own working tree, no PR/MR)

Ask the agent, e.g. **"Review my local/staged changes"**, **"Scan this repo"**,
or **"Which standards apply to this repo?"** — or run the scripts directly:

```bash
# 1. See which skills this repo resolves to
REPO_ROOT="$(pwd)" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_framework.py"

# 2. Review staged + unstaged changes (works even for a fully staged file,
#    where a plain `git diff` would show nothing)
REVIEW_MODE=local REPO_ROOT="$(pwd)" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deterministic_review.py"

# ...or review the whole repo
REVIEW_MODE=repo REPO_ROOT="$(pwd)" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deterministic_review.py"
```
Findings are written to `review_report.md` and printed. If Critical/High
findings exist, ask the agent to fix them — it invokes `llm_auto_fix.py` (the
only LLM step) and pushes the result to your current branch. No `AUTO_FIX`
env var is needed locally; that flag only gates the *unattended* PR/MR loop.

### PR/MR (CI — GitHub or GitLab)

Ask the agent, e.g. **"Review and fix PR #123"** (GitHub) or
**"Review and fix MR !7"** (GitLab) — or wire it into CI directly:

```bash
# GitHub
GITHUB_REPOSITORY="owner/repo" PR_NUMBER="123" GITHUB_TOKEN="..." REPO_ROOT="$(pwd)" \
AUTO_FIX="true" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr_mr_orchestrator.py"

# GitLab
CI_PROJECT_ID="456" CI_MERGE_REQUEST_IID="7" GITLAB_API_URL="https://gitlab.example.com/api/v4" \
GITLAB_PERSONAL_ACCESS_TOKEN="..." REPO_ROOT="$(pwd)" \
AUTO_FIX="true" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr_mr_orchestrator.py"
```
The platform is auto-detected from the env vars present. This posts one
review comment, then — if `AUTO_FIX=true` and the score is below
`SCORE_THRESHOLD` — fixes, pushes, and re-reviews, up to `MAX_FIX_ITERATIONS`
(default 3) times. See
[agents/qa-code-review.agent.md](agents/qa-code-review.agent.md) for the full
Request → Script mapping and every configuration variable.

## Guardrails (retries capped at 3, every level)

- **PR/MR-level**: `MAX_FIX_ITERATIONS` (default 3) review→fix→re-review rounds, stop at `SCORE_THRESHOLD` (default 80).
- **API/push-level**: `API_MAX_RETRIES` (default 3) for transient GitHub/GitLab API calls and the fix-commit push.
- **Agent-level**: the local Claude Code agent flow retries a failed detect→review→fix→push attempt up to 3 times total.
- **Verify-before-commit gate** — deterministic Critical/High can only decrease.

Every PR/MR always goes through the full review→findings→comment→LLM fix→re-review
loop, up to `MAX_FIX_ITERATIONS` (default 3), regardless of who authored the head
commit — including a prior auto-fix commit from the bot itself.

## Author

Abhijeet Dhumal ([@nice-abhijeet-dhumal](https://github.com/nice-abhijeet-dhumal))
