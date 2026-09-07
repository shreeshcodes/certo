# Certo: rules for every AI agent working in this repository

Read `README.md` first. It says what is real, how the demo runs, and the verification status. These rules were set by Mike Vanhorn on 2026-09-03 and apply to every agent (Claude, Codex, Copilot) and every human using one.

## Non-negotiable

1. **Never invent a statute, citation, URL, contract, bulletin, or document number.** If a real source cannot be retrieved, say so and stop; do not reconstruct from memory or paraphrase a "likely" rule. Every seed document is a real document from a real URL, stored verbatim with retrieval time and sha256 in `backend/data/sources.json` (contracts) or `backend/data/statutes/index.json` (statutes).
2. **The deterministic engine is ground truth; the LLM path is additive.** An LLM output that disagrees with the regex read of the statute, points at a clause or citation that does not exist, or fails the grounding judge is overwritten or dropped. Never the reverse.
3. **`verification.verified_by` stays empty until a named human has checked the entry against the primary source.** Machine checks set `status` and `confidence` only. Do not fill it in on anyone's behalf.
4. **Report verification tables in full.** When you check rules against sources, list every rule and its result; never summarize a check away.
5. **When a real document breaks the parser, fix the parser and leave the document alone.** Contract and statute text is never edited. The only allowed transforms are whitespace normalization and the documented furniture removal in `scripts/extract_pdf_text.py`, and each removal is recorded in `sources.json`.
6. **Commit after each task** with a message that says what changed and why. **Push, merge, open a PR, or cut a release only on an explicit yes from a human.** "Commit this" is not permission to push.

## How to work here

- Tests are offline and take about a second: `cd backend && .venv/bin/python -m pytest -q`. Run them before every commit. `./scripts/demo.sh --check` boots the API, audits all four contracts headlessly, and prints the radar.
- **Adding a rule:** retrieve the statute text from the official legislature site, store it under `backend/data/statutes/` with an `index.json` entry (URL, retrieval time, sha256), add the `RegulatoryEvent` to `backend/mock_data.py` with a `verification` record, and add a test that pins the encoded threshold.
- **Adding a contract:** a real, publicly available document from a real URL, stored verbatim under `backend/data/` with a `sources.json` entry. For PDFs use `scripts/extract_pdf_text.py` and record what it removed. Image-only pages are marked in the text, not OCR-guessed.
- **Changing a verified record** (threshold, grace period, applicability) means writing the reason and date into that record's verification note, and updating the test that pins it. Example: N.Y. Banking Law § 351's grace period was corrected from 11 to 10 days on 2026-09-06 and the note says why.
- **Encoding conventions:** `FeeCapSpec.min_grace_days` is the number of full days that must elapse before a late charge may be assessed. Tex. Fin. Code § 342.203 "after the 10th day" = 10, N.Y. Banking Law § 351 "more than ten days" = 10, Cal. Fin. Code § 22320.5 "not less than 10 days" = 10. On the contract side, "within N days after its due date" = N.
- **Source-retrieval gotchas:** statutes.capitol.texas.gov is a JavaScript application (use a real browser, not curl); leginfo.legislature.ca.gov works with curl; nysenate.gov challenges non-browser clients; SEC EDGAR needs a real User-Agent with contact info; onemainfinancial.com serves the state sample loan agreements as PDFs at `/pdf/LA-<ST>-STLA<MMYY>.pdf`.
- The engine reports what a statute says; whether it applies to a given lender (bank preemption, licence type, loan size) is the auditor's call. Say so in anything user-facing. Not legal advice.
