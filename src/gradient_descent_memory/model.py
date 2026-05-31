from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


SCOPES = {"repo", "global"}
OPERATIONS = {"add", "replace", "delete"}


@dataclass(frozen=True)
class ProposalDraft:
    id: str
    scope: str
    operation: str
    text_gradient: str
    memory: str
    confidence: float
    evidence: list[str]
    target_memory: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "scope": self.scope,
            "operation": self.operation,
            "text_gradient": self.text_gradient,
            "memory": self.memory,
            "target_memory": self.target_memory,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


def normalize_memory(memory: str) -> str:
    return re.sub(r"\s+", " ", memory.strip().lower())


def proposal_id(scope: str, operation: str, memory: str, target_memory: str = "") -> str:
    payload = "|".join([scope, operation, normalize_memory(memory), normalize_memory(target_memory)])
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return f"mg_{scope}_{digest[:12]}"
