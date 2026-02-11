from __future__ import annotations

from enum import Enum
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from openai import OpenAI
import json

client = OpenAI()


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

        # Optional semantic constraints (tighten rules)
        # supports/contradicts: Evidence -> Claim (common case)
        # depends-on: Claim -> Assumption
        # implies: Claim -> Claim
        # node_type = {n.id: n.type for n in self.nodes}
        # for e in self.edges:
        #     s, t, et = e.source, e.target, e.type
        #     if et in (EdgeType.SUPPORTS, EdgeType.CONTRADICTS):
        #         if not (node_type[s] == NodeType.EVIDENCE and node_type[t] == NodeType.CLAIM):
        #             raise ValueError(f"{et} should be Evidence -> Claim, got {node_type[s]} -> {node_type[t]}")
        #     if et == EdgeType.DEPENDS_ON:
        #         if not (node_type[s] == NodeType.CLAIM and node_type[t] == NodeType.ASSUMPTION):
        #             raise ValueError(f"depends-on should be Claim -> Assumption, got {node_type[s]} -> w{node_type[t]}")
        #     if et == EdgeType.IMPLIES:
        #         if not (node_type[s] == NodeType.CLAIM and node_type[t] == NodeType.CLAIM):
        #             raise ValueError(f"implies should be Claim -> Claim, got {node_type[s]} -> {node_type[t]}")

        return self


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
                    "Only create edges that are justified by the input."
                ),
            },
            {"role": "user", "content": user_text},
        ],
        text_format=Output,  # <-- strong constraint
    )
    return response.output_parsed


if __name__ == "__main__":
    sample = (
        "Bug report: tests fail when n=0.\n"
        "Code: for i in range(n+1): arr[i] += 1\n"
        "Error: IndexError: list index out of range\n"
        "I think it's an off-by-one bug."
    )

    out = extract_graph(sample)
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
    with open("cyto.json", "w", encoding="utf-8") as f:
        json.dump(cyto, f, indent=2, ensure_ascii=False)

    print("cyto.json exported successfully.")

