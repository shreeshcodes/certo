# Certo

AI-native continuous compliance for US fintechs operating across the state-by-state
lending patchwork. YC RFS Fall 2026 (Daivik Goel).

Wedge: multi-state consumer and commercial lending rules, starting with Texas,
California, and New York fee caps, rate ceilings, prepayment rules, loan-term
limits, and disclosure mandates.

## What is real in this repository

| Thing | Source | Where |
|---|---|---|
| Sample contract | Prosper Funding LLC / WebBank promissory note, SEC EDGAR exhibit 10.22 | `backend/data/prosper_webbank_promissory_note_2016.txt` |
| Second contract | Happen Bank (formerly LendingClub) Loan Agreement and Promissory Note, lender legal page | `backend/data/happen_bank_loan_agreement_2026.txt` |
| 15 statutory rules | Texas, California, and New York official legislature sites | `backend/mock_data.py` (`SEED_EVENTS`) |
| 17 statute texts | Same sites, verbatim, with URL, retrieval time, sha256 | `backend/data/statutes/` |

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
  parser.py                    splits a real promissory note into clauses (every word preserved)
  store.py                     in-memory store, or Postgres + pgvector when DATABASE_URL is set
  main.py                      API server
  mock_data.py                 real contracts + verified rules + verbatim statute texts
  test_pipeline.py             offline tests
  data/                        verbatim contracts and statutes with provenance
frontend/                      Next.js 14 App Router · TypeScript · Tailwind · Lucide
  src/app/page.tsx             radar · split diff viewer · remediation studio
scripts/demo.sh                one-command seeded demo
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
clean in-memory store seeded with the 15 verified rules and both real contracts,
audits both contracts, starts the dashboard on port 3000, and opens it.
`./scripts/demo.sh --check` does the same headlessly and prints the radar;
`./scripts/demo.sh --stop` stops the servers. Optional: put `ANTHROPIC_API_KEY`
in `backend/.env` to turn on the LLM path (see `.env.example`).

### 60-second walkthrough

1. **Radar (0:00).** All three states show red for the Prosper/WebBank note. Say: "This is a real promissory note from an SEC filing, audited against 15 verified statutes."
2. **Click the TX card (0:08).** The gap list filters to Texas. Click **Tex. Fin. Code § 342.203(d)** (clause cl-5, fee cap).
3. **Split diff (0:15).** Left: the verbatim statute, "five cents for each $1 of a scheduled installment". Right: the note's "greater of $15 or 5.00% of the late payment". Below: "yields $15.00 on a $50 installment, above the statutory maximum of $2.50." Point at the green **source match** badge and its **primary source** link.
4. **Generate AI patch (0:30).** The redline rewrites the formula in place to "5.00% of the late payment". The verifier panel shows three green checks: statute cited, every number traceable, no invented obligations.
5. **Edit the redline (0:38), optional.** Change 5.00% to 40%, click Approve: the server refuses with a 422 because the edited text fails grounding. Undo the edit.
6. **Approve & Apply (0:45).** Clause cl-5 is amended, a Texas filing package appears at the bottom with before/after text and an auditor attestation, and the radar re-audits: Texas and New York drop to amber, California stays red. Say: "Texas caps the fee at 5% with no dollar floor; California caps it at a flat $15. The Texas-conforming 5% formula still yields $100 on a $2,000 installment in California. One formula cannot satisfy both unless it is the lesser of $15 or 5%."
7. **Show passed checks (0:52).** Expand the green "passed checks" list: the $15 returned-payment fee sits under the Texas $30 cap; prepayment without penalty passes.
8. **Switch documents (0:57).** Pick the Happen Bank note in the header dropdown; the same late-fee formula fails the same three statutes.

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
and none has been human-verified yet (`verified_by` is empty everywhere). Two
applicability caveats matter for the demo contracts: both notes are originated
by banks (WebBank, Happen Bank) that may export their home-state rates and fees
under federal law, so a state fee cap that binds a state-licensed lender may not
bind these notes. The engine reports what the statute says; whether it applies to
a given lender is the auditor's call. Not legal advice.
