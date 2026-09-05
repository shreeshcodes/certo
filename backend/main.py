"""Certo API server.

    uvicorn main:app --reload --port 8000

Endpoints
    GET  /api/health
    GET  /api/events                 active regulatory events
    GET  /api/documents              seeded real contracts
    GET  /api/documents/sample       primary contract (OneMain Financial Texas loan agreement)
    POST /api/documents/parse        split raw agreement text into clauses
    GET  /api/radar                  per-state status for a document
    POST /api/ingest/statute         Agent A
    POST /api/audit/document         Agent B
    POST /api/remediate/preview      Agent C draft + judge (no side effects)
    POST /api/remediate/patch        human approval -> apply + filing package
"""
from __future__ import annotations

import logging
import os
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from agents import CertoPipeline, build_llm_client
from mock_data import SAMPLE_CONTRACT, SEED_BULLETINS, SEED_DOCUMENTS, SEED_EVENTS
from parser import parse_contract_text
from schemas import (
    AuditRequest,
    AuditResponse,
    ComplianceGap,
    ContractClause,
    ContractDocument,
    FilingPackage,
    Jurisdiction,
    JurisdictionStatus,
    ParseContractRequest,
    RegulatoryEvent,
    RemediationApproval,
    RemediationPatch,
    RemediationRequest,
    RemediationResponse,
    StatuteIngestRequest,
    StatuteIngestResponse,
)
from store import build_store

logging.basicConfig(level=os.getenv("CERTO_LOG_LEVEL", "INFO"))
log = logging.getLogger("certo.api")

