"""Offline tests for the deterministic pipeline. Run: python -m pytest -q"""
import re

from fastapi.testclient import TestClient

from main import app
from agents import parse_fee_formula
from mock_data import DATA_DIR, HAPPEN_CONTRACT, ONEMAIN_CA_CONTRACT, ONEMAIN_TX_CONTRACT, PROSPER_CONTRACT, SEED_BULLETINS, SEED_EVENTS, SOURCES
from parser import parse_contract_text


def test_parser_preserves_every_word_of_real_notes():
    for filename in SOURCES:
        raw = (DATA_DIR / filename).read_text()
        doc = parse_contract_text("t", "t", raw)
        joined = " ".join(c.verbatim_text for c in doc.clauses)
        assert re.findall(r"\S+", joined) == re.findall(r"\S+", raw)
        assert len(doc.clauses) >= 15


def test_parser_finds_fee_clauses_in_both_notes():
    prosper = {c.section_name: c for c in PROSPER_CONTRACT.clauses}
    assert "greater of $15 or 5.00%" in prosper["4. Late Charge"].verbatim_text
    assert "without penalty" in prosper["9. Prepayments"].verbatim_text
    assert "22. By signing this Note, I acknowledge …" in prosper
    assert "21. State Notices · New Jersey Residents" in prosper
    happen = {c.section_name: c for c in HAPPEN_CONTRACT.clauses}
    assert "greater of 5% of the outstanding payment or $15" in happen["Late fee"].verbatim_text
    assert "Lender" not in happen and "Borrower" not in happen  # wrapped lines are not headings
    assert "Controlling Law · New Jersey Residents" in happen


def test_seed_has_fifteen_events_across_three_states():
    assert len(SEED_EVENTS) == 15
    by_state = {}
    for e in SEED_EVENTS:
        by_state.setdefault(e.jurisdiction, set()).add(e.rule_type)
    assert by_state["TX"] >= {"USURY_CAP", "FEE_CAP", "PREPAYMENT_PENALTY"}
    assert by_state["CA"] >= {"USURY_CAP", "FEE_CAP", "TERM_LIMIT", "DISCLOSURE_MANDATE"}
    assert by_state["NY"] >= {"USURY_CAP", "FEE_CAP"}


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
        assert found["Tex. Fin. Code § 303.009(b)"]["numerical_threshold"] == 24.0
        assert found["Tex. Fin. Code § 302.102"]["rule_type"] == "PREPAYMENT_PENALTY"
        assert found["Tex. Bus. & Com. Code § 3.506(b)"]["fee_cap"]["usd_max"] == 30.0
        ca = found["Cal. Fin. Code § 22320.5(a)"]["fee_cap"]
        assert (ca["combinator"], ca["usd_max"], ca["min_grace_days"], ca["once_per_installment"]) == ("FLAT_USD", 15.0, 10, True)
        assert found["Cal. Fin. Code § 22334(c)"]["numerical_threshold"] == 12.0
        assert found["N.Y. Penal Law § 190.40"]["numerical_threshold"] == 25.0
        ny = found["N.Y. Banking Law § 351"]["fee_cap"]
        assert (ny["combinator"], ny["pct_max"], ny["once_per_installment"]) == ("FLAT_PCT", 5.0, True)
        # re-ingesting curated sections replaces nothing curated and creates no duplicate section keys
        after = c.get("/api/events").json()
        ids = {e["event_id"] for e in after}
        assert {e.event_id for e in SEED_EVENTS} <= ids
        keys = [(e["jurisdiction"], e["rule_type"], re.sub(r"\([a-z0-9\-]+\)", "", e["statute_citation"].split(";")[0]).strip().lower()) for e in after]
        assert len(keys) == len(set(keys))


