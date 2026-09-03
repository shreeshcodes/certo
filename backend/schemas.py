"""Deterministic Pydantic v2 schemas for the Certo compliance engine.

Every LLM call in `agents.py` is forced through one of these models via
Instructor, so downstream code never sees free-form text.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


Jurisdiction = Literal["TX", "CA", "NY", "FED"]
RuleType = Literal["FEE_CAP", "USURY_CAP", "DISCLOSURE_MANDATE", "REPORTING_DEADLINE", "PREPAYMENT_PENALTY", "TERM_LIMIT"]
ThresholdUnit = Literal["USD", "PERCENT_APR", "PERCENT_PER_MONTH", "PERCENT_OF_INSTALLMENT", "HOURS", "DAYS", "MONTHS"]
Severity = Literal["CRITICAL", "WARNING", "COMPLIANT"]
FeeKind = Literal["LATE", "NSF", "ADMIN", "ORIGINATION", "OTHER"]


class FeeCapSpec(BaseModel):
    """Structured statement of a statutory fee limit so the diff engine can
    compare formulas ('greater of $15 or 5%') against caps ('5 cents per $1')."""

    fee_kind: FeeKind = "LATE"
    combinator: Literal["FLAT_USD", "FLAT_PCT", "LESSER_OF", "GREATER_OF", "PROHIBITED"] = "FLAT_PCT"
    usd_max: Optional[float] = Field(None, description="Dollar ceiling, if any")
    pct_max: Optional[float] = Field(None, description="Percent-of-installment ceiling, if any")
    min_grace_days: Optional[int] = Field(None, description="Charge permitted only after this many days past due")
    once_per_installment: bool = Field(True, description="Statute allows at most one charge per installment")


class SourceVerification(BaseModel):
    """Provenance record. ``verified_by`` is the human who checked it; it stays
    empty until someone has. ``confidence`` is the machine check's confidence."""

    status: Literal["MATCH", "MISMATCH", "PARTIAL", "UNVERIFIED"] = "UNVERIFIED"
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    source_url: Optional[str] = None
    machine_checked_at: Optional[str] = None
    verified_by: Optional[str] = None
    notes: Optional[str] = None


class RegulatoryEvent(BaseModel):
    """A single structured statutory rule extracted from a bulletin or statute."""

    event_id: str = Field(description="Unique ID for the regulatory update")
    jurisdiction: Jurisdiction = Field(description="State or federal jurisdiction")
    agency: str = Field(description="Regulatory agency, e.g., Texas Department of Banking")
    statute_citation: str = Field(description="Exact legal citation, e.g., Tex. Fin. Code § 302.001(b)")
    effective_date: str = Field(description="ISO date when statute takes legal effect")
    rule_type: RuleType
    summary: str = Field(description="Human-readable legal summary of the rule")
    raw_source_snippet: str = Field(description="Verbatim excerpt from the statute or bulletin")
    numerical_threshold: Optional[float] = Field(None, description="Binding number, e.g. 15.00 for a dollar cap or 16.0 for APR")
    threshold_unit: Optional[ThresholdUnit] = Field(None, description="Unit of numerical_threshold so the diff engine compares like with like")
    fee_cap: Optional[FeeCapSpec] = Field(None, description="Structured fee limit for FEE_CAP rules")
    applicability: Optional[str] = Field(None, description="Scope limits, e.g. 'loans of $2,500 to $9,999' or 'residential homestead loans above 12%'")
    verification: SourceVerification = Field(default_factory=SourceVerification)

    @field_validator("effective_date")
    @classmethod
    def _iso_date(cls, v: str) -> str:
        datetime.fromisoformat(v)
        return v


class StatuteIngestRequest(BaseModel):
    jurisdiction: Jurisdiction
    agency: str
    bulletin_title: str
    raw_text: str = Field(min_length=20, description="Full text of the bulletin or statute excerpt")
    published_date: Optional[str] = None
    code_name: Optional[str] = Field(None, description="Citation prefix for 'Sec. 342.203.' style headings, e.g. 'Tex. Fin. Code'")
    source_url: Optional[str] = None


