from __future__ import annotations

from enum import Enum
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from openai import OpenAI
import json
import os
import sys
from pathlib import Path

client = OpenAI(timeout=60.0, max_retries=2)


# ---------- Schema (Strongly constrained) ----------

class NodeType(str, Enum):
    CLAIM = "Claim"
    EVIDENCE = "Evidence"
    ASSUMPTION = "Assumption"  # Assumption / Uncertainty


class EdgeType(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DEPENDS_ON = "depends-on"
    IMPLIES = "implies"


class Node(BaseModel):
    id: str = Field(..., description="Unique node id, e.g., c1, e2, a1")
    type: NodeType
    text: str = Field(..., min_length=1, description="Human-readable content")
    source: Optional[str] = Field(
        default=None,
        description="Optional provenance, e.g., 'code:L12-L18', 'test:stderr', 'log', 'spec', etc."
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional confidence in [0,1]"
    )

    @field_validator("id")
    @classmethod
    def id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("id must be non-empty")
        return v


class Edge(BaseModel):
    source: str = Field(..., description="source node id")
    target: str = Field(..., description="target node id")
    type: EdgeType


class ReasoningGraph(BaseModel):
    nodes: List[Node] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> "ReasoningGraph":
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate node ids are not allowed")

        id_set = set(ids)
        for e in self.edges:
            if e.source not in id_set:
                raise ValueError(f"Edge source '{e.source}' not found in nodes")
            if e.target not in id_set:
                raise ValueError(f"Edge target '{e.target}' not found in nodes")

        return self

        return self
        return values


class Output(BaseModel):
    text: str = Field(..., description="Short readable explanation")
    graph: ReasoningGraph


# ---------- Call model with strong schema parsing ----------

def extract_graph(user_text: str) -> Output:
    response = client.responses.parse(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "system",
                "content": (
                    "You are an information extraction engine.\n"
                    "Return a concise explanation in `text` and a reasoning graph in `graph`.\n"
                    "Node types: Claim, Evidence, Assumption.\n"
                    "Edge types: supports, contradicts, depends-on, implies.\n"
                    "Use short ids: c1,c2 for claims; e1,e2 for evidence; a1,a2 for assumptions.\n"
                    "Only create edges that are justified by the input.\n"
                    "In the `source` field, always reference the exact file and line range using the format "
                    "`filename:L<start>-L<end>` (e.g. `bucketsort.py:L12-L18`) or `filename:L<line>` for a single line. "
                    "For test output references use the test filename with the same format (e.g. `test_bucketsort.txt:L3-L7`). "
                    "Use the shortest unambiguous filename (basename only, not full path)."
                ),
            },
            {"role": "user", "content": user_text},
        ],
        text_format=Output,  # <-- strong constraint
    )
    return response.output_parsed


def load_sample_pairs(data_dir: str = "data") -> dict:
    """Load paired .py and .txt files from data directory."""
    pairs = {}
    data_path = Path(data_dir)
    
    if not data_path.exists():
        print(f"Data directory not found: {data_dir}")
        return pairs
    
    # Find all .py files and their corresponding .txt files
    py_files = {f.stem: f for f in data_path.glob("*.py")}
    txt_files = {f.stem: f for f in data_path.glob("*.txt")}
    
    # Match .py with .txt (handle test_ prefix in txt files)
    for py_stem, py_file in py_files.items():
        # Try to find matching txt file
        txt_file = None
        
        # Check for "test_<name>.txt"
        if f"test_{py_stem}" in txt_files:
            txt_file = txt_files[f"test_{py_stem}"]
        # Check for "<name>.txt" (direct match)
        elif py_stem in txt_files:
            txt_file = txt_files[py_stem]
        
        if txt_file:
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    py_content = f.read()
                with open(txt_file, "r", encoding="utf-8") as f:
                    txt_content = f.read()
                
                # Combine both contents
                combined = f"[CODE FILE: {py_file.name}]\n{py_content}\n\n[OUTPUT FILE: {txt_file.name}]\n{txt_content}"
                pairs[py_stem] = {
                    "py_file": py_file.name,
                    "txt_file": txt_file.name,
                    "content": combined
                }
                print(f"Loaded pair: {py_file.name} + {txt_file.name}")
            except Exception as e:
                print(f"Error loading pair {py_stem}: {e}")
    
    return pairs


def process_sample(sample_text: str, output_file: str = "cyto.json") -> dict:
    """Process a sample and generate cyto.json format."""
    out = extract_graph(sample_text)
    data = out.model_dump(mode="json")

    cyto = {
        "text": data["text"],
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
        }
    }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(cyto, f, indent=2, ensure_ascii=False)
    
    return cyto


if __name__ == "__main__":
    pairs = load_sample_pairs("data")
    
    if not pairs:
        print("No matching .py and .txt file pairs found in data/")
        sys.exit(1)
    
    # List available pairs
    pair_names = list(pairs.keys())
    print(f"\nAvailable sample pairs ({len(pair_names)}):")
    for i, name in enumerate(pair_names, 1):
        py_file = pairs[name]["py_file"]
        txt_file = pairs[name]["txt_file"]
        print(f"  {i}. {py_file} + {txt_file}")
    
    # Get user choice
    if len(pair_names) == 1:
        choice = 1
        print(f"\nProcessing: {pair_names[0]}")
    else:
        try:
            choice = int(input(f"\nSelect a pair (1-{len(pair_names)}): "))
            if not (1 <= choice <= len(pair_names)):
                print(f"Invalid choice. Using pair 1.")
                choice = 1
        except ValueError:
            print("Invalid input. Using pair 1.")
            choice = 1
    
    selected_pair = pair_names[choice - 1]
    pair_data = pairs[selected_pair]
    
    print(f"\nProcessing: {pair_data['py_file']} + {pair_data['txt_file']}")
    print(f"Combined content length: {len(pair_data['content'])} characters\n")
    
    process_sample(pair_data["content"], "cyto.json")
    print(f"cyto.json exported successfully.")