RADAR_STATES: List[Jurisdiction] = ["TX", "CA", "NY"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = build_store()
    app.state.pipeline = CertoPipeline(build_llm_client())
    store = app.state.store
    if not store.list_events():
        if os.getenv("CERTO_SEED_MODE", "curated") == "extract":
            for b in SEED_BULLETINS:
                events, _ = app.state.pipeline.extractor.run(b["jurisdiction"], b["agency"], b["raw_text"], b.get("published_date"), b.get("code_name"), b.get("source_url"))
                store.upsert_events(events)
        else:
            store.upsert_events(SEED_EVENTS)
    for d in SEED_DOCUMENTS:
        store.upsert_document(d)
    log.info("Certo up: mode=%s events=%d", app.state.pipeline.mode, len(store.list_events()))
    yield


app = FastAPI(title="Certo Continuous Compliance API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CERTO_CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _store():
    return app.state.store


def _pipeline() -> CertoPipeline:
    return app.state.pipeline


def build_radar(gaps: List[ComplianceGap], events: List[RegulatoryEvent]) -> List[JurisdictionStatus]:
    crit: Dict[str, int] = defaultdict(int)
    warn: Dict[str, int] = defaultdict(int)
    ok: Dict[str, int] = defaultdict(int)
    rules: Dict[str, int] = defaultdict(int)
    for e in events:
        rules[e.jurisdiction] += 1
    for g in gaps:
        if g.severity == "CRITICAL":
            crit[g.jurisdiction] += 1
        elif g.severity == "WARNING":
            warn[g.jurisdiction] += 1
        else:
            ok[g.jurisdiction] += 1
    radar = []
    for j in RADAR_STATES:
        if rules[j] == 0:
            status = "UNKNOWN"
        elif crit[j]:
            status = "RED"
        elif warn[j]:
            status = "AMBER"
        else:
            status = "GREEN"
        radar.append(JurisdictionStatus(jurisdiction=j, status=status, critical_count=crit[j], warning_count=warn[j], compliant_count=ok[j], active_rules=rules[j]))
    return radar


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": _pipeline().mode, "events": len(_store().list_events()), "store": type(_store()).__name__}


@app.get("/api/events", response_model=List[RegulatoryEvent])
def list_events(jurisdiction: Optional[List[Jurisdiction]] = Query(None)):
    return _store().list_events(jurisdiction)


@app.get("/api/documents", response_model=List[ContractDocument])
def list_documents():
    return _store().list_documents()


@app.get("/api/documents/sample", response_model=ContractDocument)
def sample_document():
    return _store().get_document(SAMPLE_CONTRACT.document_id) or SAMPLE_CONTRACT


@app.post("/api/documents/parse", response_model=ContractDocument)
def parse_document(req: ParseContractRequest):
    doc = parse_contract_text(req.document_id, req.title, req.raw_text, req.jurisdiction, req.source_url, req.source_type)
    if len(doc.clauses) < 2:
        raise HTTPException(422, "Could not split the text into clauses")
    _store().upsert_document(doc)
    return doc


@app.get("/api/documents/{document_id}", response_model=ContractDocument)
def get_document(document_id: str):
    doc = _store().get_document(document_id)
    if not doc:
        raise HTTPException(404, f"document {document_id} not found")
    return doc


@app.get("/api/radar", response_model=List[JurisdictionStatus])
def radar(document_id: str = SAMPLE_CONTRACT.document_id):
    return build_radar(_store().gaps_for(document_id), _store().list_events())


@app.post("/api/ingest/statute", response_model=StatuteIngestResponse)
def ingest_statute(req: StatuteIngestRequest):
    events, mode = _pipeline().extractor.run(req.jurisdiction, req.agency, req.raw_text, req.published_date, req.code_name, req.source_url)
    if not events:
        raise HTTPException(422, "No statutory rules with citations could be extracted from the bulletin text")
    _store().upsert_events(events)
    return StatuteIngestResponse(events=events, extraction_mode=mode)


@app.post("/api/audit/document", response_model=AuditResponse)
def audit_document(req: AuditRequest):
    store = _store()
    events = store.list_events(req.jurisdictions)
    if not events:
        raise HTTPException(409, "No regulatory events ingested; call /api/ingest/statute first")
    store.upsert_document(req.document)
    gaps, mode = _pipeline().gap_engine.run(req.document, events)
    store.replace_gaps(req.document.document_id, gaps)
    return AuditResponse(document_id=req.document.document_id, gaps=gaps, radar=build_radar(gaps, events), analysis_mode=mode)


@app.post("/api/remediate/preview", response_model=RemediationPatch)
def remediate_preview(gap_id: str, document_id: str):
    store = _store()
    gap = store.get_gap(gap_id)
    doc = store.get_document(document_id)
    if not gap or not doc:
        raise HTTPException(404, "gap or document not found; run /api/audit/document first")
    patch = _pipeline().remediator.run(gap, doc, store.event_by_citation(gap.statute_citation))
    store.save_patch(patch)
    return patch


@app.post("/api/remediate/patch", response_model=RemediationResponse)
def remediate_patch(req: RemediationRequest):
    store = _store()
    gap = store.get_gap(req.gap_id)
    doc = store.get_document(req.document_id)
    if not gap or not doc:
        raise HTTPException(404, "gap or document not found; run /api/audit/document first")
    event = store.event_by_citation(gap.statute_citation)
    patch = store.get_patch(req.gap_id) or _pipeline().remediator.run(gap, doc, event)

    if req.decision == "REJECT":
        approval = RemediationApproval(gap_id=gap.gap_id, document_id=doc.document_id, approved_patch=patch.redlined_text, auditor_id=req.auditor_id, status="REJECTED")
        store.record_approval(approval)
        return RemediationResponse(approval=approval, patch=patch)

    final_text = (req.auditor_override_text or patch.redlined_text).strip()
    verdict = _pipeline().remediator.judge(gap, final_text, patch.original_text, gap.statutory_source_snippet)
    if not verdict.is_grounded:
        raise HTTPException(422, f"Patch failed grounding verification and cannot be applied: {verdict.judge_rationale}")

    new_clauses = [
        ContractClause(clause_id=c.clause_id, section_name=c.section_name, verbatim_text=final_text if c.clause_id == gap.target_clause_id else c.verbatim_text)
        for c in doc.clauses
    ]
    updated = ContractDocument(document_id=doc.document_id, title=doc.title, jurisdiction=doc.jurisdiction, clauses=new_clauses)
    store.upsert_document(updated)

    approval = RemediationApproval(gap_id=gap.gap_id, document_id=doc.document_id, approved_patch=final_text, auditor_id=req.auditor_id, status="APPLIED")
    store.record_approval(approval)

    remaining = [g for g in store.gaps_for(doc.document_id) if g.gap_id != gap.gap_id]
    store.replace_gaps(doc.document_id, remaining)

    package = FilingPackage(
        package_id=f"pkg-{uuid.uuid4().hex[:10]}",
        jurisdiction=gap.jurisdiction,
        agency=event.agency if event else "",
        statute_citation=gap.statute_citation,
        document_id=doc.document_id,
        clause_id=gap.target_clause_id,
        before_text=patch.original_text,
        after_text=final_text,
        auditor_id=req.auditor_id,
        attestation=(
            f"Auditor {req.auditor_id} reviewed and approved the amendment of clause {gap.target_clause_id} in "
            f"'{doc.title}' to conform to {gap.statute_citation}. Grounding verification: {verdict.judge_rationale}."
        ),
    )
    return RemediationResponse(approval=approval, patch=patch, filing_package=package, updated_document=updated)
