#!/usr/bin/env python3
"""
playwright-ts -- deterministic patterns (Layer 1).

Applied ON TOP of qa-review-core when the repo uses @playwright/test WITH
TypeScript. Runtime rules are identical to playwright-js (same Playwright
API, same async pitfalls) so this module re-exports that skill's patterns and
adds only the TypeScript-specific ones. No LLM involved.
"""

import importlib.util
from pathlib import Path

# Reuse playwright-js's patterns rather than duplicating them -- the two
# skills share the exact same runtime (Playwright) API surface.
_js_review_path = Path(__file__).resolve().parents[2] / "playwright-js" / "scripts" / "review.py"
_spec = importlib.util.spec_from_file_location("_playwright_js_review", _js_review_path)
_playwright_js = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_playwright_js)

CRITICAL_PATTERNS = list(_playwright_js.CRITICAL_PATTERNS)
HIGH_PATTERNS = list(_playwright_js.HIGH_PATTERNS)
MEDIUM_PATTERNS = list(_playwright_js.MEDIUM_PATTERNS) + [
    # TypeScript-only: defeats type safety.
    (r":\s*any\b", "TypeScript 'any' type detected -- use specific types to maintain type safety"),
    (r"as\s+any\b", "TypeScript 'as any' cast detected -- use proper typing instead"),

    # TypeScript-only: page: Page passed as a parameter to a helper.
    (r"(function|const)\s+\w+\s*\([^)]*\bpage\s*:\s*Page\b", "page: Page passed as parameter to helper -- consider using a fixture or POM method instead"),
]
LOW_PATTERNS = list(_playwright_js.LOW_PATTERNS)
