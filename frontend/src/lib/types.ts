export type Jurisdiction = "TX" | "CA" | "NY" | "FED";
export type RuleType = "FEE_CAP" | "USURY_CAP" | "DISCLOSURE_MANDATE" | "REPORTING_DEADLINE";
export type Severity = "CRITICAL" | "WARNING" | "COMPLIANT";
export type RadarStatus = "GREEN" | "AMBER" | "RED" | "UNKNOWN";

export interface RegulatoryEvent {
  event_id: string;
  jurisdiction: Jurisdiction;
  agency: string;
  statute_citation: string;
  effective_date: string;
  rule_type: RuleType;
  summary: string;
  raw_source_snippet: string;
  numerical_threshold: number | null;
  threshold_unit: string | null;
}

export interface ContractClause {
  clause_id: string;
  section_name: string;
  verbatim_text: string;
}

export interface ContractDocument {
  document_id: string;
  title: string;
  jurisdiction: string;
  clauses: ContractClause[];
}

export interface ComplianceGap {
  gap_id: string;
  severity: Severity;
  statute_citation: string;
  target_clause_id: string;
  target_clause_text: string;
  violation_reason: string;
  statutory_threshold_violated: string | null;
  suggested_patch: string;
  confidence_score: number;
  is_grounded_in_citation: boolean;
  jurisdiction: Jurisdiction;
  rule_type: RuleType;
  statutory_source_snippet: string;
}

export interface JurisdictionStatus {
  jurisdiction: Jurisdiction;
  status: RadarStatus;
  critical_count: number;
  warning_count: number;
  active_rules: number;
}

export interface AuditResponse {
  document_id: string;
  gaps: ComplianceGap[];
  radar: JurisdictionStatus[];
  audited_at: string;
  analysis_mode: "llm" | "deterministic";
}

export interface GroundingVerdict {
  is_grounded: boolean;
  cited_statute_present: boolean;
  numbers_match_statute: boolean;
  no_invented_obligations: boolean;
  judge_rationale: string;
  confidence: number;
}

export interface RemediationPatch {
  gap_id: string;
  document_id: string;
  target_clause_id: string;
  original_text: string;
  redlined_text: string;
  statute_citation: string;
  change_rationale: string;
  grounding: GroundingVerdict;
  generated_at: string;
}

export interface FilingPackage {
  package_id: string;
  jurisdiction: Jurisdiction;
  agency: string;
  statute_citation: string;
  document_id: string;
  clause_id: string;
  before_text: string;
  after_text: string;
  auditor_id: string;
  attestation: string;
  generated_at: string;
}

export interface RemediationResponse {
  approval: { gap_id: string; document_id: string; approved_patch: string; auditor_id: string; timestamp: string; status: "APPLIED" | "REJECTED" };
  patch: RemediationPatch | null;
  filing_package: FilingPackage | null;
  updated_document: ContractDocument | null;
}
