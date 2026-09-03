"""Seed data.

Contracts are real, publicly available loan agreements stored verbatim under
``data/`` with provenance in ``data/sources.json``. Statutory text below is
verbatim from the official state legislature sites named in each entry.
Nothing in this module is reconstructed from memory.

Each RegulatoryEvent carries a ``verification`` record: the URL it was checked
against, the machine check's confidence, and ``verified_by``, which stays empty
until a human has checked the entry.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from parser import parse_contract_text
from schemas import CompanyPolicy, ContractDocument, FeeCapSpec, RegulatoryEvent, SourceVerification

DATA_DIR = Path(__file__).parent / "data"
SOURCES: Dict[str, dict] = json.loads((DATA_DIR / "sources.json").read_text())
MACHINE_CHECKED_AT = "2026-09-03T03:10:00+00:00"


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
# Verbatim statutory excerpts (primary sources). These feed Agent A in
# CERTO_SEED_MODE=extract and the ingest tests.
# ---------------------------------------------------------------------------

TX_STATUTES_URL = "https://statutes.capitol.texas.gov/Docs/FI/htm/FI.{ch}.htm#{sec}"
CA_LEGINFO_URL = "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=FIN&sectionNum={sec}."
NY_SENATE_URL = "https://www.nysenate.gov/legislation/laws/{law}/{sec}"

TX_302_001_TEXT = """Sec. 302.001. CONTRACTING FOR, CHARGING, OR RECEIVING INTEREST OR TIME PRICE DIFFERENTIAL; USURIOUS INTEREST. (a) A creditor may contract for, charge, and receive from an obligor interest or time price differential. (b) The maximum rate or amount of interest is 10 percent a year except as otherwise provided by law. A greater rate of interest than 10 percent a year is usurious unless otherwise provided by law. All contracts for usurious interest are contrary to public policy and subject to the appropriate penalty prescribed by Chapter 305. (c) To determine the interest rate of a loan under this subtitle, all interest at any time contracted for shall be aggregated and amortized using the actuarial method during the stated term of the loan. (d) In addition to interest authorized by Subsection (b), a loan providing for a rate of interest that is 10 percent a year or less may provide for a delinquency charge on the amount of any payment in default for a period of not less than 10 days in an amount not to exceed the greater of five percent of the amount of the payment or $7.50. The charging of the delinquency charge does not make the loan subject to Chapter 342 or any other provision of Subtitle B. Amended by Acts 1999, 76th Leg., ch. 62, Sec. 7.18(a), eff. Sept. 1, 1999; Acts 2001, 77th Leg., ch. 916, Sec. 8, eff. Sept. 1, 2001."""

TX_342_203_TEXT = """Sec. 342.203. ADDITIONAL INTEREST FOR DEFAULT: REGULAR TRANSACTION. (a) A loan contract that includes precomputed interest or uses the scheduled installment earnings method and that is a regular transaction may provide for additional interest for default if any part of an installment remains unpaid after the 10th day after the date on which the installment is due, including Sundays and holidays. (b) A loan contract that uses the scheduled installment earnings method and that is a regular transaction may provide for additional interest for default if any part of an installment remains unpaid after the 10th day after the date on which the installment is due, including Sundays and holidays. (c) A loan contract that includes simple interest and that is a regular transaction may provide for additional interest for default if any part of an installment remains unpaid after the 10th day after the date on which the installment is due, including Sundays and holidays. (d) The additional interest may not exceed five cents for each $1 of a scheduled installment. (e) Interest under this section may not be collected more than once on the same installment. Amended by Acts 1999, 76th Leg., ch. 62, Sec. 7.19(a), eff. Sept. 1, 1999; Acts 1999, 76th Leg., ch. 909, Sec. 2.10, eff. Sept. 1, 1999; Acts 1999, 76th Leg., ch. 934, Sec. 2.01, eff. Sept. 1, 1999."""

CA_22304_5_TEXT = """22304.5. (a) For any loan of a bona fide principal amount of at least two thousand five hundred dollars ($2,500) but less than ten thousand dollars ($10,000), as determined in accordance with Section 22251, a finance lender may contract for or receive charges at a rate not exceeding an annual simple interest rate of 36 percent per annum plus the Federal Funds Rate."""

CA_22300_TEXT = """22300. No licensee shall directly or indirectly charge, contract for, or receive any interest or charge of any nature unless a loan is made."""

NY_14A_TEXT = """§ 14-a. Rate of interest; superintendent of financial services to adopt regulations. 1. The maximum rate of interest provided for in section 5-501 of the general obligations law shall be sixteen per centum per annum."""

NY_5_501_TEXT = """§ 5-501. Rate of interest; usury forbidden. 1. The rate of interest, as computed pursuant to this title, upon the loan or forbearance of any money, goods, or things in action, except as provided in subdivisions five and six of this section or as otherwise provided by law, shall be six per centum per annum unless a different rate is prescribed in section fourteen-a of the banking law."""

SEED_BULLETINS: List[Dict[str, str]] = [
    {"jurisdiction": "TX", "agency": "Texas Legislature (Finance Code); administered by the OCCC", "bulletin_title": "Tex. Fin. Code § 302.001", "raw_text": TX_302_001_TEXT, "code_name": "Tex. Fin. Code", "source_url": TX_STATUTES_URL.format(ch="302", sec="302.001"), "published_date": "2001-09-01"},
    {"jurisdiction": "TX", "agency": "Texas Legislature (Finance Code); administered by the OCCC", "bulletin_title": "Tex. Fin. Code § 342.203", "raw_text": TX_342_203_TEXT, "code_name": "Tex. Fin. Code", "source_url": TX_STATUTES_URL.format(ch="342", sec="342.203"), "published_date": "1999-09-01"},
    {"jurisdiction": "CA", "agency": "California Legislature (Financial Code); administered by the DFPI", "bulletin_title": "Cal. Fin. Code § 22304.5", "raw_text": CA_22304_5_TEXT, "code_name": "Cal. Fin. Code", "source_url": CA_LEGINFO_URL.format(sec="22304.5"), "published_date": "2020-01-01"},
    {"jurisdiction": "CA", "agency": "California Legislature (Financial Code); administered by the DFPI", "bulletin_title": "Cal. Fin. Code § 22300", "raw_text": CA_22300_TEXT, "code_name": "Cal. Fin. Code", "source_url": CA_LEGINFO_URL.format(sec="22300"), "published_date": "1995-07-01"},
    {"jurisdiction": "NY", "agency": "New York Legislature (Banking Law); administered by NYDFS", "bulletin_title": "N.Y. Banking Law § 14-a", "raw_text": NY_14A_TEXT, "code_name": "N.Y. Banking Law", "source_url": NY_SENATE_URL.format(law="BNK", sec="14-A"), "published_date": "1980-12-01"},
]


def _v(status: str, confidence: float, url: str, notes: str) -> SourceVerification:
    return SourceVerification(status=status, confidence=confidence, source_url=url, machine_checked_at=MACHINE_CHECKED_AT, verified_by=None, notes=notes)


SEED_EVENTS: List[RegulatoryEvent] = [
    RegulatoryEvent(
        event_id="evt-tx-302-001",
        jurisdiction="TX",
        agency="Texas OCCC / Texas Department of Banking",
        statute_citation="Tex. Fin. Code § 302.001(b)",
        effective_date="2001-09-01",
        rule_type="USURY_CAP",
        summary="General usury ceiling: the maximum rate of interest is 10 percent a year unless another provision of law allows more.",
        raw_source_snippet="The maximum rate or amount of interest is 10 percent a year except as otherwise provided by law. A greater rate of interest than 10 percent a year is usurious unless otherwise provided by law.",
        numerical_threshold=10.0,
        threshold_unit="PERCENT_APR",
        applicability="default ceiling; Chapter 342 licensed lenders and Chapter 303 optional ceilings authorize higher rates",
        verification=_v("MATCH", 0.95, TX_STATUTES_URL.format(ch="302", sec="302.001"), "Number matches. 2026-09-03: snippet replaced with verbatim statute text; the earlier snippet was a paraphrase."),
    ),
    RegulatoryEvent(
        event_id="evt-tx-342-203",
        jurisdiction="TX",
        agency="Texas OCCC / Texas Department of Banking",
        statute_citation="Tex. Fin. Code § 342.203(d)",
        effective_date="1999-09-01",
        rule_type="FEE_CAP",
        summary="Default charge on a Chapter 342 regular-transaction loan may not exceed five cents per $1 of the scheduled installment (5%), only after the 10th day past due, and only once per installment. There is no separate dollar cap.",
        raw_source_snippet="(c) A loan contract that includes simple interest and that is a regular transaction may provide for additional interest for default if any part of an installment remains unpaid after the 10th day after the date on which the installment is due, including Sundays and holidays. (d) The additional interest may not exceed five cents for each $1 of a scheduled installment. (e) Interest under this section may not be collected more than once on the same installment.",
        numerical_threshold=5.0,
        threshold_unit="PERCENT_OF_INSTALLMENT",
        fee_cap=FeeCapSpec(fee_kind="LATE", combinator="FLAT_PCT", usd_max=None, pct_max=5.0, min_grace_days=10, once_per_installment=True),
        applicability="regular-transaction consumer loans under Chapter 342 (licensed lenders)",
        verification=_v("MATCH", 0.95, TX_STATUTES_URL.format(ch="342", sec="342.203"), "2026-09-03 correction: the spec said 'lesser of $15.00 or 5%'. The statute says five cents for each $1 of a scheduled installment, no dollar cap, after the 10th day, once per installment. Citation moved from (a) to (d)."),
    ),
    RegulatoryEvent(
        event_id="evt-ca-22304-5",
        jurisdiction="CA",
        agency="California DFPI",
        statute_citation="Cal. Fin. Code § 22304.5(a)",
        effective_date="2020-01-01",
        rule_type="USURY_CAP",
        summary="Loans of at least $2,500 and less than $10,000 are capped at an annual simple interest rate of 36 percent plus the Federal Funds Rate.",
        raw_source_snippet="For any loan of a bona fide principal amount of at least two thousand five hundred dollars ($2,500) but less than ten thousand dollars ($10,000), as determined in accordance with Section 22251, a finance lender may contract for or receive charges at a rate not exceeding an annual simple interest rate of 36 percent per annum plus the Federal Funds Rate.",
        numerical_threshold=36.0,
        threshold_unit="PERCENT_APR",
        applicability="bona fide principal of $2,500 to $9,999.99; ceiling is 36% plus the Federal Funds Rate, so 36% is the floor of the cap",
        verification=_v("MATCH", 0.9, CA_LEGINFO_URL.format(sec="22304.5"), "Number matches § 22304.5(a). 2026-09-03 correction: the entry had been cited as '§ 22303 / § 22304.5'; § 22303 governs loans under $2,500 with monthly tiered rates and does not contain the 36% figure."),
    ),
    RegulatoryEvent(
        event_id="evt-ca-22300",
        jurisdiction="CA",
        agency="California DFPI",
        statute_citation="Cal. Fin. Code § 22300",
        effective_date="1995-07-01",
        rule_type="FEE_CAP",
        summary="A licensee may not charge, contract for, or receive any interest or charge of any nature unless a loan is made.",
        raw_source_snippet="No licensee shall directly or indirectly charge, contract for, or receive any interest or charge of any nature unless a loan is made.",
        numerical_threshold=None,
        threshold_unit=None,
        fee_cap=FeeCapSpec(fee_kind="OTHER", combinator="PROHIBITED", once_per_installment=False),
        applicability="California Financing Law licensees",
        verification=_v("MATCH", 0.9, CA_LEGINFO_URL.format(sec="22300"), "2026-09-03 correction: the spec described § 22300 as a 48-hour opt-out notice rule for automatically enrolled optional products. The statute contains no such language and no primary source for that rule was found. Entry replaced with the actual text of § 22300."),
    ),
    RegulatoryEvent(
        event_id="evt-ny-5-501",
        jurisdiction="NY",
        agency="New York DFS",
        statute_citation="N.Y. Banking Law § 14-a(1); N.Y. Gen. Oblig. Law § 5-501(1)",
        effective_date="1980-12-01",
        rule_type="USURY_CAP",
        summary="Civil usury ceiling of 16 percent per annum, set by Banking Law § 14-a for General Obligations Law § 5-501.",
        raw_source_snippet="The maximum rate of interest provided for in section 5-501 of the general obligations law shall be sixteen per centum per annum.",
        numerical_threshold=16.0,
        threshold_unit="PERCENT_APR",
        applicability="loans under $250,000 (§ 5-501(6)(a)); corporations cannot plead civil usury",
        verification=_v("MATCH", 0.95, NY_SENATE_URL.format(law="BNK", sec="14-A"), "16% confirmed in Banking Law § 14-a(1). § 5-501(1) itself says six per centum 'unless a different rate is prescribed in section fourteen-a of the banking law', so the citation now names both. Checked also against https://www.nysenate.gov/legislation/laws/GOB/5-501."),
    ),
]

SEED_POLICIES: List[CompanyPolicy] = [
    CompanyPolicy(policy_id="pol-late-fee", name="Late fee formula: greater of $15 or 5% of the late payment", jurisdiction="FED", rule_type="FEE_CAP", current_value=15.0, unit="USD", source_document_id=SAMPLE_CONTRACT.document_id),
    CompanyPolicy(policy_id="pol-nsf-fee", name="Returned payment fee", jurisdiction="FED", rule_type="FEE_CAP", current_value=15.0, unit="USD", source_document_id=SAMPLE_CONTRACT.document_id),
]
