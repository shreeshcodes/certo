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


# State-licensed non-bank lender forms first: OneMain Financial Group, LLC is
# licensed by the Texas OCCC and under the California Financing Law, so the
# Texas and California caps bind these contracts directly. The two bank notes
# (WebBank, Happen Bank) may export their home-state rates under federal law.
ONEMAIN_TX_CONTRACT: ContractDocument = _load_contract("onemain_texas_loan_agreement_2026.txt", "doc-onemain-tx-2026")
ONEMAIN_CA_CONTRACT: ContractDocument = _load_contract("onemain_california_loan_agreement_2026.txt", "doc-onemain-ca-2026")
PROSPER_CONTRACT: ContractDocument = _load_contract("prosper_webbank_promissory_note_2016.txt", "doc-prosper-note-2016")
HAPPEN_CONTRACT: ContractDocument = _load_contract("happen_bank_loan_agreement_2026.txt", "doc-happen-note-2026")
SAMPLE_CONTRACT: ContractDocument = ONEMAIN_TX_CONTRACT  # the primary demo document
SEED_DOCUMENTS: List[ContractDocument] = [ONEMAIN_TX_CONTRACT, ONEMAIN_CA_CONTRACT, PROSPER_CONTRACT, HAPPEN_CONTRACT]

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

STATUTES_DIR = DATA_DIR / "statutes"
STATUTE_INDEX: Dict[str, dict] = json.loads((STATUTES_DIR / "index.json").read_text())


def _statute_text(key: str) -> str:
    return (STATUTES_DIR / f"{key}.txt").read_text()


SEED_BULLETINS += [
    {"jurisdiction": "TX", "agency": "Texas Legislature (Finance Code); administered by the OCCC", "bulletin_title": "Tex. Fin. Code § 303.009", "raw_text": _statute_text("tx-fin-303-009"), "code_name": "Tex. Fin. Code", "source_url": STATUTE_INDEX["tx-fin-303-009"]["source_url"], "published_date": "2011-09-01"},
    {"jurisdiction": "TX", "agency": "Texas Legislature (Finance Code); administered by the OCCC", "bulletin_title": "Tex. Fin. Code § 302.102", "raw_text": _statute_text("tx-fin-302-102"), "code_name": "Tex. Fin. Code", "source_url": STATUTE_INDEX["tx-fin-302-102"]["source_url"], "published_date": "1999-09-01"},
    {"jurisdiction": "TX", "agency": "Texas Legislature (Business & Commerce Code)", "bulletin_title": "Tex. Bus. & Com. Code § 3.506", "raw_text": _statute_text("tx-bc-3-506"), "code_name": "Tex. Bus. & Com. Code", "source_url": STATUTE_INDEX["tx-bc-3-506"]["source_url"], "published_date": "2003-09-01"},
    {"jurisdiction": "CA", "agency": "California Legislature (Financial Code); administered by the DFPI", "bulletin_title": "Cal. Fin. Code § 22320.5", "raw_text": _statute_text("ca-fin-22320-5"), "code_name": "Cal. Fin. Code", "source_url": STATUTE_INDEX["ca-fin-22320-5"]["source_url"], "published_date": "1999-01-01"},
    {"jurisdiction": "CA", "agency": "California Legislature (Financial Code); administered by the DFPI", "bulletin_title": "Cal. Fin. Code § 22305", "raw_text": _statute_text("ca-fin-22305"), "code_name": "Cal. Fin. Code", "source_url": STATUTE_INDEX["ca-fin-22305"]["source_url"], "published_date": "2020-01-01"},
    {"jurisdiction": "CA", "agency": "California Legislature (Financial Code); administered by the DFPI", "bulletin_title": "Cal. Fin. Code § 22334", "raw_text": _statute_text("ca-fin-22334"), "code_name": "Cal. Fin. Code", "source_url": STATUTE_INDEX["ca-fin-22334"]["source_url"], "published_date": "2020-01-01"},
    {"jurisdiction": "CA", "agency": "California Legislature (Financial Code); administered by the DFPI", "bulletin_title": "Cal. Fin. Code § 22337", "raw_text": _statute_text("ca-fin-22337"), "code_name": "Cal. Fin. Code", "source_url": STATUTE_INDEX["ca-fin-22337"]["source_url"], "published_date": "2012-01-01"},
    {"jurisdiction": "NY", "agency": "New York Legislature (Penal Law)", "bulletin_title": "N.Y. Penal Law § 190.40", "raw_text": _statute_text("ny-pen-190-40"), "code_name": "N.Y. Penal Law", "source_url": STATUTE_INDEX["ny-pen-190-40"]["source_url"], "published_date": "1976-09-01"},
    {"jurisdiction": "NY", "agency": "New York Legislature (Banking Law); administered by NYDFS", "bulletin_title": "N.Y. Banking Law § 351", "raw_text": _statute_text("ny-bnk-351"), "code_name": "N.Y. Banking Law", "source_url": STATUTE_INDEX["ny-bnk-351"]["source_url"], "published_date": "2005-01-01"},
]

