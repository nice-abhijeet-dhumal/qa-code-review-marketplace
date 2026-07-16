#!/usr/bin/env python3
"""
Framework dispatcher.

Detects which QA automation framework(s) a repository uses and returns the
ordered, composable set of skills that apply. Skills layer:

    qa-review-core            (always)
    + one driver overlay      (playwright-ts | playwright-js | selenium-java)
    + bdd-cucumber            (additive, when .feature files are present)

Each selected skill owns its own `scripts/review.py` (see
`deterministic_review.py`, which loads and merges them). This module ONLY
resolves which skills apply and loads their `SKILL.md` bodies (used as LLM
fix-context, never for review).

Detection scans the repo root AND its immediate subdirectories (depth 1), not
just the root. Multi-package layouts -- a root `package.json` with no test
dependencies plus the real Playwright/Selenium project nested one level down
(e.g. `ui/package.json`, `api/package.json`, `ui/tsconfig.json`) -- are common
in this org's repos and were previously invisible to root-only checks, which
silently fell back to `qa-review-core` with NO driver overlay at all.
"""

import os
from pathlib import Path
from typing import List, Optional

SKILLS_DIRNAME = "skills"

# Directories never worth descending into when looking for a nested project.
_SKIP_SUBDIRS = {
    "node_modules", "dist", "build", "target", "out",
    "allure-results", "playwright-report", "test-results",
}


def _candidate_dirs(repo: Path) -> List[Path]:
    """Repo root plus its immediate subdirectories, root first.

    Covers the common `ui/`, `api/`, `web/` monorepo split where the root
    package.json/tsconfig.json/build file is a stub and the real framework
    dependency lives one level down.
    """
    candidates = [repo]
    try:
        for child in sorted(repo.iterdir()):
            if child.is_dir() and not child.name.startswith(".") and child.name not in _SKIP_SUBDIRS:
                candidates.append(child)
    except OSError:
        pass
    return candidates


def _file_contains(path: Path, needle: str) -> bool:
    if not path.is_file():
        return False
    try:
        return needle in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def _glob_any(repo: Path, pattern: str) -> bool:
    return next(repo.rglob(pattern), None) is not None


def _find_playwright_project(repo: Path) -> Optional[dict]:
    """First dir (root-first, then immediate subdirs) whose package.json
    declares @playwright/test. Returns {'dir', 'has_tsconfig'} or None."""
    for d in _candidate_dirs(repo):
        if _file_contains(d / "package.json", "@playwright/test"):
            has_ts = (d / "tsconfig.json").is_file() or _glob_any(d, "playwright.config.ts")
            return {"dir": d, "has_tsconfig": has_ts}
    return None


def _find_java_project(repo: Path) -> Optional[dict]:
    """First dir with a Maven/Gradle build file. Returns {'dir', 'uses_selenium'} or None."""
    for d in _candidate_dirs(repo):
        for name in ("pom.xml", "build.gradle", "build.gradle.kts"):
            build_file = d / name
            if build_file.is_file():
                return {"dir": d, "uses_selenium": _file_contains(build_file, "selenium")}
    return None


def detect_frameworks(repo_root: str) -> List[str]:
    """Return the ordered list of skill names that apply to this repo."""
    repo = Path(repo_root).resolve()
    skills: List[str] = ["qa-review-core"]

    playwright = _find_playwright_project(repo)
    java = _find_java_project(repo)

    # Driver overlay (pick one). A matched Playwright dependency is a more
    # specific signal than a bare Java build file, so it wins if both exist.
    if playwright:
        skills.append("playwright-ts" if playwright["has_tsconfig"] else "playwright-js")
    elif java:
        # Java project without an obvious selenium dep: still closest overlay.
        skills.append("selenium-java")

    # BDD overlay (additive)
    if _glob_any(repo, "*.feature"):
        skills.append("bdd-cucumber")

    return skills


def plugin_skills_dir() -> Path:
    """The plugin's skills/ dir, where the standards + scripts live.

    This script sits at <plugin>/skills/review-engine/scripts/, so the skills
    dir is two levels up. Standards are loaded from HERE, independently of
    REPO_ROOT (which points at the repo under review, not the plugin).
    """
    return Path(__file__).resolve().parents[2]


def load_skills(repo_root: str, skill_names: List[str],
                skills_dir: Optional[str] = None) -> str:
    """Concatenate the SKILL.md bodies for the given skill names.

    Used ONLY as fix-context for the LLM auto-fix layer -- review findings
    never come from this text, only from each skill's scripts/review.py
    (deterministic_review.py).
    """
    base = Path(skills_dir) if skills_dir else plugin_skills_dir()
    parts: List[str] = []
    for name in skill_names:
        skill_file = base / name / "SKILL.md"
        if skill_file.is_file():
            parts.append(f"# ===== SKILL: {name} =====\n"
                         + skill_file.read_text(encoding="utf-8", errors="ignore"))
        else:
            parts.append(f"# ===== SKILL: {name} (not found at {skill_file}) =====")
    return "\n\n".join(parts)


def resolve(repo_root: Optional[str] = None) -> dict:
    """Detect frameworks and load the composed review standard."""
    repo_root = repo_root or os.environ.get("REPO_ROOT", ".")
    skills_dir = os.environ.get("SKILLS_DIR")
    names = detect_frameworks(repo_root)
    standard = load_skills(repo_root, names, skills_dir)
    return {"repo_root": repo_root, "skills": names, "standard": standard}


if __name__ == "__main__":
    import json
    info = resolve()
    print(json.dumps({"skills": info["skills"],
                      "repo_root": info["repo_root"],
                      "standard_chars": len(info["standard"])}, indent=2))
