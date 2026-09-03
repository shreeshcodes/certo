"""Offline tests for the deterministic pipeline. Run: python -m pytest -q"""
import re

from fastapi.testclient import TestClient

from main import app
from mock_data import DATA_DIR, HAPPEN_CONTRACT, SAMPLE_CONTRACT, SEED_BULLETINS, SEED_EVENTS, SOURCES
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


def test_every_seed_event_has_provenance_and_no_human_verifier():
    for e in SEED_EVENTS:
        assert e.verification.source_url and e.verification.source_url.startswith("https://")
        assert e.verification.status in ("MATCH", "PARTIAL")
        assert e.verification.confidence > 0
        assert e.verification.verified_by is None
        assert e.raw_source_snippet.strip()


def test_extractor_reads_real_statute_text():
    with TestClient(app) as c:
        found = {}
        for b in SEED_BULLETINS:
            r = c.post("/api/ingest/statute", json=b)
            assert r.status_code == 200, r.text
            for e in r.json()["events"]:
                found[e["statute_citation"]] = e
        assert found["Tex. Fin. Code § 302.001(b)"]["numerical_threshold"] == 10.0
        d = found["Tex. Fin. Code § 302.001(d)"]["fee_cap"]
        assert (d["combinator"], d["usd_max"], d["pct_max"], d["min_grace_days"]) == ("GREATER_OF", 7.5, 5.0, 10)
        t = found["Tex. Fin. Code § 342.203(d)"]
        assert t["numerical_threshold"] == 5.0 and t["threshold_unit"] == "PERCENT_OF_INSTALLMENT"
        assert t["fee_cap"]["usd_max"] is None and t["fee_cap"]["min_grace_days"] == 10 and t["fee_cap"]["once_per_installment"]
        assert found["Cal. Fin. Code § 22304.5"]["numerical_threshold"] == 36.0
        assert found["Cal. Fin. Code § 22300"]["fee_cap"]["combinator"] == "PROHIBITED"
        assert found["N.Y. Banking Law § 14-a"]["numerical_threshold"] == 16.0
        # re-ingesting a curated section does not duplicate it
        assert len(c.get("/api/events").json()) == len(SEED_EVENTS) + 1  # + § 302.001(d), which is not in the curated set yet


def test_end_to_end_offline():
    with TestClient(app) as c:
        docs = c.get("/api/documents").json()
        assert {d["document_id"] for d in docs} >= {SAMPLE_CONTRACT.document_id, HAPPEN_CONTRACT.document_id}
        assert all(d["source_url"] for d in docs)

        r = c.post("/api/audit/document", json={"document": SAMPLE_CONTRACT.model_dump()})
        assert r.status_code == 200, r.text
        body = r.json()
        radar = {s["jurisdiction"]: s["status"] for s in body["radar"]}
        assert radar == {"TX": "RED", "CA": "AMBER", "NY": "AMBER"}
        late = [g for g in body["gaps"] if g["target_clause_id"] == "cl-5" and g["statute_citation"] == "Tex. Fin. Code § 342.203(d)"]
        assert late and late[0]["severity"] == "CRITICAL"
        assert "$2.50" in late[0]["violation_reason"]  # 5% of a $50 installment
        blanks = [g for g in body["gaps"] if g["target_clause_id"] == "cl-2"]
        assert {g["severity"] for g in blanks} == {"WARNING"} and len(blanks) == 3
        assert all(g["is_grounded_in_citation"] for g in body["gaps"])

        gap = late[0]
        r = c.post("/api/remediate/preview", params={"gap_id": gap["gap_id"], "document_id": SAMPLE_CONTRACT.document_id})
        assert r.status_code == 200, r.text
        patch = r.json()
        assert patch["grounding"]["is_grounded"] is True
        assert "greater of" not in patch["redlined_text"]

        r = c.post("/api/remediate/patch", json={"gap_id": gap["gap_id"], "document_id": SAMPLE_CONTRACT.document_id, "auditor_id": "bryce"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["approval"]["status"] == "APPLIED"
        assert out["filing_package"]["statute_citation"] == gap["statute_citation"]
        again = c.post("/api/audit/document", json={"document": out["updated_document"]}).json()
        assert all(g["gap_id"] != gap["gap_id"] or g["severity"] == "COMPLIANT" for g in again["gaps"])

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