def test_end_to_end_offline():
    with TestClient(app) as c:
        docs = c.get("/api/documents").json()
        assert {d["document_id"] for d in docs} >= {PROSPER_CONTRACT.document_id, HAPPEN_CONTRACT.document_id}
        assert all(d["source_url"] for d in docs)

        r = c.post("/api/audit/document", json={"document": PROSPER_CONTRACT.model_dump()})
        assert r.status_code == 200, r.text
        body = r.json()
        radar = {s["jurisdiction"]: s["status"] for s in body["radar"]}
        assert radar == {"TX": "RED", "CA": "RED", "NY": "RED"}
        crit = {(g["jurisdiction"], g["statute_citation"]) for g in body["gaps"] if g["severity"] == "CRITICAL"}
        assert crit == {
            ("TX", "Tex. Fin. Code § 342.203(d)"),
            ("TX", "Tex. Fin. Code § 302.001(d)"),
            ("CA", "Cal. Fin. Code § 22320.5(a)-(b)"),
            ("NY", "N.Y. Banking Law § 351"),
        }
        assert all(g["target_clause_id"] == "cl-5" for g in body["gaps"] if g["severity"] == "CRITICAL")
        late = [g for g in body["gaps"] if g["target_clause_id"] == "cl-5" and g["statute_citation"] == "Tex. Fin. Code § 342.203(d)"]
        assert "$2.50" in late[0]["violation_reason"]  # 5% of a $50 installment
        blanks = [g for g in body["gaps"] if g["target_clause_id"] == "cl-2" and "blank" in g["violation_reason"]]
        assert {g["severity"] for g in blanks} == {"WARNING"} and len(blanks) == 5
        passed = {(g["statute_citation"], g["target_clause_id"]) for g in body["gaps"] if g["severity"] == "COMPLIANT"}
        assert ("Tex. Fin. Code § 302.102", "cl-10") in passed  # prepay without penalty
        assert any(c == "cl-12" for _, c in passed)  # $15 NSF fee within the $30 Texas cap
        assert all(g["is_grounded_in_citation"] for g in body["gaps"])

        gap = late[0]
        r = c.post("/api/remediate/preview", params={"gap_id": gap["gap_id"], "document_id": PROSPER_CONTRACT.document_id})
        assert r.status_code == 200, r.text
        patch = r.json()
        assert patch["grounding"]["is_grounded"] is True
        assert "greater of" not in patch["redlined_text"]

        r = c.post("/api/remediate/patch", json={"gap_id": gap["gap_id"], "document_id": PROSPER_CONTRACT.document_id, "auditor_id": "bryce"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["approval"]["status"] == "APPLIED"
        assert out["filing_package"]["statute_citation"] == gap["statute_citation"]
        again = c.post("/api/audit/document", json={"document": out["updated_document"]}).json()
        assert all(g["gap_id"] != gap["gap_id"] or g["severity"] == "COMPLIANT" for g in again["gaps"])

        # An ungrounded human override is refused.
        r = c.post("/api/audit/document", json={"document": PROSPER_CONTRACT.model_dump()})
        gap2 = [g for g in r.json()["gaps"] if g["severity"] == "CRITICAL"][0]
        r = c.post("/api/remediate/patch", json={"gap_id": gap2["gap_id"], "document_id": PROSPER_CONTRACT.document_id, "auditor_id": "bryce", "auditor_override_text": "Late charge shall be $99 or 40% of the payment."})
        assert r.status_code == 422


def test_happen_note_audit():
    with TestClient(app) as c:
        body = c.post("/api/audit/document", json={"document": HAPPEN_CONTRACT.model_dump()}).json()
        crit = {(g["jurisdiction"], g["target_clause_id"]) for g in body["gaps"] if g["severity"] == "CRITICAL"}
        assert crit == {("TX", "cl-7"), ("CA", "cl-7"), ("NY", "cl-7")}
        warn = {(g["statute_citation"], g["target_clause_id"]) for g in body["gaps"] if g["severity"] == "WARNING"}
        assert ("Cal. Fin. Code § 22305", "cl-5") in warn  # origination fee amount unstated vs $75 cap
        assert ("Cal. Fin. Code § 22334(c)", "cl-4") in warn  # blank term vs 12-month minimum


def test_parse_endpoint():
    with TestClient(app) as c:
        raw = (DATA_DIR / "prosper_webbank_promissory_note_2016.txt").read_text()
        r = c.post("/api/documents/parse", json={"document_id": "doc-x", "title": "x", "raw_text": raw})
        assert r.status_code == 200
        assert len(r.json()["clauses"]) >= 30


def test_parser_splits_form_style_agreements():
    tx = ONEMAIN_TX_CONTRACT.clauses
    names = [c.section_name for c in tx]
    assert names.count("LATE CHARGE") == 2  # the Truth in Lending box label and the Section B clause
    assert "RETURNED CHECK CHARGE" in names and "GOVERNING LAW" in names and "QUESTIONS OR COMPLAINTS" in names
    assert "1. ADDITIONAL DEFINITIONS" in names and "2. WHAT CLAIMS ARE COVERED" in names and "8. SELECTION OF ARBITRATOR" in names
    assert "ITEMIZATION OF AMOUNT FINANCED" in names and "PREPAID FINANCE CHARGES" in names
    assert not any(n.startswith(("1. $", "2. $", "Paid To")) for n in names)  # the itemization table is not a clause list
    by_name = {c.section_name: c for c in tx}
    assert by_name["DATE OF LOAN"].verbatim_text.startswith("B. LOAN TERMS AND CONDITIONS")  # section title folded into its first clause
    assert "5% of the scheduled payment" in [c for c in tx if c.section_name == "LATE CHARGE"][1].verbatim_text
    assert "Office of Consumer Credit Commissioner" in by_name["QUESTIONS OR COMPLAINTS"].verbatim_text
    ca = {c.section_name: c for c in ONEMAIN_CA_CONTRACT.clauses}
    assert "California Finance Lenders Law" in ca["GOVERNING LAW"].verbatim_text
    assert "10.00" in ca["LATE CHARGE"].verbatim_text and "DISHONORED CHECK CHARGE" in ca
    assert "[Page 3 of the source PDF is a scanned image with no text layer.]" in " ".join(c.verbatim_text for c in ONEMAIN_CA_CONTRACT.clauses)


def test_fee_formula_reads_form_fill_blanks():
    f = parse_fee_formula("LATE CHARGE: X D If any payment is not paid in full within 10 days after its due date, I will be charged _5.00 __ % of the entire amount of the payment, but not more than $ N/A or less than $ N/A.")
    assert (f.combinator, f.pct, f.usd, f.grace_days) == ("FLAT_PCT", 5.0, None, 10.0)
    f = parse_fee_formula("RETURNED CHECK CHARGE. If a check or other instrument I give to You is returned unpaid for any reason, I agree to pay a returned check charge of $_______ 30.00 or such greater amount as allowed by law.")
    assert (f.kind, f.combinator, f.usd) == ("NSF", "FLAT_USD", 30.0)
    f = parse_fee_formula("LATE CHARGE: D 10 days after its due date, I will be charged $__ X If any payment is not paid in full within __ 10.00_ if the entire scheduled payment exceeds $0 ___ or $__ 10.00_ if the entire scheduled payment is $ 0 ___ or less.")
    assert (f.combinator, f.usd, f.grace_days) == ("FLAT_USD", 10.0, 10.0)  # $0 is a threshold, not a fee


def test_onemain_texas_form_audit():
    """A state-licensed lender's own Texas form: the Texas caps bind it and it passes them."""
    with TestClient(app) as c:
        docs = c.get("/api/documents").json()
        assert docs[0]["document_id"] == ONEMAIN_TX_CONTRACT.document_id  # primary demo document
        body = c.post("/api/audit/document", json={"document": ONEMAIN_TX_CONTRACT.model_dump()}).json()
        radar = {s["jurisdiction"]: s["status"] for s in body["radar"]}
        assert radar["TX"] == "GREEN" and radar["CA"] == "RED"
        crit = {(g["jurisdiction"], g["statute_citation"], g["target_clause_id"]) for g in body["gaps"] if g["severity"] == "CRITICAL"}
        late_clauses = {c["clause_id"] for c in docs[0]["clauses"] if c["section_name"] == "LATE CHARGE"}
        assert {("CA", "Cal. Fin. Code § 22320.5(a)-(b)", cl) for cl in late_clauses} <= crit
        passed = {(g["statute_citation"], g["target_clause_id"]) for g in body["gaps"] if g["severity"] == "COMPLIANT"}
        assert all(("Tex. Fin. Code § 342.203(d)", cl) in passed for cl in late_clauses)  # 5% after 10 days
        assert any(cite.startswith("Tex. Fin. Code § 342.502(d)") and c == "cl-39" for cite, c in passed)  # $30 returned-check charge
        warn = {(g["statute_citation"], g["target_clause_id"]) for g in body["gaps"] if g["severity"] == "WARNING"}
        assert ("Cal. Fin. Code § 22305", "cl-37") in warn  # administrative fee amount is in the itemization, not the clause
        # Open encoding question, pinned so a change is deliberate: N.Y. Banking Law § 351 is seeded with an
        # 11-day minimum while Tex. Fin. Code § 342.203 ("after the 10th day") is seeded with 10; this form's
        # "within 10 days after it is due" therefore fails NY on grace days alone.
        ny = [g for g in body["gaps"] if g["jurisdiction"] == "NY"]
        assert ny and all("after 10 days" in g["violation_reason"] and "11 days" in g["violation_reason"] for g in ny)


def test_onemain_california_form_audit():
    with TestClient(app) as c:
        body = c.post("/api/audit/document", json={"document": ONEMAIN_CA_CONTRACT.model_dump()}).json()
        radar = {s["jurisdiction"]: s["status"] for s in body["radar"]}
        assert radar["CA"] == "GREEN" and radar["TX"] == "RED"
        passed = {(g["statute_citation"], g["target_clause_id"]) for g in body["gaps"] if g["severity"] == "COMPLIANT"}
        assert ("Cal. Fin. Code § 22320.5(a)-(b)", "cl-5") in passed  # flat $10 after 10 days
        crit = {(g["jurisdiction"], g["statute_citation"]) for g in body["gaps"] if g["severity"] == "CRITICAL"}
        assert ("TX", "Tex. Fin. Code § 342.203(d)") in crit  # $10 flat exceeds 5% of a small installment
        tx = next(g for g in body["gaps"] if g["jurisdiction"] == "TX" and g["statute_citation"] == "Tex. Fin. Code § 342.203(d)")
        assert "$10.00 on a $50 installment" in tx["violation_reason"]


def test_onemain_texas_form_remediation_loop():
    """Both copies of the late-charge formula (Section B and the Truth in Lending box) must be
    patched before California clears; Texas stays green throughout."""
    with TestClient(app) as c:
        doc = ONEMAIN_TX_CONTRACT.model_dump()
        body = c.post("/api/audit/document", json={"document": doc}).json()
        gap = next(g for g in body["gaps"] if g["target_clause_id"] == "cl-38" and g["jurisdiction"] == "CA" and g["severity"] == "CRITICAL")
        r = c.post("/api/remediate/preview", params={"gap_id": gap["gap_id"], "document_id": doc["document_id"]})
        assert r.status_code == 200, r.text
        patch = r.json()
        assert "not to exceed $15.00" in patch["redlined_text"] and patch["grounding"]["is_grounded"] is True
        # an edited redline that fails grounding is refused
        r = c.post("/api/remediate/patch", json={"gap_id": gap["gap_id"], "document_id": doc["document_id"], "auditor_id": "bryce", "auditor_override_text": patch["redlined_text"].replace("$15.00", "$99.00")})
        assert r.status_code == 422
        out = c.post("/api/remediate/patch", json={"gap_id": gap["gap_id"], "document_id": doc["document_id"], "auditor_id": "bryce"}).json()
        assert out["approval"]["status"] == "APPLIED" and out["filing_package"]["statute_citation"] == "Cal. Fin. Code § 22320.5(a)-(b)"
        doc = out["updated_document"]
        body = c.post("/api/audit/document", json={"document": doc}).json()
        radar = {s["jurisdiction"]: s["status"] for s in body["radar"]}
        assert radar["TX"] == "GREEN" and radar["CA"] == "RED"  # the Truth in Lending box still carries the original formula
        assert all(g["severity"] == "COMPLIANT" for g in body["gaps"] if g["target_clause_id"] == "cl-38" and g["jurisdiction"] in ("CA", "TX"))
        gap = next(g for g in body["gaps"] if g["target_clause_id"] == "cl-5" and g["jurisdiction"] == "CA" and g["severity"] == "CRITICAL")
        out = c.post("/api/remediate/patch", json={"gap_id": gap["gap_id"], "document_id": doc["document_id"], "auditor_id": "bryce"}).json()
        body = c.post("/api/audit/document", json={"document": out["updated_document"]}).json()
        radar = {s["jurisdiction"]: s["status"] for s in body["radar"]}
        assert radar["TX"] == "GREEN" and radar["CA"] == "AMBER"
        assert {g["statute_citation"] for g in body["gaps"] if g["jurisdiction"] == "CA" and g["severity"] != "COMPLIANT"} == {"Cal. Fin. Code § 22305", "Cal. Fin. Code § 22337(a)"}
