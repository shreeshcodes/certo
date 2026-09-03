"""Certo multi-agent reasoning pipeline.

Three agents, each with two execution paths:

* ``llm``            -- Instructor-wrapped OpenAI or Anthropic call, forced into a
                        Pydantic schema. Selected when OPENAI_API_KEY or
                        ANTHROPIC_API_KEY is present (CERTO_LLM_PROVIDER overrides).
* ``deterministic``  -- Pure-Python statutory rule engine. Always available, used as
                        the offline path and as the ground-truth cross-check that
                        keeps LLM output honest.

Agent A  StatutoryDeltaExtractor   bulletin text        -> List[RegulatoryEvent]
Agent B  GapAnalysisEngine         contract + events    -> List[ComplianceGap]
Agent C  RemediationVerifier       gap                  -> RemediationPatch (+ judge)
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from pydantic import BaseModel

from schemas import (
    ComplianceGap,
    ContractClause,
    ContractDocument,
    GroundingVerdict,
    Jurisdiction,
    RegulatoryEvent,
    RemediationPatch,
    RuleType,
)

log = logging.getLogger("certo.agents")

# ---------------------------------------------------------------------------
# LLM client (Instructor). Lazily constructed; None when no key is configured.
# ---------------------------------------------------------------------------


class _EventList(BaseModel):
    events: List[RegulatoryEvent]


class _GapList(BaseModel):
    gaps: List[ComplianceGap]


class _Redline(BaseModel):
    redlined_text: str
    change_rationale: str


@dataclass
class LLMClient:
    provider: str
    model: str
    _client: object

    def structured(self, response_model, system: str, user: str, max_retries: int = 2):
        if self.provider == "anthropic":
            return self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
                response_model=response_model,
                max_retries=max_retries,
            )
        return self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_model=response_model,
            max_retries=max_retries,
        )


def build_llm_client() -> Optional[LLMClient]:
    provider = os.getenv("CERTO_LLM_PROVIDER", "").lower()
    if not provider:
        if os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        else:
            return None
    try:
        import instructor  # type: ignore

        if provider == "anthropic":
            from anthropic import Anthropic  # type: ignore

            model = os.getenv("CERTO_LLM_MODEL", "claude-sonnet-5")
            return LLMClient("anthropic", model, instructor.from_anthropic(Anthropic()))
        from openai import OpenAI  # type: ignore

        model = os.getenv("CERTO_LLM_MODEL", "gpt-4o-2024-08-06")
        return LLMClient("openai", model, instructor.from_openai(OpenAI()))
    except Exception as exc:  # missing SDK, bad key, etc.
        log.warning("LLM client unavailable (%s); using deterministic path", exc)
        return None


# ---------------------------------------------------------------------------
# Shared text utilities
# ---------------------------------------------------------------------------

_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:percent|%)", re.IGNORECASE)
_USD_RE = re.compile(r"\$\s?(\d+(?:,\d{3})*(?:\.\d{1,2})?)")
_HOURS_RE = re.compile(r"(\d+)\s*(?:\(\d+\)\s*)?hours?|\((\d+)\)\s*hours?", re.IGNORECASE)
_CITE_RE = re.compile(
    r"((?:Tex(?:as)?\.?\s+Fin(?:ance)?\.?\s+Code|California Financial Code|Cal\.?\s+Fin\.?\s+Code|"
    r"N\.Y\.\s+Gen\.\s+Oblig\.\s+Law|N\.Y\.\s+Banking\s+Law|N\.Y\.\s+Penal\s+Law|Cal\.?\s+Code\s+Regs\.[^§]*)"
    r"\s*§\s*([\d.\-]+(?:\([a-z0-9]+\))*))",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]
    return f"{prefix}-{digest}"


def _percents(text: str) -> List[float]:
    return [float(m.group(1)) for m in _PCT_RE.finditer(text)]


def _dollars(text: str) -> List[float]:
    return [float(m.group(1).replace(",", "")) for m in _USD_RE.finditer(text)]


def _hours(text: str) -> List[float]:
    out: List[float] = []
    for m in _HOURS_RE.finditer(text):
        val = m.group(1) or m.group(2)
        if val:
            out.append(float(val))
    return out


def _normalize_citation(raw: str) -> str:
    raw = re.sub(r"\s+", " ", raw).strip()
    raw = re.sub(r"(?i)^tex(?:as)?\.?\s+fin(?:ance)?\.?\s+code", "Tex. Fin. Code", raw)
    raw = re.sub(r"(?i)^california financial code", "Cal. Fin. Code", raw)
    raw = re.sub(r"(?i)^cal\.?\s+fin\.?\s+code", "Cal. Fin. Code", raw)
    return raw


# ---------------------------------------------------------------------------
# Agent A: Statutory Delta Extractor
# ---------------------------------------------------------------------------

_RULE_KEYWORDS: Sequence[Tuple[RuleType, Tuple[str, ...]]] = (
    ("FEE_CAP", ("late charge", "delinquency", "late fee", "delinquency fee")),
    ("DISCLOSURE_MANDATE", ("opt-out", "opt out", "notice", "disclos")),
    ("REPORTING_DEADLINE", ("report", "file with", "filing deadline", "annual report")),
    ("USURY_CAP", ("interest", "usury", "apr", "rate of interest", "annual simple interest")),
)


class StatutoryDeltaExtractor:
    """Agent A. Parses raw bulletin text into RegulatoryEvent records."""

    SYSTEM = (
        "You are a statutory extraction engine for US consumer-lending regulators. "
        "Read the bulletin and emit one RegulatoryEvent per distinct rule. "
        "statute_citation must be copied exactly as it appears. raw_source_snippet must be a "
        "verbatim substring of the bulletin. numerical_threshold is the binding number for the rule "
        "(dollar cap, APR percent, hours). Never invent rules that are not in the text."
    )

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm

    def run(
        self,
        jurisdiction: Jurisdiction,
        agency: str,
        raw_text: str,
        published_date: Optional[str] = None,
    ) -> Tuple[List[RegulatoryEvent], str]:
        deterministic = self._extract_deterministic(jurisdiction, agency, raw_text, published_date)
        if self.llm is None:
            return deterministic, "deterministic"
        try:
            user = f"Jurisdiction: {jurisdiction}\nAgency: {agency}\n\nBULLETIN:\n{raw_text}"
            result: _EventList = self.llm.structured(_EventList, self.SYSTEM, user)
            events = [e for e in result.events if self._snippet_is_verbatim(e, raw_text)]
            if not events:
                log.warning("LLM extractor returned no verbatim-grounded events; using deterministic")
                return deterministic, "deterministic"
            for e in events:
                e.jurisdiction = jurisdiction
                e.agency = agency
                if not e.event_id:
                    e.event_id = _stable_id("evt", jurisdiction, e.statute_citation, e.rule_type)
            return self._reconcile(events, deterministic), "llm"
        except Exception as exc:
            log.warning("LLM extractor failed (%s); using deterministic", exc)
            return deterministic, "deterministic"

    @staticmethod
    def _snippet_is_verbatim(event: RegulatoryEvent, raw_text: str) -> bool:
        needle = re.sub(r"\s+", " ", event.raw_source_snippet).strip().lower()
        hay = re.sub(r"\s+", " ", raw_text).lower()
        return bool(needle) and needle in hay

    @staticmethod
    def _reconcile(llm_events: List[RegulatoryEvent], det_events: List[RegulatoryEvent]) -> List[RegulatoryEvent]:
        """Deterministic numbers win on conflict: the regex reads the statute literally."""
        by_key = {(d.rule_type, d.statute_citation): d for d in det_events}
        for e in llm_events:
            d = by_key.get((e.rule_type, e.statute_citation))
            if d and d.numerical_threshold is not None and e.numerical_threshold != d.numerical_threshold:
                log.info("threshold conflict on %s: llm=%s det=%s", e.statute_citation, e.numerical_threshold, d.numerical_threshold)
                e.numerical_threshold = d.numerical_threshold
                e.threshold_unit = d.threshold_unit
        return llm_events

    def _extract_deterministic(
        self, jurisdiction: Jurisdiction, agency: str, raw_text: str, published_date: Optional[str]
    ) -> List[RegulatoryEvent]:
        effective = self._effective_date(raw_text, published_date)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n(?=\d+\.\s)", raw_text) if p.strip()]
        events: List[RegulatoryEvent] = []
        for para in paragraphs:
            cites = [_normalize_citation(m.group(1)) for m in _CITE_RE.finditer(para)]
            if not cites:
                continue
            rule_type = self._classify(para)
            if rule_type is None:
                continue
            threshold, unit, snippet = self._threshold(rule_type, para)
            citation = cites[0] if len(cites) == 1 else " / ".join(dict.fromkeys(cites))
            events.append(
                RegulatoryEvent(
                    event_id=_stable_id("evt", jurisdiction, citation, rule_type),
                    jurisdiction=jurisdiction,
                    agency=agency,
                    statute_citation=citation,
                    effective_date=effective,
                    rule_type=rule_type,
                    summary=self._summary(rule_type, threshold, unit, citation),
                    raw_source_snippet=snippet,
                    numerical_threshold=threshold,
                    threshold_unit=unit,
                )
            )
        return events

    @staticmethod
    def _effective_date(raw_text: str, published_date: Optional[str]) -> str:
        m = re.search(r"Effective\s+(\d{4}-\d{2}-\d{2})", raw_text, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"on or after\s+(\d{4}-\d{2}-\d{2})", raw_text, re.IGNORECASE)
        if m:
            return m.group(1)
        return published_date or _DATE_RE.search(raw_text).group(1) if (published_date or _DATE_RE.search(raw_text)) else "1970-01-01"

    @staticmethod
    def _classify(para: str) -> Optional[RuleType]:
        low = para.lower()
        if "effective date" in low and not any(k in low for _, ks in _RULE_KEYWORDS for k in ks if k != "report"):
            return None
        for rule_type, keys in _RULE_KEYWORDS:
            if any(k in low for k in keys):
                if rule_type == "REPORTING_DEADLINE" and "interest" in low:
                    continue
                return rule_type
        return None

    @staticmethod
    def _sentence_containing(para: str, needle_re: re.Pattern) -> str:
        sentences = re.split(r"(?<=[.;])\s+", para)
        for s in sentences:
            if needle_re.search(s):
                return s.strip()
        return sentences[0].strip()

    def _threshold(self, rule_type: RuleType, para: str) -> Tuple[Optional[float], Optional[str], str]:
        if rule_type == "FEE_CAP":
            usd = _dollars(para)
            snippet = self._sentence_containing(para, _USD_RE)
            return (min(usd) if usd else None), ("USD" if usd else None), snippet
        if rule_type == "USURY_CAP":
            pcts = _percents(para)
            # "maximum" / "may not exceed" sentence carries the binding ceiling.
            binding = re.compile(r"(maximum|may not exceed|not exceed|ceiling)", re.IGNORECASE)
            snippet = self._sentence_containing(para, binding)
            local = _percents(snippet)
            value = max(local) if local else (max(pcts) if pcts else None)
            return value, ("PERCENT_APR" if value is not None else None), snippet
        if rule_type == "DISCLOSURE_MANDATE":
            hrs = _hours(para)
            snippet = self._sentence_containing(para, re.compile(r"hours?|notice", re.IGNORECASE))
            return (hrs[0] if hrs else None), ("HOURS" if hrs else None), snippet
        days = re.findall(r"(\d+)\s*days?", para, re.IGNORECASE)
        snippet = self._sentence_containing(para, re.compile(r"days?|deadline", re.IGNORECASE))
        return (float(days[0]) if days else None), ("DAYS" if days else None), snippet

    @staticmethod
    def _summary(rule_type: RuleType, threshold: Optional[float], unit: Optional[str], citation: str) -> str:
        if rule_type == "FEE_CAP" and threshold is not None:
            return f"Late/delinquency charge capped at ${threshold:.2f} per installment under {citation}."
        if rule_type == "USURY_CAP" and threshold is not None:
            return f"Maximum permissible interest rate is {threshold:g}% per annum under {citation}."
        if rule_type == "DISCLOSURE_MANDATE" and threshold is not None:
            return f"Mandatory written opt-out notice with a {threshold:g}-hour window under {citation}."
        if rule_type == "REPORTING_DEADLINE" and threshold is not None:
            return f"Reporting deadline of {threshold:g} days under {citation}."
        return f"{rule_type.replace('_', ' ').title()} rule under {citation}."


# ---------------------------------------------------------------------------
# Agent B: Gap Analysis & Policy Diff Engine
# ---------------------------------------------------------------------------


class GapAnalysisEngine:
    """Agent B. Diffs every contract clause against every active rule."""

    SYSTEM = (
        "You are a compliance gap analyst. For each active RegulatoryEvent, decide whether any "
        "contract clause violates it. Emit a ComplianceGap ONLY when the clause text contains a "
        "term (rate, fee, notice period, enrollment mechanic) that conflicts with the statute. "
        "target_clause_text must be the exact clause text. statute_citation must be copied from the event. "
        "suggested_patch must cite the statute and use only numbers from the statute. Set severity "
        "CRITICAL for a hard numeric or mandatory-process violation, WARNING for ambiguous drafting."
    )

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm

    def run(self, document: ContractDocument, events: Iterable[RegulatoryEvent]) -> Tuple[List[ComplianceGap], str]:
        events = list(events)
        deterministic = self._analyze_deterministic(document, events)
        if self.llm is None:
            return deterministic, "deterministic"
        try:
            user = (
                "ACTIVE RULES:\n" + "\n".join(e.model_dump_json() for e in events)
                + "\n\nCONTRACT:\n" + document.model_dump_json()
            )
            result: _GapList = self.llm.structured(_GapList, self.SYSTEM, user)
            merged = self._merge(result.gaps, deterministic, document, events)
            return merged, "llm"
        except Exception as exc:
            log.warning("LLM gap engine failed (%s); using deterministic", exc)
            return deterministic, "deterministic"

    # -- deterministic engine ------------------------------------------------

    def _analyze_deterministic(self, document: ContractDocument, events: List[RegulatoryEvent]) -> List[ComplianceGap]:
        gaps: List[ComplianceGap] = []
        for event in events:
            for clause in document.clauses:
                gap = self._check_clause(document, clause, event)
                if gap is not None:
                    gaps.append(gap)
        return gaps

    def _check_clause(self, document: ContractDocument, clause: ContractClause, event: RegulatoryEvent) -> Optional[ComplianceGap]:
        text = clause.verbatim_text
        low = text.lower()
        if event.rule_type == "USURY_CAP":
            if not re.search(r"\binterest\b|per annum|\bapr\b", low) or re.search(r"\blate\b|delinquen", low):
                return None
            rates = _percents(text)
            if not rates or event.numerical_threshold is None:
                return None
            rate = max(rates)
            if rate <= event.numerical_threshold:
                return None
            return self._gap(
                document, clause, event,
                severity="CRITICAL",
                reason=(
                    f"Clause sets interest at {rate:g}% per annum; {event.statute_citation} caps the rate at "
                    f"{event.numerical_threshold:g}% for {event.jurisdiction} borrowers."
                ),
                threshold=f"{event.numerical_threshold:g}% APR",
                patch=self._usury_patch(text, rate, event),
                confidence=0.97,
            )
        if event.rule_type == "FEE_CAP":
            if not re.search(r"\blate\b|delinquen", low):
                return None
            usd = _dollars(text)
            pcts = _percents(text)
            over_usd = usd and event.numerical_threshold is not None and max(usd) > event.numerical_threshold
            over_pct = pcts and max(pcts) > 5.0
            uses_greater = "greater of" in low
            repeats = bool(re.search(r"each (month|period)|per month|for each month", low))
            if not (over_usd or over_pct or uses_greater or repeats):
                return None
            reasons = []
            if over_usd:
                reasons.append(f"dollar late charge ${max(usd):.2f} exceeds the ${event.numerical_threshold:.2f} cap")
            if over_pct:
                reasons.append(f"{max(pcts):g}% of the installment exceeds the 5% cap")
            if uses_greater:
                reasons.append("'greater of' formula inverts the statutory 'lesser of' test")
            if repeats:
                reasons.append("charge repeats monthly but only one delinquency charge per installment is allowed")
            return self._gap(
                document, clause, event,
                severity="CRITICAL",
                reason=f"Under {event.statute_citation}: " + "; ".join(reasons) + ".",
                threshold=f"lesser of ${event.numerical_threshold:.2f} or 5% of the unpaid installment, once per installment",
                patch=self._fee_patch(text, event),
                confidence=0.98,
            )
        if event.rule_type == "DISCLOSURE_MANDATE":
            auto = bool(re.search(r"automatically enrolled|auto-?enrol", low))
            if not auto:
                return None
            hrs = _hours(text)
            has_notice = "opt-out notice" in low or "written notice" in low
            window_ok = bool(hrs) and event.numerical_threshold is not None and max(hrs) >= event.numerical_threshold
            if has_notice and window_ok:
                return None
            missing = []
            if not has_notice:
                missing.append("no separate written opt-out notice")
            if not window_ok:
                missing.append(f"no {event.numerical_threshold:g}-hour opt-out window before the first charge")
            return self._gap(
                document, clause, event,
                severity="CRITICAL",
                reason=f"Automatic enrollment in an optional product with " + " and ".join(missing) + f", contrary to {event.statute_citation}.",
                threshold=f"{event.numerical_threshold:g}-hour opt-out window with separate written notice",
                patch=self._disclosure_patch(text, event),
                confidence=0.95,
            )
        if event.rule_type == "REPORTING_DEADLINE":
            if "report" not in low:
                return None
            return self._gap(
                document, clause, event,
                severity="WARNING",
                reason=f"Clause references reporting obligations; confirm alignment with {event.statute_citation}.",
                threshold=None,
                patch=text,
                confidence=0.6,
            )
        return None

    def _gap(self, document, clause, event, *, severity, reason, threshold, patch, confidence) -> ComplianceGap:
        return ComplianceGap(
            gap_id=_stable_id("gap", document.document_id, clause.clause_id, event.event_id),
            severity=severity,
            statute_citation=event.statute_citation,
            target_clause_id=clause.clause_id,
            target_clause_text=clause.verbatim_text,
            violation_reason=reason,
            statutory_threshold_violated=threshold,
            suggested_patch=patch,
            confidence_score=confidence,
            is_grounded_in_citation=event.statute_citation in patch,
            jurisdiction=event.jurisdiction,
            rule_type=event.rule_type,
            statutory_source_snippet=event.raw_source_snippet,
        )

    @staticmethod
    def _usury_patch(text: str, rate: float, event: RegulatoryEvent) -> str:
        cap = event.numerical_threshold
        return (
            f"{text} Notwithstanding the foregoing, for Borrowers residing in {event.jurisdiction}, the interest "
            f"rate shall not exceed {cap:g}% per annum, the maximum rate permitted under {event.statute_citation}, "
            f"and any rate stated above in excess of {cap:g}% shall be reduced to {cap:g}% for such Borrowers."
        )

    @staticmethod
    def _fee_patch(text: str, event: RegulatoryEvent) -> str:
        """Rewrite the offending formula in place rather than appending an
        override, so the corrected clause re-audits clean."""
        cap = event.numerical_threshold if event.numerical_threshold is not None else 15.0
        patched = re.sub(r"(?i)\bgreater of\b", "lesser of", text)
        patched = _USD_RE.sub(lambda m: f"${cap:.2f}" if float(m.group(1).replace(",", "")) > cap else m.group(0), patched)
        patched = _PCT_RE.sub(lambda m: "five percent (5%)" if float(m.group(1)) > 5.0 else m.group(0), patched)
        patched = re.sub(r"(?i)[^.]*\b(?:each|per) month\b[^.]*\.", "", patched).strip()
        if not re.search(r"(?i)only (?:one|once)", patched):
            patched += " Only one such charge may be collected on any one installment."
        return f"{patched} This charge is limited as required by {event.statute_citation}."

    @staticmethod
    def _disclosure_patch(text: str, event: RegulatoryEvent) -> str:
        hrs = int(event.numerical_threshold or 48)
        return (
            f"Borrower may elect to enroll in Lender's Payment Protection Plan. Where Borrower is enrolled, Lender "
            f"shall deliver a written opt-out notice separately from this Agreement and shall not assess any charge "
            f"for the Plan until at least {hrs} hours after delivery of that notice, during which Borrower may opt out "
            f"without charge, as required by {event.statute_citation}."
        )

    # -- LLM merge -----------------------------------------------------------

    def _merge(self, llm_gaps: List[ComplianceGap], det_gaps: List[ComplianceGap], document: ContractDocument, events: List[RegulatoryEvent]) -> List[ComplianceGap]:
        """Deterministic findings are ground truth; LLM findings are kept only when
        they point at a real clause, a real citation, and use only statutory numbers."""
        clauses = {c.clause_id: c for c in document.clauses}
        cites = {e.statute_citation: e for e in events}
        det_keys = {(g.target_clause_id, g.statute_citation) for g in det_gaps}
        merged = list(det_gaps)
        for g in llm_gaps:
            if g.target_clause_id not in clauses or g.statute_citation not in cites:
                continue
            if (g.target_clause_id, g.statute_citation) in det_keys:
                continue
            event = cites[g.statute_citation]
            g.target_clause_text = clauses[g.target_clause_id].verbatim_text
            g.jurisdiction = event.jurisdiction
            g.rule_type = event.rule_type
            g.statutory_source_snippet = event.raw_source_snippet
            g.is_grounded_in_citation = event.statute_citation in g.suggested_patch
            g.confidence_score = min(g.confidence_score, 0.8)
            g.gap_id = _stable_id("gap", document.document_id, g.target_clause_id, event.event_id)
            merged.append(g)
        return merged


# ---------------------------------------------------------------------------
# Agent C: Deterministic Remediation & Verifier (LLM-as-a-judge)
# ---------------------------------------------------------------------------


class RemediationVerifier:
    """Agent C. Produces a redline for a gap and verifies it is grounded."""

    DRAFT_SYSTEM = (
        "You are a regulatory drafting attorney. Rewrite the offending clause so it complies with the cited "
        "statute. Cite the statute inline. Use ONLY numbers that appear in the statute snippet. Do not add "
        "obligations the statute does not impose. Keep every compliant term of the original clause."
    )
    JUDGE_SYSTEM = (
        "You are an independent grounding judge. Given a statute snippet, its citation, and a proposed redline, "
        "verify: (1) the citation appears verbatim in the redline; (2) every number in the redline appears in "
        "the statute snippet or is a non-regulatory term carried over from the original clause; (3) the redline "
        "imposes no obligation absent from the statute. Be strict."
    )

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm

    def run(self, gap: ComplianceGap, document: ContractDocument, event: Optional[RegulatoryEvent]) -> RemediationPatch:
        original = gap.target_clause_text
        snippet = event.raw_source_snippet if event else gap.statutory_source_snippet
        redline, rationale = gap.suggested_patch, self._rationale(gap)
        if self.llm is not None:
            try:
                user = (
                    f"CITATION: {gap.statute_citation}\nSTATUTE SNIPPET: {snippet}\n"
                    f"VIOLATION: {gap.violation_reason}\nORIGINAL CLAUSE: {original}\n"
                    f"DETERMINISTIC DRAFT (must remain at least this strict): {gap.suggested_patch}"
                )
                draft: _Redline = self.llm.structured(_Redline, self.DRAFT_SYSTEM, user)
                if draft.redlined_text.strip():
                    redline, rationale = draft.redlined_text.strip(), draft.change_rationale.strip()
            except Exception as exc:
                log.warning("LLM redline failed (%s); using deterministic patch", exc)
        verdict = self.judge(gap, redline, original, snippet)
        if not verdict.is_grounded and redline != gap.suggested_patch:
            # Fall back to the deterministic patch, which is grounded by construction.
            log.info("LLM redline for %s failed grounding; reverting to deterministic patch", gap.gap_id)
            redline, rationale = gap.suggested_patch, self._rationale(gap)
            verdict = self.judge(gap, redline, original, snippet)
        return RemediationPatch(
            gap_id=gap.gap_id,
            document_id=document.document_id,
            target_clause_id=gap.target_clause_id,
            original_text=original,
            redlined_text=redline,
            statute_citation=gap.statute_citation,
            change_rationale=rationale,
            grounding=verdict,
        )

    @staticmethod
    def _rationale(gap: ComplianceGap) -> str:
        return (
            f"Conforms clause {gap.target_clause_id} to {gap.statute_citation}: {gap.violation_reason} "
            f"Binding threshold: {gap.statutory_threshold_violated or 'see statute'}."
        )

    def judge(self, gap: ComplianceGap, redline: str, original: str, snippet: str) -> GroundingVerdict:
        deterministic = self.deterministic_judge(gap, redline, original, snippet)
        if self.llm is None:
            return deterministic
        try:
            user = (
                f"CITATION: {gap.statute_citation}\nSTATUTE SNIPPET: {snippet}\nORIGINAL CLAUSE: {original}\n"
                f"PROPOSED REDLINE: {redline}"
            )
            llm_verdict: GroundingVerdict = self.llm.structured(GroundingVerdict, self.JUDGE_SYSTEM, user)
            # Both judges must agree for the patch to count as grounded.
            return GroundingVerdict(
                is_grounded=deterministic.is_grounded and llm_verdict.is_grounded,
                cited_statute_present=deterministic.cited_statute_present and llm_verdict.cited_statute_present,
                numbers_match_statute=deterministic.numbers_match_statute and llm_verdict.numbers_match_statute,
                no_invented_obligations=deterministic.no_invented_obligations and llm_verdict.no_invented_obligations,
                judge_rationale=f"LLM judge: {llm_verdict.judge_rationale} | Deterministic judge: {deterministic.judge_rationale}",
                confidence=min(deterministic.confidence, llm_verdict.confidence),
            )
        except Exception as exc:
            log.warning("LLM judge failed (%s); deterministic verdict stands", exc)
            return deterministic

    @staticmethod
    def deterministic_judge(gap: ComplianceGap, redline: str, original: str, snippet: str) -> GroundingVerdict:
        cited = gap.statute_citation in redline
        allowed_numbers = (
            set(_all_numbers(snippet))
            | set(_all_numbers(original))
            | set(_all_numbers(gap.statutory_threshold_violated or ""))
            | set(_all_numbers(gap.statute_citation))
        )
        redline_numbers = set(_all_numbers(redline.replace(gap.statute_citation, "")))
        stray = sorted(n for n in redline_numbers if n not in allowed_numbers)
        numbers_ok = not stray
        invented = _invented_obligations(redline, original, snippet)
        no_invented = not invented
        reasons = []
        reasons.append("citation present" if cited else f"citation '{gap.statute_citation}' missing from redline")
        reasons.append("all numbers trace to statute or original clause" if numbers_ok else f"unsourced numbers in redline: {stray}")
        reasons.append("no new obligations detected" if no_invented else f"possible invented obligations: {invented}")
        grounded = cited and numbers_ok and no_invented
        confidence = 0.99 if grounded else (0.6 if cited else 0.2)
        return GroundingVerdict(
            is_grounded=grounded,
            cited_statute_present=cited,
            numbers_match_statute=numbers_ok,
            no_invented_obligations=no_invented,
            judge_rationale="; ".join(reasons),
            confidence=confidence,
        )


_NUM_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_OBLIGATION_RE = re.compile(r"\b(?:shall|must|is required to|agrees to)\s+([a-z][a-z\- ]{2,40}?)(?=[,.;]|\s(?:and|or|the|a|an|any|to|of|under|as)\b)", re.IGNORECASE)


def _all_numbers(text: str) -> List[float]:
    out = []
    for m in _NUM_RE.finditer(text or ""):
        try:
            out.append(float(m.group(0).replace(",", "")))
        except ValueError:
            continue
    return out


def _invented_obligations(redline: str, original: str, snippet: str) -> List[str]:
    """Verbs of obligation in the redline whose predicate word is absent from
    both the original clause and the statute snippet."""
    corpus = (original + " " + snippet).lower()
    found: List[str] = []
    for m in _OBLIGATION_RE.finditer(redline):
        head = m.group(1).strip().lower().split(" ")[0]
        if head and head not in corpus and head not in {"pay", "deliver", "not", "be"}:
            found.append(head)
    return found


# ---------------------------------------------------------------------------
# Pipeline facade
# ---------------------------------------------------------------------------


class CertoPipeline:
    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm
        self.extractor = StatutoryDeltaExtractor(llm)
        self.gap_engine = GapAnalysisEngine(llm)
        self.remediator = RemediationVerifier(llm)

    @property
    def mode(self) -> str:
        return "llm" if self.llm else "deterministic"
