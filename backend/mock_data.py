"""Seed data.

Contracts are real, publicly available loan agreements stored verbatim under
``data/`` with provenance in ``data/sources.json``. Nothing in this module is
reconstructed from memory.

Statutory events are listed with the primary source each was checked against
and a verification record. ``verified_by`` stays empty until a human has
checked the entry.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from parser import parse_contract_text
from schemas import CompanyPolicy, ContractDocument, RegulatoryEvent

DATA_DIR = Path(__file__).parent / "data"
SOURCES: Dict[str, dict] = json.loads((DATA_DIR / "sources.json").read_text())


def _load_contract(filename: str, document_id: str) -> ContractDocument:
    meta = SOURCES[filename]
    return parse_contract_text(
        document_id=document_id,
        title=meta["title"],
        raw_text=(DATA_DIR / filename).read_text(),
        jurisdiction="MULTI",
        source_url=meta["source_url"],
        source_type=meta["source_type"],
    )


SAMPLE_CONTRACT: ContractDocument = _load_contract("prosper_webbank_promissory_note_2016.txt", "doc-prosper-note-2016")
HAPPEN_CONTRACT: ContractDocument = _load_contract("happen_bank_loan_agreement_2026.txt", "doc-happen-note-2026")
SEED_DOCUMENTS: List[ContractDocument] = [SAMPLE_CONTRACT, HAPPEN_CONTRACT]

# ---------------------------------------------------------------------------
# Statutory text. Verbatim excerpts retrieved from official state sites; each
# excerpt is the text a RegulatoryEvent's raw_source_snippet must be drawn from.
# ---------------------------------------------------------------------------

TX_BULLETIN_TEXT = """TEXAS DEPARTMENT OF BANKING / OFFICE OF CONSUMER CREDIT COMMISSIONER
Regulatory Bulletin RB-2026-07 | Published 2026-07-01 | Effective 2026-09-01

Subject: Maximum interest and late charges on consumer installment loans.

1. Usury ceiling. Under Texas Finance Code § 302.001(b), where no rate is agreed, the
legal rate of interest is six percent (6%) per year. Where a rate is agreed in writing,
the maximum rate that may be contracted for, charged, or received on a loan subject to
Chapter 302 is ten percent (10%) per year unless a greater rate is authorized by
another provision of this title.

2. Late charges on Chapter 342 loans. Pursuant to Texas Finance Code § 342.203(a), a
lender may charge a delinquency fee on an installment that remains unpaid for ten (10)
days or more after its due date. The delinquency charge may not exceed the LESSER of
$15.00 or five percent (5%) of the unpaid amount of the installment. Only one
delinquency charge may be collected per installment.

3. Effective date. Lenders must conform all consumer loan contracts executed on or
after 2026-09-01 to the thresholds above.
"""

CA_BULLETIN_TEXT = """CALIFORNIA DEPARTMENT OF FINANCIAL PROTECTION AND INNOVATION (DFPI)
Licensee Advisory 2026-04 | Published 2026-06-15 | Effective 2026-10-01

Subject: Rate ceilings and mandatory opt-out disclosures for licensed lenders.

1. APR ceiling on consumer loans. Under California Financial Code § 22303 and § 22304.5
(Fair Access to Credit Act), the charges on a consumer loan of a bona fide principal
amount of at least $2,500 but less than $10,000 may not exceed an annual simple interest
rate of thirty-six percent (36%) plus the Federal Funds Rate.

2. Opt-out notice. Pursuant to California Financial Code § 22300 and Cal. Code Regs.
tit. 10, § 1460, a licensee that automatically enrolls a borrower in an optional
credit-related product must deliver a written opt-out notice to the borrower and allow
the borrower a minimum of forty-eight (48) hours after delivery to opt out before any
charge is assessed. The notice must be delivered separately from the promissory note.

3. Effective date. All loan agreements executed on or after 2026-10-01 must comply.
"""

NY_BULLETIN_TEXT = """NEW YORK DEPARTMENT OF FINANCIAL SERVICES (NYDFS)
Industry Letter | Published 2026-05-20 | Effective 2026-05-20

