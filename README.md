# Certo

AI-native continuous compliance for US fintechs operating across the state-by-state
lending patchwork. YC RFS Fall 2026 (Daivik Goel).

Wedge: multi-state consumer and commercial lending rules, starting with Texas,
California, and New York fee caps, rate ceilings, prepayment rules, loan-term
limits, and disclosure mandates.

## What is real in this repository

| Thing | Source | Where |
|---|---|---|
| Primary contract | OneMain Financial Group, LLC, Texas Loan Agreement and Disclosure Statement, the lender's published sample form TXSTLA0726 (`onemainfinancial.com/pdf/LA-TX-STLA0726.pdf`) | `backend/data/onemain_texas_loan_agreement_2026.txt` |
| Second contract | OneMain Financial Group, LLC, California Loan Agreement and Disclosure Statement, sample form CASTLA0726 (`onemainfinancial.com/pdf/LA-CA-STLA0726.pdf`) | `backend/data/onemain_california_loan_agreement_2026.txt` |
| Third contract | Prosper Funding LLC / WebBank promissory note, SEC EDGAR exhibit 10.22 | `backend/data/prosper_webbank_promissory_note_2016.txt` |
| Fourth contract | Happen Bank (formerly LendingClub) Loan Agreement and Promissory Note, lender legal page | `backend/data/happen_bank_loan_agreement_2026.txt` |
| Provenance | URL, retrieval time, extraction method, sha256 of the stored text (and of the source PDF) for every contract | `backend/data/sources.json` |
| PDF extraction | Reproducible text-layer extraction for the OneMain forms (poppler layout mode, barcode glyphs and page furniture dropped, nothing else touched) | `scripts/extract_pdf_text.py` |
| 15 statutory rules | Texas, California, and New York official legislature sites | `backend/mock_data.py` (`SEED_EVENTS`) |
| 17 statute texts | Same sites, verbatim, with URL, retrieval time, sha256 | `backend/data/statutes/` |

The primary document is deliberately a **state-licensed non-bank lender's own
form**. OneMain Financial Group, LLC is licensed and examined by the Texas Office
of Consumer Credit Commissioner and lends in California under the California
Financing Law, and its forms say so, so the Texas and California caps in the
rule set bind these contracts directly. The two bank notes (WebBank, Happen
Bank) stay in the demo as the contrast case: a bank may export its home-state
rates and fees under federal law, so a state cap that binds a licensed lender
may not bind them. The OneMain forms are sample forms with the lender's own
sample figures ($5,000 over 48 months); the California PDF has three image-only
pages (security, insurance, default, remedies, and the start of the arbitration
agreement) that are marked in the text rather than OCR-guessed. Every fee,
prepayment, term, disclosure, and governing-law clause is on a text-layer page.

Every `RegulatoryEvent` carries a `verification` record: the URL it was checked
against, the machine check's status and confidence, and `verified_by`, which is
empty until a human has checked the entry. Nothing in the repository is
reconstructed from memory. The 2026-09-03 verification pass found two errors in
the original spec and corrected them: Texas late fees are capped at 5 cents per
dollar of the installment with no dollar floor (not "the lesser of $15 or 5%"),
and California Financial Code § 22300 says nothing about 48-hour opt-out notices.

## Architecture

```
backend/                       FastAPI · Pydantic v2 · Instructor
  schemas.py                   deterministic contracts for every agent boundary
  agents.py                    Agent A extractor · Agent B gap engine · Agent C remediator + judge
  parser.py                    splits a real note or form-style agreement into clauses (every word preserved)
  store.py                     in-memory store, or Postgres + pgvector when DATABASE_URL is set
  main.py                      API server
  mock_data.py                 real contracts + verified rules + verbatim statute texts
  test_pipeline.py             offline tests
  data/                        verbatim contracts and statutes with provenance
frontend/                      Next.js 14 App Router · TypeScript · Tailwind · Lucide
  src/app/page.tsx             radar · split diff viewer · remediation studio
scripts/demo.sh                one-command seeded demo
scripts/extract_pdf_text.py    verbatim text-layer extraction for lender PDF forms
```

