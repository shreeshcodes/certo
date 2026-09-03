"""Storage layer. In-memory by default; Postgres + pgvector when DATABASE_URL is set.

The vector side is used for statute retrieval (find the rules most similar to a
clause). Embeddings come from OpenAI when a key exists, otherwise from a
deterministic hashed bag-of-words so the demo runs fully offline.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from typing import Dict, List, Optional, Tuple

from schemas import ComplianceGap, ContractDocument, RegulatoryEvent, RemediationApproval, RemediationPatch

log = logging.getLogger("certo.store")

EMBED_DIM = 256


def embed(text: str) -> List[float]:
    if os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI  # type: ignore

            resp = OpenAI().embeddings.create(model="text-embedding-3-small", input=text, dimensions=EMBED_DIM)
            return list(resp.data[0].embedding)
        except Exception as exc:
            log.warning("OpenAI embedding failed (%s); using hashed embedding", exc)
    vec = [0.0] * EMBED_DIM
    for tok in re.findall(r"[a-z0-9§$%.]+", text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % EMBED_DIM] += 1.0 if (h >> 8) % 2 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class MemoryStore:
    def __init__(self) -> None:
        self.events: Dict[str, RegulatoryEvent] = {}
        self.event_vectors: Dict[str, List[float]] = {}
        self.documents: Dict[str, ContractDocument] = {}
        self.gaps: Dict[str, ComplianceGap] = {}
        self.patches: Dict[str, RemediationPatch] = {}
        self.approvals: List[RemediationApproval] = []

    # events
    def upsert_events(self, events: List[RegulatoryEvent]) -> None:
        for e in events:
            self.events[e.event_id] = e
            self.event_vectors[e.event_id] = embed(f"{e.statute_citation} {e.summary} {e.raw_source_snippet}")

    def list_events(self, jurisdictions: Optional[List[str]] = None) -> List[RegulatoryEvent]:
        evs = list(self.events.values())
        if jurisdictions:
            evs = [e for e in evs if e.jurisdiction in jurisdictions]
        return sorted(evs, key=lambda e: (e.jurisdiction, e.statute_citation))

    def get_event(self, event_id: str) -> Optional[RegulatoryEvent]:
        return self.events.get(event_id)

    def event_by_citation(self, citation: str) -> Optional[RegulatoryEvent]:
        for e in self.events.values():
            if e.statute_citation == citation:
                return e
        return None

    def similar_events(self, text: str, k: int = 3) -> List[Tuple[RegulatoryEvent, float]]:
        q = embed(text)
        scored = [(self.events[i], cosine(q, v)) for i, v in self.event_vectors.items()]
        return sorted(scored, key=lambda t: -t[1])[:k]

    # documents / gaps / patches
    def upsert_document(self, doc: ContractDocument) -> None:
        self.documents[doc.document_id] = doc

    def get_document(self, document_id: str) -> Optional[ContractDocument]:
        return self.documents.get(document_id)

    def list_documents(self) -> List[ContractDocument]:
        return list(self.documents.values())

    def replace_gaps(self, document_id: str, gaps: List[ComplianceGap]) -> None:
        for gid in [g for g, v in self.gaps.items() if v.gap_id.startswith("gap-") and self._gap_doc(v) == document_id]:
            self.gaps.pop(gid, None)
        for g in gaps:
            self.gaps[g.gap_id] = g
            self._gap_docs[g.gap_id] = document_id

    _gap_docs: Dict[str, str] = {}

    def _gap_doc(self, gap: ComplianceGap) -> Optional[str]:
        return self._gap_docs.get(gap.gap_id)

    def get_gap(self, gap_id: str) -> Optional[ComplianceGap]:
        return self.gaps.get(gap_id)

    def gaps_for(self, document_id: str) -> List[ComplianceGap]:
        return [g for g in self.gaps.values() if self._gap_docs.get(g.gap_id) == document_id]

    def save_patch(self, patch: RemediationPatch) -> None:
        self.patches[patch.gap_id] = patch

    def get_patch(self, gap_id: str) -> Optional[RemediationPatch]:
        return self.patches.get(gap_id)

    def record_approval(self, approval: RemediationApproval) -> None:
        self.approvals.append(approval)


class PostgresStore(MemoryStore):
    """Write-through persistence of events + embeddings to Postgres/pgvector.

    Reads still come from the in-process cache, which is hydrated from the
    table at startup, so the API stays fast and the vector search stays
    identical across both backends.
    """

    DDL = """
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE TABLE IF NOT EXISTS regulatory_events (
        event_id TEXT PRIMARY KEY,
        payload JSONB NOT NULL,
        embedding vector(256) NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT now()
    );
    CREATE TABLE IF NOT EXISTS remediation_approvals (
        id SERIAL PRIMARY KEY,
        payload JSONB NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now()
    );
    """

    def __init__(self, dsn: str) -> None:
        super().__init__()
        import psycopg  # type: ignore

        self._psycopg = psycopg
        self.dsn = dsn
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(self.DDL)
            for event_id, payload, embedding in conn.execute("SELECT event_id, payload, embedding::text FROM regulatory_events"):
                self.events[event_id] = RegulatoryEvent.model_validate(payload)
                self.event_vectors[event_id] = [float(x) for x in embedding.strip("[]").split(",")]
        log.info("PostgresStore hydrated %d events", len(self.events))

    def upsert_events(self, events: List[RegulatoryEvent]) -> None:
        super().upsert_events(events)
        with self._psycopg.connect(self.dsn, autocommit=True) as conn:
            for e in events:
                vec = "[" + ",".join(f"{x:.6f}" for x in self.event_vectors[e.event_id]) + "]"
                conn.execute(
                    "INSERT INTO regulatory_events (event_id, payload, embedding) VALUES (%s, %s::jsonb, %s::vector) "
                    "ON CONFLICT (event_id) DO UPDATE SET payload = EXCLUDED.payload, embedding = EXCLUDED.embedding, updated_at = now()",
                    (e.event_id, e.model_dump_json(), vec),
                )

    def record_approval(self, approval: RemediationApproval) -> None:
        super().record_approval(approval)
        with self._psycopg.connect(self.dsn, autocommit=True) as conn:
            conn.execute("INSERT INTO remediation_approvals (payload) VALUES (%s::jsonb)", (approval.model_dump_json(),))


def build_store() -> MemoryStore:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        try:
            return PostgresStore(dsn)
        except Exception as exc:
            log.warning("Postgres unavailable (%s); using in-memory store", exc)
    return MemoryStore()