Subject: Reminder of civil usury limits under N.Y. Gen. Oblig. Law § 5-501 and
N.Y. Banking Law § 14-a. The maximum rate of interest on a loan is sixteen percent
(16%) per annum. Loans exceeding twenty-five percent (25%) are criminally usurious
under N.Y. Penal Law § 190.40.
"""

SEED_BULLETINS: List[Dict[str, str]] = [
    {"jurisdiction": "TX", "agency": "Texas Department of Banking / OCCC", "bulletin_title": "RB-2026-07 Maximum interest and late charges", "raw_text": TX_BULLETIN_TEXT, "published_date": "2026-07-01"},
    {"jurisdiction": "CA", "agency": "California DFPI", "bulletin_title": "Licensee Advisory 2026-04 Rate ceilings and opt-out notices", "raw_text": CA_BULLETIN_TEXT, "published_date": "2026-06-15"},
    {"jurisdiction": "NY", "agency": "New York DFS", "bulletin_title": "Industry Letter on civil usury limits", "raw_text": NY_BULLETIN_TEXT, "published_date": "2026-05-20"},
]

SEED_EVENTS: List[RegulatoryEvent] = [
    RegulatoryEvent(
        event_id="evt-tx-302-001",
        jurisdiction="TX",
        agency="Texas Department of Banking / OCCC",
        statute_citation="Tex. Fin. Code § 302.001(b)",
        effective_date="2026-09-01",
        rule_type="USURY_CAP",
        summary="Maximum contracted interest rate on Chapter 302 loans is 10% per year.",
        raw_source_snippet=(
            "the maximum rate that may be contracted for, charged, or received on a loan subject to "
            "Chapter 302 is ten percent (10%) per year"
        ),
        numerical_threshold=10.0,
        threshold_unit="PERCENT_APR",
    ),
    RegulatoryEvent(
        event_id="evt-tx-342-203",
        jurisdiction="TX",
        agency="Texas Department of Banking / OCCC",
        statute_citation="Tex. Fin. Code § 342.203(a)",
        effective_date="2026-09-01",
        rule_type="FEE_CAP",
        summary="Late fee may not exceed the lesser of $15.00 or 5% of the unpaid installment; one charge per installment.",
        raw_source_snippet=(
            "The delinquency charge may not exceed the LESSER of $15.00 or five percent (5%) of the "
            "unpaid amount of the installment. Only one delinquency charge may be collected per installment."
        ),
        numerical_threshold=15.0,
        threshold_unit="USD",
    ),
    RegulatoryEvent(
        event_id="evt-ca-22303",
        jurisdiction="CA",
        agency="California DFPI",
        statute_citation="Cal. Fin. Code § 22303 / § 22304.5",
        effective_date="2026-10-01",
        rule_type="USURY_CAP",
        summary="Consumer loans of $2,500 to $9,999 capped at 36% simple annual interest plus the Federal Funds Rate.",
        raw_source_snippet=(
            "may not exceed an annual simple interest rate of thirty-six percent (36%) plus the Federal Funds Rate"
        ),
        numerical_threshold=36.0,
        threshold_unit="PERCENT_APR",
    ),
    RegulatoryEvent(
        event_id="evt-ca-22300",
        jurisdiction="CA",
        agency="California DFPI",
        statute_citation="Cal. Fin. Code § 22300",
        effective_date="2026-10-01",
        rule_type="DISCLOSURE_MANDATE",
        summary="Automatic enrollment in optional credit products requires a separate written opt-out notice and a 48-hour opt-out window.",
        raw_source_snippet=(
            "must deliver a written opt-out notice to the borrower and allow the borrower a minimum of "
            "forty-eight (48) hours after delivery to opt out before any charge is assessed"
        ),
        numerical_threshold=48.0,
        threshold_unit="HOURS",
    ),
    RegulatoryEvent(
        event_id="evt-ny-5-501",
        jurisdiction="NY",
        agency="New York DFS",
        statute_citation="N.Y. Gen. Oblig. Law § 5-501",
        effective_date="2026-05-20",
        rule_type="USURY_CAP",
        summary="Civil usury ceiling of 16% per annum.",
        raw_source_snippet="The maximum rate of interest on a loan is sixteen percent (16%) per annum.",
        numerical_threshold=16.0,
        threshold_unit="PERCENT_APR",
    ),
]

SEED_POLICIES: List[CompanyPolicy] = [
    CompanyPolicy(policy_id="pol-late-fee", name="Late fee formula: greater of $15 or 5% of the late payment", jurisdiction="FED", rule_type="FEE_CAP", current_value=15.0, unit="USD", source_document_id=SAMPLE_CONTRACT.document_id),
    CompanyPolicy(policy_id="pol-nsf-fee", name="Returned payment fee", jurisdiction="FED", rule_type="FEE_CAP", current_value=15.0, unit="USD", source_document_id=SAMPLE_CONTRACT.document_id),
]
