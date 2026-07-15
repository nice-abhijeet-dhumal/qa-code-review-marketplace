#!/usr/bin/env python3
"""
Framework dispatcher.

Detects which QA automation framework(s) a repository uses and returns the
ordered, composable set of skills that apply. Skills layer:

    qa-review-core            (always)
    + one driver overlay      (playwright-ts | playwright-js | selenium-java)
    + bdd-cucumber            (additive, when .feature files are present)

The selected skill bodies are concatenated and handed to the LLM review/fix
layers as the review standard. This is the single place framework knowledge is
resolved, so the same detection drives Layer 1 config, the LLM prompt, and the
provider adapters.
"""

import os
from pathlib import Path
from typing import List, Optional

SKILLS_DIRNAME = "skills"

# Driver overlays, checked in priority order. Each entry:
#   (skill_name, detector) where detector(repo_root) -> bool
def _has(repo: Path, *relpaths: str) -> bool:
    return any((repo / p).exists() for p in relpaths)


def _file_contains(repo: Path, relpath: str, needle: str) -> bool:
    p = repo / relpath
    if not p.is_file():
        return False
    try:
        return needle in p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def _glob_any(repo: Path, pattern: str) -> bool:
    return next(repo.rglob(pattern), None) is not None


def detect_frameworks(repo_root: str) -> List[str]:
    """Return the ordered list of skill names that apply to this repo."""
    repo = Path(repo_root).resolve()
    skills: List[str] = ["qa-review-core"]

    is_node = (repo / "package.json").is_file()
    uses_playwright = is_node and _file_contains(repo, "package.json", "@playwright/test")
    has_tsconfig = (repo / "tsconfig.json").is_file()
    is_java = _has(repo, "pom.xml", "build.gradle", "build.gradle.kts")
    uses_selenium = (
        _file_contains(repo, "pom.xml", "selenium")
        or _file_contains(repo, "build.gradle", "selenium")
        or _file_contains(repo, "build.gradle.kts", "selenium")
    )

    # Driver overlay (pick one)
    if uses_playwright and has_tsconfig:
        skills.append("playwright-ts")
    elif uses_playwright:
        skills.append("playwright-js")
    elif is_java and uses_selenium:
        skills.append("selenium-java")
    elif is_java:
        # Java project without an obvious selenium dep: still closest overlay.
        skills.append("selenium-java")

    # BDD overlay (additive)
    if _glob_any(repo, "*.feature"):
        skills.append("bdd-cucumber")

    return skills


def plugin_skills_dir() -> Path:
    """The plugin's skills/ dir, where the framework standards live.

    This script sits at <plugin>/skills/review-engine/scripts/, so the skills
    dir is two levels up. The standards are loaded from HERE, independently of
    REPO_ROOT (which points at the repo under review, not the plugin).
    """
    return Path(__file__).resolve().parents[2]


def load_skills(repo_root: str, skill_names: List[str],
                skills_dir: Optional[str] = None) -> str:
    """Concatenate the SKILL.md bodies for the given skill names."""
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
