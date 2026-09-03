# Certo

AI-native continuous compliance for US fintechs operating across the state-by-state
lending patchwork. YC RFS Fall 2026 (Daivik Goel).

Wedge: multi-state consumer and commercial lending rules, starting with Texas
(Fin. Code ch. 302 usury, § 342.203 late fees) and California (Fin. Code § 22300
opt-out notices, § 22303 rate ceilings), with New York usury as the third radar state.

## Architecture

```
backend/                       FastAPI · Pydantic v2 · Instructor
  schemas.py                   deterministic contracts for every agent boundary
  agents.py                    Agent A extractor · Agent B gap engine · Agent C remediator + judge
  store.py                     in-memory store, or Postgres + pgvector when DATABASE_URL is set
  main.py                      API server
  mock_data.py                 TX / CA / NY bulletins + non-compliant sample loan agreement
  test_pipeline.py             offline end-to-end test
frontend/                      Next.js 14 App Router · TypeScript · Tailwind · Lucide
  src/app/page.tsx             radar · split diff viewer · remediation studio
```

Every agent has two execution paths. With `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
set, calls go through Instructor and are forced into the Pydantic schemas. Without a
key, a pure-Python statutory rule engine runs the same interfaces, so the whole demo
works offline. When both run, the deterministic path is ground truth: LLM thresholds
that disagree with the regex read of the statute are overwritten, LLM gaps that
point at non-existent clauses or citations are dropped, and an LLM redline that
fails grounding falls back to the deterministic patch.

### Agents

| Agent | Input | Output | Hallucination control |
|---|---|---|---|
| A · Statutory Delta Extractor | bulletin text | `RegulatoryEvent[]` | snippet must be a verbatim substring; thresholds reconciled against regex |
| B · Gap Analysis Engine | contract + events | `ComplianceGap[]` | clause and citation must exist; deterministic findings always kept |
| C · Remediation & Verifier | gap | `RemediationPatch` + `GroundingVerdict` | dual judge (LLM + deterministic) must both pass; citation present, numbers traceable, no invented obligations |

Human-in-the-loop: `POST /api/remediate/patch` is the only mutation of the contract.
It requires an `auditor_id`, re-runs the grounding judge on whatever text the auditor
actually approved (including manual edits), refuses with 422 if it fails, and emits
a `FilingPackage` attestation on success.

## Run

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

Open http://localhost:3000. The dashboard boots by auditing the seeded sample
agreement; TX, CA, and NY should all show red. Pick a gap, generate the patch,
approve it, and the radar re-audits.

Tests:

```bash
cd backend && source .venv/bin/activate && pip install pytest && python -m pytest -q
```

## API

| Method | Path | Agent |
|---|---|---|
| GET | `/api/health` | |
| GET | `/api/events` | |
| GET | `/api/documents/sample` | |
| POST | `/api/ingest/statute` | A |
| POST | `/api/audit/document` | B |
| POST | `/api/remediate/preview?gap_id&document_id` | C (draft + judge, no side effects) |
| POST | `/api/remediate/patch` | C (human approval, apply, filing package) |

Interactive docs at http://localhost:8000/docs.

## Data note

Statutory text in `mock_data.py` is paraphrased from public sources for demo
purposes and is not legal advice. Bryce owns validation against live bulletins.
