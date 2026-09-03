"""Pre-seeded ground truth: sample TX and CA regulatory bulletins plus a
deliberately non-compliant multi-state consumer loan agreement.

Statutory text is paraphrased from public sources (Texas Finance Code
Chapters 302 and 342; California Financing Law, Fin. Code § 22000 et seq.)
and is illustrative demo data, not legal advice.
"""
from __future__ import annotations

from typing import Dict, List

from schemas import CompanyPolicy, ContractClause, ContractDocument, RegulatoryEvent

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
    {
        "jurisdiction": "TX",
        "agency": "Texas Department of Banking / OCCC",
        "bulletin_title": "RB-2026-07 Maximum interest and late charges",
        "raw_text": TX_BULLETIN_TEXT,
        "published_date": "2026-07-01",
    },
    {
        "jurisdiction": "CA",
        "agency": "California DFPI",
        "bulletin_title": "Licensee Advisory 2026-04 Rate ceilings and opt-out notices",
        "raw_text": CA_BULLETIN_TEXT,
        "published_date": "2026-06-15",
    },
    {
        "jurisdiction": "NY",
        "agency": "New York DFS",
        "bulletin_title": "Industry Letter on civil usury limits",
        "raw_text": NY_BULLETIN_TEXT,
        "published_date": "2026-05-20",
    },
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

SAMPLE_CONTRACT = ContractDocument(
    document_id="doc-loan-2026-0917",
    title="Multi-State Consumer Installment Loan Agreement v3.2",
    jurisdiction="MULTI",
    clauses=[
        ContractClause(
            clause_id="cl-1",
            section_name="1. Parties and Governing Law",
            verbatim_text=(
                "This Consumer Installment Loan Agreement is entered into between Meridian Lending LLC "
                "(\"Lender\") and the undersigned Borrower. This Agreement is offered to residents of Texas, "
                "California, and New York and shall be governed by the laws of the Borrower's state of residence."
            ),
        ),
        ContractClause(
            clause_id="cl-2",
            section_name="2. Interest Rate",
            verbatim_text=(
                "Borrower agrees to pay interest on the unpaid principal balance at a fixed rate of "
                "twenty-two percent (22.00%) per annum, calculated on a simple interest basis, "
                "irrespective of Borrower's state of residence."
            ),
        ),
        ContractClause(
            clause_id="cl-3",
            section_name="3. Late Payment Charge",
            verbatim_text=(
                "If any installment is not paid within ten (10) days after its due date, Borrower shall pay "
                "a late charge equal to the greater of $35.00 or ten percent (10%) of the overdue installment. "
                "Lender may assess this charge for each month the installment remains unpaid."
            ),
        ),
        ContractClause(
            clause_id="cl-4",
            section_name="4. Optional Payment Protection Plan",
            verbatim_text=(
                "Borrower is automatically enrolled in Lender's Payment Protection Plan at a monthly premium "
                "of $9.95, which will be added to the first installment. Borrower may cancel the Plan at any "
                "time by calling Lender; no separate notice will be sent."
            ),
        ),
        ContractClause(
            clause_id="cl-5",
            section_name="5. Prepayment",
            verbatim_text=(
                "Borrower may prepay the loan in whole or in part at any time without penalty. Interest "
                "accrues only through the date of prepayment."
            ),
        ),
    ],
)

SEED_POLICIES: List[CompanyPolicy] = [
    CompanyPolicy(
        policy_id="pol-apr",
        name="Standard consumer APR",
        jurisdiction="FED",
        rule_type="USURY_CAP",
        current_value=22.0,
        unit="PERCENT_APR",
        source_document_id=SAMPLE_CONTRACT.document_id,
    ),
    CompanyPolicy(
        policy_id="pol-late-fee",
        name="Late fee floor",
        jurisdiction="FED",
        rule_type="FEE_CAP",
        current_value=35.0,
        unit="USD",
        source_document_id=SAMPLE_CONTRACT.document_id,
    ),
]
