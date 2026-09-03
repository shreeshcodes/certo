"""Offline smoke tests for the deterministic pipeline. Run: python -m pytest -q"""
import re

from fastapi.testclient import TestClient

from main import app
from mock_data import DATA_DIR, HAPPEN_CONTRACT, SAMPLE_CONTRACT, SOURCES
from parser import parse_contract_text


def test_parser_preserves_every_word_of_real_notes():
    for filename in SOURCES:
        raw = (DATA_DIR / filename).read_text()
        doc = parse_contract_text("t", "t", raw)
        joined = " ".join(c.verbatim_text for c in doc.clauses)
        assert re.findall(r"\S+", joined) == re.findall(r"\S+", raw)
        assert len(doc.clauses) >= 15


def test_parser_finds_fee_clauses_in_both_notes():
    prosper = {c.section_name: c for c in SAMPLE_CONTRACT.clauses}
    assert "greater of $15 or 5.00%" in prosper["4. Late Charge"].verbatim_text
    assert "without penalty" in prosper["9. Prepayments"].verbatim_text
    assert "22. By signing this Note, I acknowledge …" in prosper
    assert "21. State Notices · New Jersey Residents" in prosper
    happen = {c.section_name: c for c in HAPPEN_CONTRACT.clauses}
    assert "greater of 5% of the outstanding payment or $15" in happen["Late fee"].verbatim_text
    assert "Lender" not in happen and "Borrower" not in happen  # wrapped lines are not headings
    assert "Controlling Law · New Jersey Residents" in happen


def test_end_to_end_offline():
    with TestClient(app) as c:
        health = c.get("/api/health").json()
        assert health["events"] >= 5
        docs = c.get("/api/documents").json()
        assert {d["document_id"] for d in docs} >= {SAMPLE_CONTRACT.document_id, HAPPEN_CONTRACT.document_id}
        assert all(d["source_url"] for d in docs)

        r = c.post("/api/audit/document", json={"document": SAMPLE_CONTRACT.model_dump()})
        assert r.status_code == 200, r.text
        body = r.json()
        radar = {s["jurisdiction"]: s["status"] for s in body["radar"]}
        assert radar["TX"] == "RED"
        late = [g for g in body["gaps"] if g["target_clause_id"] == "cl-5" and g["jurisdiction"] == "TX"]
        assert late and late[0]["severity"] == "CRITICAL"
        assert all(g["is_grounded_in_citation"] for g in body["gaps"] if g["severity"] != "COMPLIANT")

        gap = late[0]
        r = c.post("/api/remediate/preview", params={"gap_id": gap["gap_id"], "document_id": SAMPLE_CONTRACT.document_id})
        assert r.status_code == 200, r.text
        assert r.json()["grounding"]["is_grounded"] is True

        r = c.post("/api/remediate/patch", json={"gap_id": gap["gap_id"], "document_id": SAMPLE_CONTRACT.document_id, "auditor_id": "bryce"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["approval"]["status"] == "APPLIED"
        assert out["filing_package"]["statute_citation"] == gap["statute_citation"]
        assert all(g["gap_id"] != gap["gap_id"] for g in c.post("/api/audit/document", json={"document": out["updated_document"]}).json()["gaps"])

        # An ungrounded human override is refused.
        r = c.post("/api/audit/document", json={"document": SAMPLE_CONTRACT.model_dump()})
        gap2 = [g for g in r.json()["gaps"] if g["severity"] == "CRITICAL"][0]
        r = c.post("/api/remediate/patch", json={"gap_id": gap2["gap_id"], "document_id": SAMPLE_CONTRACT.document_id, "auditor_id": "bryce", "auditor_override_text": "Late charge shall be $99 or 40% of the payment."})
        assert r.status_code == 422


def test_parse_endpoint():
    with TestClient(app) as c:
        raw = (DATA_DIR / "prosper_webbank_promissory_note_2016.txt").read_text()
        r = c.post("/api/documents/parse", json={"document_id": "doc-x", "title": "x", "raw_text": raw})
        assert r.status_code == 200
        assert len(r.json()["clauses"]) >= 30
