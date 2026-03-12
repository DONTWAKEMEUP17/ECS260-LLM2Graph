"""
Auto pipeline: processes all test_case pairs and saves each graph to output/<name>.json
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from main import extract_graph

OUTPUT_DIR = Path("output")
TEST_CASE_DIR = Path("test_case")


def parse_sources(py_file: Path, txt_file: Path) -> dict:
    """Build a {basename: content} dict for snippet lookup.
    Handles both plain .py files and multi-file SWE-bench files with [FILE: ...] headers."""
    sources = {}
    txt_content = txt_file.read_text(encoding="utf-8")
    sources[txt_file.name] = txt_content

    py_content = py_file.read_text(encoding="utf-8")
    # Detect multi-file format (SWE-bench): starts with "[FILE: ...]"
    if py_content.lstrip().startswith("[FILE:"):
        import re
        parts = re.split(r"\[FILE:\s*(.+?)\]\n", py_content)
        # parts = ["", filename, content, filename, content, ...]
        it = iter(parts[1:])
        for fname, content in zip(it, it):
            sources[fname.strip().split("/")[-1]] = content  # basename only
    else:
        sources[py_file.name] = py_content

    return sources


def load_pairs(data_dir: Path) -> dict:
    pairs = {}
    py_files = {f.stem: f for f in data_dir.glob("*.py")}
    txt_files = {f.stem: f for f in data_dir.glob("*.txt")}

    for py_stem, py_file in py_files.items():
        txt_file = txt_files.get(f"test_{py_stem}") or txt_files.get(py_stem)
        if txt_file:
            py_content = py_file.read_text(encoding="utf-8")
            txt_content = txt_file.read_text(encoding="utf-8")
            combined = (
                f"[CODE FILE: {py_file.name}]\n{py_content}\n\n"
                f"[OUTPUT FILE: {txt_file.name}]\n{txt_content}"
            )
            sources = parse_sources(py_file, txt_file)
            pairs[py_stem] = {"py": py_file.name, "txt": txt_file.name, "content": combined, "sources": sources}
    return pairs


def to_cyto(out, sources: dict = None) -> dict:
    data = out.model_dump(mode="json")
    result = {
        "text": data["text"],
        "sources": sources or {},
        "elements": {
            "nodes": [
                {
                    "data": {
                        "id": n["id"],
                        "label": n["text"],
                        "type": n["type"],
                        "source": n.get("source"),
                        "confidence": n.get("confidence"),
                    }
                }
                for n in data["graph"]["nodes"]
            ],
            "edges": [
                {
                    "data": {
                        "id": f'{e["type"]}:{e["source"]}->{e["target"]}',
                        "source": e["source"],
                        "target": e["target"],
                        "type": e["type"],
                    }
                }
                for e in data["graph"]["edges"]
            ],
        },
    }
    return result


def run_pipeline(data_dir: Path = TEST_CASE_DIR, output_dir: Path = OUTPUT_DIR):
    pairs = load_pairs(data_dir)
    if not pairs:
        print(f"No pairs found in {data_dir}/")
        sys.exit(1)

    output_dir.mkdir(exist_ok=True)
    print(f"Found {len(pairs)} pair(s): {', '.join(pairs)}\n")

    results = {}
    for name, pair in pairs.items():
        print(f"[{name}] Processing {pair['py']} + {pair['txt']} ...")
        try:
            print(f"[{name}] Calling LLM (timeout: 90s)...")
            out = extract_graph(pair["content"])
            cyto = to_cyto(out, pair.get("sources"))
            out_path = output_dir / f"{name}.json"
            out_path.write_text(json.dumps(cyto, indent=2, ensure_ascii=False), encoding="utf-8")
            node_count = len(cyto["elements"]["nodes"])
            edge_count = len(cyto["elements"]["edges"])
            print(f"[{name}] Done — {node_count} nodes, {edge_count} edges -> {out_path}\n")
            results[name] = {"status": "ok", "nodes": node_count, "edges": edge_count}
        except Exception as e:
            print(f"[{name}] ERROR: {e}\n")
            results[name] = {"status": "error", "error": str(e)}

    # Summary
    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for name, r in results.items():
        if r["status"] == "ok":
            print(f"  {name}: {r['nodes']} nodes, {r['edges']} edges")
        else:
            print(f"  {name}: FAILED — {r['error']}")

    # Also write a combined manifest
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nManifest saved to {manifest_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=str(TEST_CASE_DIR), help="Input directory (default: test_case)")
    parser.add_argument("--out", default=str(OUTPUT_DIR), help="Output directory (default: output)")
    args = parser.parse_args()
    run_pipeline(Path(args.dir), Path(args.out))
