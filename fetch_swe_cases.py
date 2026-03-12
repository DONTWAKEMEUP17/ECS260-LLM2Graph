"""
Fetch 8-10 realistic cases from SWE-bench Lite and format them for the pipeline.

Output (in swe_cases/):
  <slug>.py          — buggy source files concatenated with [FILE: ...] headers
  test_<slug>.txt    — GitHub issue description + failing test names + diff

Then run:  python pipeline.py --dir swe_cases
"""
from __future__ import annotations

import re
import time
import json
import os
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OUT_DIR = Path("swe_cases")

# Curated instance_ids from SWE-bench Lite:
# Criteria: 1-3 files changed, well-known small repos, clear bug description
TARGET_INSTANCES = [
    "psf__requests-2317",    # requests: wrong exception type on invalid URL
    "psf__requests-3362",    # requests: PreparedRequest copy loses headers
    "pallets__flask-4045",   # flask: blueprint url_prefix ignored in some cases
    "pallets__flask-4935",   # flask: redirect loop with double slash
    "pytest-dev__pytest-5103", # pytest: marker filtering regression
    "pytest-dev__pytest-7168", # pytest: --co crash on import error
    "pypa__pip-9135",          # pip: incorrect requirement marker evaluation
    "django__django-13710",    # django: QuerySet.bulk_create() ignores update_fields
    "sympy__sympy-13177",      # sympy: wrong simplification of Abs
    "matplotlib__matplotlib-23913",  # matplotlib: colorbar crash on log scale
]

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")  # optional, avoids rate limits
HF_DATASET_URL = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=princeton-nlp%2FSWE-bench_Lite&config=default&split=test&offset=0&length=300"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def gh_headers() -> dict:
    h = {"Accept": "application/vnd.github.v3.raw"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


def fetch_file_at_commit(repo: str, path: str, commit: str) -> str | None:
    """Fetch a single file from GitHub at a specific commit."""
    url = f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"
    for attempt in range(3):
        r = requests.get(url, headers=gh_headers(), timeout=15)
        if r.status_code == 200:
            return r.text
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 30))
            print(f"    Rate limited — waiting {wait}s …")
            time.sleep(wait)
        elif r.status_code == 404:
            return None
        else:
            time.sleep(2)
    return None


def parse_patch_files(patch: str) -> list[str]:
    """Extract file paths from a unified diff patch."""
    paths = []
    for line in patch.splitlines():
        # +++ b/path/to/file.py
        if line.startswith("+++ b/"):
            p = line[6:].strip()
            if p != "/dev/null" and p.endswith(".py"):
                paths.append(p)
    return list(dict.fromkeys(paths))  # deduplicate, preserve order


def truncate(text: str, max_chars: int = 6000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [truncated at {max_chars} chars]"


def load_swebench_lite() -> list[dict]:
    """Load SWE-bench Lite rows from HuggingFace dataset server."""
    print("Loading SWE-bench Lite from HuggingFace …")
    rows = []
    offset = 0
    length = 100
    while True:
        url = (
            "https://datasets-server.huggingface.co/rows"
            f"?dataset=princeton-nlp%2FSWE-bench_Lite&config=default&split=test"
            f"&offset={offset}&length={length}"
        )
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            print(f"  HuggingFace API error {r.status_code}. Trying alternate URL...")
            # fallback: try the resolve endpoint
            break
        data = r.json()
        batch = [row["row"] for row in data.get("rows", [])]
        rows.extend(batch)
        if len(batch) < length:
            break
        offset += length
        time.sleep(0.5)
    print(f"  Loaded {len(rows)} instances.")
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_instance(instance: dict) -> bool:
    slug = instance["instance_id"].replace("/", "__")
    repo = instance["repo"]          # e.g. "psf/requests"
    base_commit = instance["base_commit"]
    patch = instance.get("patch", "")
    problem = instance.get("problem_statement", "").strip()
    fail_tests = instance.get("FAIL_TO_PASS", [])
    pass_tests = instance.get("PASS_TO_PASS", [])

    print(f"\n[{slug}]")
    print(f"  repo={repo}  commit={base_commit[:8]}")

    # --- find changed Python files ---
    changed_files = parse_patch_files(patch)
    if not changed_files:
        print("  No Python files in patch — skipping.")
        return False
    if len(changed_files) > 5:
        # keep only the first 5 to avoid context explosion
        changed_files = changed_files[:5]
    print(f"  Changed files: {changed_files}")

    # --- fetch file contents at base commit ---
    file_sections = []
    for fpath in changed_files:
        content = fetch_file_at_commit(repo, fpath, base_commit)
        if content is None:
            print(f"  Could not fetch {fpath} — skipping file.")
            continue
        file_sections.append(f"[FILE: {fpath}]\n{truncate(content)}")
        time.sleep(0.3)

    if not file_sections:
        print("  No files fetched — skipping instance.")
        return False

    # --- build code file (saved as .py so pipeline.py picks it up) ---
    code_text = "\n\n".join(file_sections)

    # --- build test/issue output file ---
    fail_list = "\n".join(f"  FAIL  {t}" for t in (fail_tests if isinstance(fail_tests, list) else [fail_tests]))
    pass_list = "\n".join(f"  PASS  {t}" for t in (pass_tests if isinstance(pass_tests, list) else [pass_tests])[:5])

    test_text = (
        f"[ISSUE / BUG REPORT]\n{problem}\n\n"
        f"[FAILING TESTS]\n{fail_list or '(none listed)'}\n\n"
        f"[PASSING TESTS (sample)]\n{pass_list or '(none listed)'}\n\n"
        f"[PATCH DIFF]\n{truncate(patch, 3000)}"
    )

    # --- write outputs ---
    OUT_DIR.mkdir(exist_ok=True)
    code_path = OUT_DIR / f"{slug}.py"
    test_path = OUT_DIR / f"test_{slug}.txt"
    code_path.write_text(code_text, encoding="utf-8")
    test_path.write_text(test_text, encoding="utf-8")
    print(f"  Saved: {code_path.name}  +  {test_path.name}")
    return True


def main():
    instances = load_swebench_lite()
    if not instances:
        print("Failed to load dataset. Check your internet connection.")
        sys.exit(1)

    # index by instance_id
    by_id = {row["instance_id"]: row for row in instances}

    saved = 0
    skipped = []
    for iid in TARGET_INSTANCES:
        if iid not in by_id:
            print(f"\n[{iid}] Not found in dataset — skipping.")
            skipped.append(iid)
            continue
        ok = process_instance(by_id[iid])
        if ok:
            saved += 1

    print("\n" + "=" * 50)
    print(f"Done. {saved} cases saved to {OUT_DIR}/")
    if skipped:
        print(f"Skipped (not in dataset): {skipped}")
    print(f"\nNext step:")
    print(f"  python pipeline.py --dir swe_cases")


if __name__ == "__main__":
    main()
