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
RuleType = Literal["FEE_CAP", "USURY_CAP", "DISCLOSURE_MANDATE", "REPORTING_DEADLINE"]
Severity = Literal["CRITICAL", "WARNING", "COMPLIANT"]


class RegulatoryEvent(BaseModel):
    """A single structured statutory delta extracted from a bulletin."""

    event_id: str = Field(description="Unique ID for the regulatory update")
    jurisdiction: Jurisdiction = Field(description="State or federal jurisdiction")
    agency: str = Field(description="Regulatory agency, e.g., Texas Department of Banking")
    statute_citation: str = Field(description="Exact legal citation, e.g., TX Fin Code § 302.001")
    effective_date: str = Field(description="ISO date when statute takes legal effect")
    rule_type: RuleType
    summary: str = Field(description="Human-readable legal summary of the statutory delta")
    raw_source_snippet: str = Field(description="Verbatim excerpt from the regulatory bulletin")
    numerical_threshold: Optional[float] = Field(
        None,
        description="Extracted numerical cap, e.g., 15.00 for dollar cap or 16.0 for APR",
    )
    threshold_unit: Optional[Literal["USD", "PERCENT_APR", "PERCENT_OF_INSTALLMENT", "HOURS", "DAYS"]] = Field(
        None, description="Unit of numerical_threshold so the diff engine can compare like with like"
    )

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


class StatuteIngestResponse(BaseModel):
    events: List[RegulatoryEvent]
    ingested_at: datetime = Field(default_factory=_utcnow)
    extraction_mode: Literal["llm", "deterministic"]


class ContractClause(BaseModel):
    clause_id: str
    section_name: str
    verbatim_text: str


class ContractDocument(BaseModel):
    document_id: str
    title: str
    jurisdiction: str
    clauses: List[ContractClause]


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
    statutory_source_snippet: str = Field(
        default="", description="Verbatim statute text shown beside the offending clause in the diff viewer"
    )


class AuditRequest(BaseModel):
    document: ContractDocument
    jurisdictions: Optional[List[Jurisdiction]] = Field(
        None, description="Restrict the audit to these jurisdictions; default is all ingested"
    )


class JurisdictionStatus(BaseModel):
    jurisdiction: Jurisdiction
    status: Literal["GREEN", "AMBER", "RED", "UNKNOWN"]
    critical_count: int
    warning_count: int
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
    auditor_override_text: Optional[str] = Field(
        None, description="If the human edits the AI redline, the edited text wins"
    )


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
