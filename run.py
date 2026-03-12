"""
One-command launcher:
  python run.py              # process test_case/ and open browser
  python run.py --swe        # also fetch & process SWE-bench cases
  python run.py --dir <path> # process a custom directory
"""
from __future__ import annotations

import argparse
import os
import sys
import subprocess
import webbrowser
import time
import threading
import http.server
import socketserver
from pathlib import Path


PORT = 8000


# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

def ensure_deps():
    try:
        import openai, pydantic, requests  # noqa: F401
    except ImportError:
        print("Installing dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"])
        print("Dependencies installed.\n")


# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------

def ensure_api_key():
    # Try .env file first
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    os.environ["OPENAI_API_KEY"] = key
                    break

    if os.environ.get("OPENAI_API_KEY"):
        return

    print("OPENAI_API_KEY is not set.")
    key = input("Enter your OpenAI API key (or press Enter to skip graph generation): ").strip()
    if key:
        os.environ["OPENAI_API_KEY"] = key
        save = input("Save to .env for next time? [y/N]: ").strip().lower()
        if save == "y":
            env_file.write_text(f'OPENAI_API_KEY="{key}"\n')
            print("Saved to .env\n")
    else:
        print("Skipping graph generation — will serve existing output files only.\n")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(input_dir: str, output_dir: str):
    if not os.environ.get("OPENAI_API_KEY"):
        print(f"[pipeline] Skipping {input_dir} (no API key).")
        return
    print(f"\n[pipeline] Processing {input_dir}/ → {output_dir}/")
    result = subprocess.run(
        [sys.executable, "pipeline.py", "--dir", input_dir, "--out", output_dir],
        check=False,
    )
    if result.returncode != 0:
        print(f"[pipeline] Finished with errors (exit {result.returncode}).")


def fetch_swe(output_dir: str):
    if not os.environ.get("OPENAI_API_KEY"):
        print("[swe] Skipping (no API key).")
        return
    swe_dir = Path("swe_cases")
    if not swe_dir.exists() or not list(swe_dir.glob("*.py")):
        print("\n[swe] Fetching SWE-bench cases...")
        result = subprocess.run([sys.executable, "fetch_swe_cases.py"], check=False)
        if result.returncode != 0:
            print("[swe] fetch_swe_cases.py failed — skipping SWE cases.")
            return
    else:
        print(f"\n[swe] swe_cases/ already exists ({len(list(swe_dir.glob('*.py')))} cases), skipping fetch.")

    run_pipeline("swe_cases", output_dir)


# ---------------------------------------------------------------------------
# Merge manifests so the viewer shows all cases in one dropdown
# ---------------------------------------------------------------------------

def merge_manifests(dirs: list[str]):
    import json
    combined = {}
    for d in dirs:
        mf = Path(d) / "manifest.json"
        if mf.exists():
            data = json.loads(mf.read_text())
            for k, v in data.items():
                combined[k] = {**v, "_dir": d}

    # Write a merged manifest that index.html can read
    # index.html currently reads output/manifest.json — write a merged one there
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)

    # Copy all json graph files into output/ with dir-prefixed names
    for d in dirs:
        if d == "output":
            continue
        src_dir = Path(d)
        for jf in src_dir.glob("*.json"):
            if jf.name == "manifest.json":
                continue
            dest = out_dir / f"{src_dir.name}__{jf.name}"
            dest.write_bytes(jf.read_bytes())
            # update manifest key
            stem = jf.stem
            if stem in combined and combined[stem].get("_dir") == d:
                combined[f"{src_dir.name}__{stem}"] = combined.pop(stem)

    merged_path = out_dir / "manifest.json"
    merged_path.write_text(json.dumps(combined, indent=2))
    print(f"\n[merge] Combined manifest: {len(combined)} graphs → {merged_path}")


# ---------------------------------------------------------------------------
# HTTP server + browser
# ---------------------------------------------------------------------------

def serve_and_open():
    os.chdir(Path(__file__).parent)

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass  # suppress per-request logs

    with socketserver.TCPServer(("", PORT), QuietHandler) as httpd:
        url = f"http://localhost:{PORT}/index.html"
        print(f"\nServing at {url}")
        print("Press Ctrl+C to stop.\n")

        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LLM2Graph one-command launcher")
    parser.add_argument("--swe", action="store_true", help="Also fetch and process SWE-bench Lite cases")
    parser.add_argument("--dir", default=None, help="Process a custom input directory instead of test_case/")
    parser.add_argument("--no-pipeline", action="store_true", help="Skip pipeline, just serve existing output")
    args = parser.parse_args()

    ensure_deps()
    ensure_api_key()

    if not args.no_pipeline:
        if args.dir:
            run_pipeline(args.dir, "output")
        else:
            run_pipeline("test_case", "output")
            if args.swe:
                fetch_swe("output_swe")
                merge_manifests(["output", "output_swe"])

    serve_and_open()


if __name__ == "__main__":
    main()
