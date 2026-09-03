"""Offline smoke tests for the deterministic pipeline. Run: python -m pytest -q"""
from fastapi.testclient import TestClient

from main import app
from mock_data import SAMPLE_CONTRACT, TX_BULLETIN_TEXT, CA_BULLETIN_TEXT


def test_end_to_end_offline():
    with TestClient(app) as c:
        assert c.get("/api/health").json()["events"] >= 5

        r = c.post("/api/ingest/statute", json={"jurisdiction": "TX", "agency": "TX DOB", "bulletin_title": "t", "raw_text": TX_BULLETIN_TEXT})
        assert r.status_code == 200, r.text
        types = {e["rule_type"]: e for e in r.json()["events"]}
        assert types["FEE_CAP"]["numerical_threshold"] == 15.0
        assert types["USURY_CAP"]["numerical_threshold"] == 10.0

        r = c.post("/api/ingest/statute", json={"jurisdiction": "CA", "agency": "DFPI", "bulletin_title": "t", "raw_text": CA_BULLETIN_TEXT})
        types = {e["rule_type"]: e for e in r.json()["events"]}
        assert types["DISCLOSURE_MANDATE"]["numerical_threshold"] == 48.0
        assert types["USURY_CAP"]["numerical_threshold"] == 36.0

        r = c.post("/api/audit/document", json={"document": SAMPLE_CONTRACT.model_dump()})
        assert r.status_code == 200, r.text
        body = r.json()
        radar = {s["jurisdiction"]: s["status"] for s in body["radar"]}
        assert radar == {"TX": "RED", "CA": "RED", "NY": "RED"}
        by_clause = {}
        for g in body["gaps"]:
            by_clause.setdefault(g["target_clause_id"], []).append(g)
        assert "cl-2" in by_clause and "cl-3" in by_clause and "cl-4" in by_clause
        assert "cl-5" not in by_clause
        assert all(g["is_grounded_in_citation"] for g in body["gaps"])

        gap = by_clause["cl-3"][0]
        r = c.post("/api/remediate/preview", params={"gap_id": gap["gap_id"], "document_id": SAMPLE_CONTRACT.document_id})
        assert r.status_code == 200, r.text
        assert r.json()["grounding"]["is_grounded"] is True

        r = c.post("/api/remediate/patch", json={"gap_id": gap["gap_id"], "document_id": SAMPLE_CONTRACT.document_id, "auditor_id": "bryce"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["approval"]["status"] == "APPLIED"
        assert out["filing_package"]["statute_citation"] == gap["statute_citation"]
        clause = next(cl for cl in out["updated_document"]["clauses"] if cl["clause_id"] == "cl-3")
        assert "$15.00" in clause["verbatim_text"]

        # An ungrounded human override is refused.
        gap2 = by_clause["cl-2"][0]
        r = c.post("/api/remediate/patch", json={"gap_id": gap2["gap_id"], "document_id": SAMPLE_CONTRACT.document_id, "auditor_id": "bryce", "auditor_override_text": "Interest shall be 99% per annum."})
        assert r.status_code == 422
