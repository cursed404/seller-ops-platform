from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from app.domain.schemas import Citation


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class KnowledgeBaseService:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self._documents = documents

    def search(self, *, incident_type: str, query_text: str, limit: int = 3) -> list[dict[str, Any]]:
        query_tokens = tokenize(f"{incident_type} {query_text}")
        query_counter = Counter(query_tokens)
        scored: list[tuple[float, dict[str, Any]]] = []
        for document in self._documents:
            haystack = " ".join(
                [
                    document["title"],
                    document["category"],
                    document["body"],
                    " ".join(document.get("tags", [])),
                ]
            )
            doc_counter = Counter(tokenize(haystack))
            overlap = sum(min(query_counter[token], doc_counter[token]) for token in query_counter)
            if incident_type in document["category"] or incident_type in document["slug"]:
                overlap += 4
            if overlap == 0:
                continue
            magnitude = math.sqrt(sum(value * value for value in doc_counter.values())) or 1.0
            score = overlap / magnitude
            excerpt = document["body"][:240].strip()
            citation = Citation(
                document_id=document["id"],
                slug=document["slug"],
                title=document["title"],
                excerpt=excerpt,
                score=round(score, 4),
            )
            scored.append((score, {"document": document, "citation": citation.model_dump(mode="json")}))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