class StatuteIngestResponse(BaseModel):
    events: List[RegulatoryEvent]
    ingested_at: datetime = Field(default_factory=_utcnow)
    extraction_mode: Literal["llm", "deterministic"]


class ContractClause(BaseModel):
    clause_id: str
    section_name: str
    verbatim_text: str


class ParseContractRequest(BaseModel):
    document_id: str
    title: str
    raw_text: str = Field(min_length=50)
    jurisdiction: str = "MULTI"
    source_url: Optional[str] = None
    source_type: Optional[str] = None


class ContractDocument(BaseModel):
    document_id: str
    title: str
    jurisdiction: str
    clauses: List[ContractClause]
    source_url: Optional[str] = Field(None, description="Where the verbatim text was retrieved from")
    source_type: Optional[str] = Field(None, description="e.g. SEC EDGAR exhibit, lender legal page")
    retrieved_at: Optional[str] = Field(None, description="ISO timestamp of retrieval")


class CompanyPolicy(BaseModel):
    """Internal policy value the company currently operates under."""

    policy_id: str
    name: str
    jurisdiction: Jurisdiction
    rule_type: RuleType
    current_value: float
    unit: str
    source_document_id: Optional[str] = None


class ComplianceGap(BaseModel):
    gap_id: str
    severity: Severity
    statute_citation: str
    target_clause_id: str
    target_clause_text: str
    violation_reason: str
    statutory_threshold_violated: Optional[str] = None
    suggested_patch: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    is_grounded_in_citation: bool
    jurisdiction: Jurisdiction
    rule_type: RuleType
    statutory_source_snippet: str = Field(default="", description="Verbatim statute text shown beside the offending clause in the diff viewer")


class AuditRequest(BaseModel):
    document: ContractDocument
    jurisdictions: Optional[List[Jurisdiction]] = Field(None, description="Restrict the audit to these jurisdictions; default is all ingested")


class JurisdictionStatus(BaseModel):
    jurisdiction: Jurisdiction
    status: Literal["GREEN", "AMBER", "RED", "UNKNOWN"]
    critical_count: int
    warning_count: int
    compliant_count: int = 0
    active_rules: int


class AuditResponse(BaseModel):
    document_id: str
    gaps: List[ComplianceGap]
    radar: List[JurisdictionStatus]
    audited_at: datetime = Field(default_factory=_utcnow)
    analysis_mode: Literal["llm", "deterministic"]


class GroundingVerdict(BaseModel):
    """LLM-as-a-judge output: does the redline stay inside the cited statute?"""

    is_grounded: bool
    cited_statute_present: bool
    numbers_match_statute: bool
    no_invented_obligations: bool
    judge_rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


class RemediationPatch(BaseModel):
    gap_id: str
    document_id: str
    target_clause_id: str
    original_text: str
    redlined_text: str
    statute_citation: str
    change_rationale: str
    grounding: GroundingVerdict
    generated_at: datetime = Field(default_factory=_utcnow)


class RemediationApproval(BaseModel):
    gap_id: str
    document_id: str
    approved_patch: str
    auditor_id: str
    timestamp: datetime = Field(default_factory=_utcnow)
    status: Literal["APPLIED", "REJECTED"]


class RemediationRequest(BaseModel):
    gap_id: str
    document_id: str
    auditor_id: str
    decision: Literal["APPROVE", "REJECT"] = "APPROVE"
    auditor_override_text: Optional[str] = Field(None, description="If the human edits the AI redline, the edited text wins")


class FilingPackage(BaseModel):
    package_id: str
    jurisdiction: Jurisdiction
    agency: str
    statute_citation: str
    document_id: str
    clause_id: str
    before_text: str
    after_text: str
    auditor_id: str
    attestation: str
    generated_at: datetime = Field(default_factory=_utcnow)


class RemediationResponse(BaseModel):
    approval: RemediationApproval
    patch: Optional[RemediationPatch] = None
    filing_package: Optional[FilingPackage] = None
    updated_document: Optional[ContractDocument] = None