Every agent has two execution paths. With `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
set, calls go through Instructor and are forced into the Pydantic schemas. Without a
key, a pure-Python statutory rule engine runs the same interfaces, so the whole demo
works offline. The deterministic path is ground truth: LLM thresholds that disagree
with the regex read of the statute are overwritten, LLM gaps that point at
non-existent clauses or citations are dropped, and an LLM redline that fails
grounding falls back to the deterministic patch.

### Agents

| Agent | Input | Output | Hallucination control |
|---|---|---|---|
| A · Statutory Delta Extractor | statute or bulletin text | `RegulatoryEvent[]` | snippet must be a verbatim substring; thresholds and fee caps reconciled against the regex read |
| B · Gap Analysis Engine | contract + events | `ComplianceGap[]` | clause and citation must exist; deterministic findings always kept; fee formulas compared numerically across installment sizes |
| C · Remediation & Verifier | gap | `RemediationPatch` + `GroundingVerdict` | dual judge (LLM + deterministic) must both pass: citation present, every number traceable, no invented obligations |

Human-in-the-loop: `POST /api/remediate/patch` is the only mutation of the contract.
It requires an `auditor_id`, re-runs the grounding judge on whatever text the auditor
actually approved (including manual edits), refuses with 422 if it fails, and emits
a `FilingPackage` attestation on success.

## Run the demo

```bash
./scripts/demo.sh
```

That creates the backend virtualenv if needed, starts the API on port 8000 with a
clean in-memory store seeded with the 15 verified rules and the four real
contracts, audits all four, starts the dashboard on port 3000, and opens it.
`./scripts/demo.sh --check` does the same headlessly and prints the radar;
`./scripts/demo.sh --stop` stops the servers. Optional: put `ANTHROPIC_API_KEY`
in `backend/.env` to turn on the LLM path (see `.env.example`).

### 60-second walkthrough

1. **Radar (0:00).** The dashboard opens on OneMain Financial's Texas loan agreement. Texas is green, California and New York are red. Say: "This is the published form of a lender the Texas OCCC licenses, so the Texas caps bind it, and it passes them: the 5% late charge after 10 days and the $30 returned-check charge. The engine is not just finding fault."
2. **Click the CA card (0:10).** Two critical gaps on the same late-charge formula, once in Section B (clause cl-38, **LATE CHARGE**) and once in the Truth in Lending box (cl-5). Click cl-38's **Cal. Fin. Code § 22320.5** entry.
3. **Split diff (0:18).** Left: the verbatim statute, "an amount not in excess of fifteen dollars ($15)". Right: "The late charge will be 5% of the scheduled payment." Below: "yields $100.00 on a $2000 installment, above the statutory maximum of $15.00." Point at the green **source match** badge and its **primary source** link.
4. **Generate AI patch (0:30).** The redline appends ", not to exceed $15.00" to the formula sentence, adds the once-per-installment sentence, and cites the section. The verifier panel shows three green checks: statute cited, every number traceable, no invented obligations.
5. **Edit the redline (0:38), optional.** Change $15.00 to $99.00 and click Approve: the server refuses with a 422 because the edited text fails grounding. Undo the edit.
6. **Approve & Apply (0:45).** Clause cl-38 is amended, a California filing package appears at the bottom with before/after text and an auditor attestation, and the radar re-audits: California drops from two criticals to one, because the Truth in Lending box still carries the original formula. Approve cl-5 the same way and California turns amber: only warnings remain (the administrative fee amount lives in the itemization, not the clause, and the note carries no CFL license number). Texas stays green throughout.
7. **Show passed checks (0:55).** Expand the green list for Texas: § 342.203(d) and § 302.001(d) on both late-charge clauses, and § 3.506(b) on the $30 returned-check charge.
8. **Switch documents (1:00).** Pick the California form in the header dropdown: California is green (a flat $10 after 10 days), Texas is red (the flat $10 exceeds 5% of a $50 installment). Then pick the Prosper/WebBank note: all three states red, with the bank-exportation caveat below.

## Run pieces by hand

Backend (Python 3.11+):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Tests:

```bash
cd backend && source .venv/bin/activate && pip install pytest && python -m pytest -q
```

## API

| Method | Path | Agent |
|---|---|---|
| GET | `/api/health` | |
| GET | `/api/events` | |
| GET | `/api/documents` | |
| POST | `/api/documents/parse` | clause parser |
| POST | `/api/ingest/statute` | A |
| POST | `/api/audit/document` | B |
| POST | `/api/remediate/preview?gap_id&document_id` | C (draft + judge, no side effects) |
| POST | `/api/remediate/patch` | C (human approval, apply, filing package) |

Interactive docs at http://localhost:8000/docs.

## Verification status

All 15 rules were machine-checked against the official state sites on 2026-09-03
and none has been human-verified yet (`verified_by` is empty everywhere).

**Applicability.** The primary document is a state-licensed lender's own Texas
form, and the second is its California form, so the Texas and California caps
bind them directly. The Prosper/WebBank and Happen Bank notes are bank-originated
and may export their home-state rates and fees under federal law; the engine
reports what the statute says, and whether it applies to a given lender is the
auditor's call.

**Open encoding question, exposed by the new document.** N.Y. Banking Law § 351
("default of more than ten days") is seeded with an 11-day minimum grace period,
while Tex. Fin. Code § 342.203 ("after the 10th day") is seeded with 10. OneMain's
"within 10 days after it is due" means the charge lands on day 11, which
satisfies both statutes, so the New York finding on both OneMain forms is an
artifact of the encoding. It is pinned in `test_onemain_texas_form_audit` so that
changing it is a deliberate decision.

**Known engine limits on form-style agreements.** Checkbox semantics are not read
(the Truth in Lending box's "[Z] I will not have to pay a penalty for prepaying"
is not recognised as a no-penalty term, so the OneMain forms get no § 302.102
pass). A fill-in value printed after the sentence's period ("dishonored check
charge of $______. 15.00") is invisible to the fee parser. A prepaid charge
labelled "Points" ($250 on the California form) is not recognised as an
administrative or origination fee, so § 22305 is not checked against it. No Texas
administrative-fee rule is in the rule set, so the $125 administrative fee on the
Texas form is unchecked; adding one means retrieving the statute first. Not legal
advice.