# ---------------------------------------------------------------------------
# Task 4 coverage: ten more rules across TX, CA, NY. Every entry was checked
# against the primary source named in its verification record on 2026-09-03.
# ---------------------------------------------------------------------------

SEED_EVENTS += [
    RegulatoryEvent(
        event_id="evt-tx-302-001-d",
        jurisdiction="TX",
        agency="Texas OCCC / Texas Department of Banking",
        statute_citation="Tex. Fin. Code § 302.001(d)",
        effective_date="2001-09-01",
        rule_type="FEE_CAP",
        summary="On a loan at 10 percent a year or less, a delinquency charge may not exceed the greater of five percent of the payment or $7.50, and only for a payment at least 10 days in default.",
        raw_source_snippet="In addition to interest authorized by Subsection (b), a loan providing for a rate of interest that is 10 percent a year or less may provide for a delinquency charge on the amount of any payment in default for a period of not less than 10 days in an amount not to exceed the greater of five percent of the amount of the payment or $7.50.",
        numerical_threshold=7.5,
        threshold_unit="USD",
        fee_cap=FeeCapSpec(fee_kind="LATE", combinator="GREATER_OF", usd_max=7.5, pct_max=5.0, min_grace_days=10, once_per_installment=False),
        applicability="loans contracting for interest at 10 percent a year or less that are outside Chapter 342",
        verification=_v("MATCH", 0.9, STATUTE_INDEX["tx-fin-302-001"]["source_url"], "Verbatim from § 302.001(d) as rendered on statutes.capitol.texas.gov."),
    ),
    RegulatoryEvent(
        event_id="evt-tx-303-009",
        jurisdiction="TX",
        agency="Texas OCCC / Texas Department of Banking",
        statute_citation="Tex. Fin. Code § 303.009(b)",
        effective_date="2011-09-01",
        rule_type="USURY_CAP",
        summary="Under the optional rate ceilings, the consumer ceiling can never exceed 24 percent a year (18 percent floor under (a); 28 percent for business, commercial, or investment purpose under (c)).",
        raw_source_snippet="(b) Except as provided by Subsection (c), if the rate computed for the weekly, monthly, quarterly, or annualized ceiling is more than 24 percent a year, the ceiling is 24 percent a year. (c) For a contract made, extended, or renewed under which credit is extended for a business, commercial, investment, or similar purpose, the limitation on the ceilings determined by those computations is 28 percent a year.",
        numerical_threshold=24.0,
        threshold_unit="PERCENT_APR",
        applicability="contracts that elect a Chapter 303 optional ceiling (consumer purpose); Chapter 342 Subchapter E loans may instead use the tiered rates in § 342.201(e)",
        verification=_v("MATCH", 0.9, STATUTE_INDEX["tx-fin-303-009"]["source_url"], "Verbatim from § 303.009(b)-(c) as rendered on statutes.capitol.texas.gov."),
    ),
    RegulatoryEvent(
        event_id="evt-tx-302-102",
        jurisdiction="TX",
        agency="Texas OCCC / Texas Department of Banking",
        statute_citation="Tex. Fin. Code § 302.102",
        effective_date="1999-09-01",
        rule_type="PREPAYMENT_PENALTY",
        summary="No prepayment penalty may be collected on a loan on the borrower's residential homestead when the rate exceeds 12 percent a year, unless a federal agency requires it.",
        raw_source_snippet="If the interest rate on a loan for property that is or is to be the residential homestead of the borrower is greater than 12 percent a year, a prepayment penalty may not be collected on the loan unless the penalty is required by an agency created by federal law.",
        numerical_threshold=12.0,
        threshold_unit="PERCENT_APR",
        applicability="loans on the borrower's residential homestead with an interest rate above 12 percent a year",
        verification=_v("MATCH", 0.9, STATUTE_INDEX["tx-fin-302-102"]["source_url"], "Verbatim from § 302.102 as rendered on statutes.capitol.texas.gov."),
    ),
    RegulatoryEvent(
        event_id="evt-tx-342-502-d",
        jurisdiction="TX",
        agency="Texas OCCC / Texas Department of Banking",
        statute_citation="Tex. Fin. Code § 342.502(d); Tex. Bus. & Com. Code § 3.506(b)",
        effective_date="2003-09-01",
        rule_type="FEE_CAP",
        summary="A returned-payment (dishonored check or debit) fee on a Chapter 342 loan may not exceed the $30 processing fee set by Business & Commerce Code § 3.506.",
        raw_source_snippet="(d) On a loan subject to this chapter a lender may assess and collect a fee that does not exceed the amount prescribed by Section 3.506, Business & Commerce Code, for the return by a depository institution of a dishonored check, negotiable order of withdrawal, or share draft offered in full or partial payment of a loan. [§ 3.506(b):] may charge the drawer or indorser a maximum processing fee of $30.",
        numerical_threshold=30.0,
        threshold_unit="USD",
        fee_cap=FeeCapSpec(fee_kind="NSF", combinator="FLAT_USD", usd_max=30.0, pct_max=None, min_grace_days=None, once_per_installment=False),
        applicability="Chapter 342 loans; § 3.506(d) confirms the fee may be added to the balance without interest",
        verification=_v("MATCH", 0.9, STATUTE_INDEX["tx-fin-342-502"]["source_url"], "§ 342.502(d) cross-references B&C § 3.506; the $30 figure verified at " + STATUTE_INDEX["tx-bc-3-506"]["source_url"] + "."),
    ),
    RegulatoryEvent(
        event_id="evt-ca-22320-5",
        jurisdiction="CA",
        agency="California DFPI",
        statute_citation="Cal. Fin. Code § 22320.5(a)-(b)",
        effective_date="1999-01-01",
        rule_type="FEE_CAP",
        summary="Delinquency fee capped at $10 for a default of at least 10 days or $15 for a default of at least 15 days, collected at most once per default.",
        raw_source_snippet="(a) A licensee may contract for and receive a delinquency fee not in excess of one of the following amounts: (1) For a period in default of not less than 10 days, an amount not in excess of ten dollars ($10). (2) For a period in default of not less than 15 days, an amount not in excess of fifteen dollars ($15). (b) The delinquency fee may not be collected more than once for the same default and may be collected at the time of the default or at any time thereafter.",
        numerical_threshold=15.0,
        threshold_unit="USD",
        fee_cap=FeeCapSpec(fee_kind="LATE", combinator="FLAT_USD", usd_max=15.0, pct_max=None, min_grace_days=10, once_per_installment=True),
        applicability="California Financing Law licensee loans other than precomputed loans (subdivision (d))",
        verification=_v("MATCH", 0.95, STATUTE_INDEX["ca-fin-22320-5"]["source_url"], "Verbatim from leginfo.legislature.ca.gov; full section stored in data/statutes/ca-fin-22320-5.txt."),
    ),
    RegulatoryEvent(
        event_id="evt-ca-22305",
        jurisdiction="CA",
        agency="California DFPI",
        statute_citation="Cal. Fin. Code § 22305",
        effective_date="2020-01-01",
        rule_type="FEE_CAP",
        summary="One administrative fee per loan: at most the lesser of 5 percent of principal or $50 on loans of $2,500 or less, and at most $75 on loans above $2,500.",
        raw_source_snippet="a licensee may contract for and receive an administrative fee, which shall be fully earned immediately upon making the loan, with respect to a loan of a bona fide principal amount of not more than two thousand five hundred dollars ($2,500) at a rate not in excess of 5 percent of the principal amount (exclusive of the administrative fee) or fifty dollars ($50), whichever is less, and with respect to a loan of a bona fide principal amount in excess of two thousand five hundred dollars ($2,500), at an amount not to exceed seventy-five dollars ($75). No administrative fee may be contracted for or received in connection with the refinancing of a loan unless at least one year has elapsed since the receipt of a previous administrative fee paid by the borrower. Only one administrative fee may be contracted for or received until the loan has been repaid in full.",
        numerical_threshold=75.0,
        threshold_unit="USD",
        fee_cap=FeeCapSpec(fee_kind="ORIGINATION", combinator="FLAT_USD", usd_max=75.0, pct_max=None, min_grace_days=None, once_per_installment=False),
        applicability="loans above $2,500 ($75 cap); loans of $2,500 or less are capped at the lesser of 5 percent of principal or $50; an origination fee is the administrative fee for CFL purposes",
        verification=_v("MATCH", 0.9, STATUTE_INDEX["ca-fin-22305"]["source_url"], "Verbatim from leginfo.legislature.ca.gov; full section stored in data/statutes/ca-fin-22305.txt."),
    ),
    RegulatoryEvent(
        event_id="evt-ca-22334-c",
        jurisdiction="CA",
        agency="California DFPI",
        statute_citation="Cal. Fin. Code § 22334(c)",
        effective_date="2020-01-01",
        rule_type="TERM_LIMIT",
        summary="A loan of at least $2,500 and less than $10,000 may not schedule repayment of principal over less than 12 months.",
        raw_source_snippet="(c) A licensee shall not enter into any contract for a loan that provides for a scheduled repayment of principal that is less than 12 months. This subdivision applies to a loan of a bona fide principal amount of at least two thousand five hundred dollars ($2,500), but less than ten thousand dollars ($10,000).",
        numerical_threshold=12.0,
        threshold_unit="MONTHS",
        applicability="bona fide principal of $2,500 to $9,999.99; subdivision (a) also caps the term at 60 months and 15 days for $3,000 to $9,999.99",
        verification=_v("MATCH", 0.95, STATUTE_INDEX["ca-fin-22334"]["source_url"], "Verbatim from leginfo.legislature.ca.gov; full section stored in data/statutes/ca-fin-22334.txt."),
    ),
    RegulatoryEvent(
        event_id="evt-ca-22337-a",
        jurisdiction="CA",
        agency="California DFPI",
        statute_citation="Cal. Fin. Code § 22337(a)",
        effective_date="2012-01-01",
        rule_type="DISCLOSURE_MANDATE",
        summary="At the time the loan is made the lender must deliver a statement showing its name, address, and license number, the loan's date, amount, maturity, repayment terms, security, and the agreed rate of charge or the Regulation Z annual percentage rate.",
        raw_source_snippet="(a) Deliver or cause to be delivered to the borrower, or any one thereof, at the time the loan is made, a statement showing in clear and distinct terms the name, address, and license number of the finance lender and the broker, if any. The statement shall show the date, amount, and maturity of the loan contract, how and when repayable, the nature of the security for the loan, if any, and the agreed rate of charge or the annual percentage rate pursuant to Regulation Z promulgated by the Consumer Financial Protection Bureau (12 C.F.R. 1026).",
        numerical_threshold=None,
        threshold_unit=None,
        applicability="every licensed finance lender at the time a loan is made",
        verification=_v("MATCH", 0.95, STATUTE_INDEX["ca-fin-22337"]["source_url"], "Verbatim from leginfo.legislature.ca.gov; full section stored in data/statutes/ca-fin-22337.txt."),
    ),
    RegulatoryEvent(
        event_id="evt-ny-190-40",
        jurisdiction="NY",
        agency="New York DFS / New York Attorney General",
        statute_citation="N.Y. Penal Law § 190.40",
        effective_date="1976-09-01",
        rule_type="USURY_CAP",
        summary="Criminal usury: knowingly charging interest above 25 percent per annum without legal authorization is a class E felony.",
        raw_source_snippet="A person is guilty of criminal usury in the second degree when, not being authorized or permitted by law to do so, he knowingly charges, takes or receives any money or other property as interest on the loan or forebearance of any money or other property, at a rate exceeding twenty-five per centum per annum or the equivalent rate for a longer or shorter period.",
        numerical_threshold=25.0,
        threshold_unit="PERCENT_APR",
        applicability="all lenders not otherwise authorized, including loans to corporations; loans of $2,500,000 or more are exempt under Gen. Oblig. Law § 5-501(6)(b)",
        verification=_v("MATCH", 0.95, STATUTE_INDEX["ny-pen-190-40"]["source_url"], "Verbatim from nysenate.gov (retrieved through a fetch; the site challenges non-browser clients)."),
    ),
    RegulatoryEvent(
        event_id="evt-ny-bnk-351",
        jurisdiction="NY",
        agency="New York DFS",
        statute_citation="N.Y. Banking Law § 351",
        effective_date="2005-01-01",
        rule_type="FEE_CAP",
        summary="A licensed lender may collect a default charge of at most five percent of the installment in default, only after a default of more than ten days, and only once per default.",
        raw_source_snippet="In the event of default of more than ten days in the payment of any scheduled installment, the licensee may charge and collect a default charge not exceeding five percent of the installment in default. This charge may not be collected more than once for the same default and may be collected at the time of such default or at any time thereafter.",
        numerical_threshold=5.0,
        threshold_unit="PERCENT_OF_INSTALLMENT",
        fee_cap=FeeCapSpec(fee_kind="LATE", combinator="FLAT_PCT", usd_max=None, pct_max=5.0, min_grace_days=11, once_per_installment=True),
        applicability="Article 9 licensed lenders (personal loans of $25,000 or less, Banking Law § 340)",
        verification=_v("MATCH", 0.9, STATUTE_INDEX["ny-bnk-351"]["source_url"], "Verbatim from nysenate.gov (retrieved through a fetch; the site challenges non-browser clients). 'More than ten days' is encoded as an 11-day minimum."),
    ),
]

SEED_POLICIES: List[CompanyPolicy] = [
    CompanyPolicy(policy_id="pol-late-fee", name="Late fee formula: greater of $15 or 5% of the late payment", jurisdiction="FED", rule_type="FEE_CAP", current_value=15.0, unit="USD", source_document_id=PROSPER_CONTRACT.document_id),
    CompanyPolicy(policy_id="pol-nsf-fee", name="Returned payment fee", jurisdiction="FED", rule_type="FEE_CAP", current_value=15.0, unit="USD", source_document_id=PROSPER_CONTRACT.document_id),
]
