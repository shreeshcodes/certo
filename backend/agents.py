"""Certo multi-agent reasoning pipeline.

Three agents, each with two execution paths:

* ``llm``            -- Instructor-wrapped OpenAI or Anthropic call, forced into a
                        Pydantic schema. Selected when OPENAI_API_KEY or
                        ANTHROPIC_API_KEY is present (CERTO_LLM_PROVIDER overrides).
* ``deterministic``  -- Pure-Python statutory rule engine. Always available, used as
                        the offline path and as the ground truth that keeps LLM
                        output honest.

Agent A  StatutoryDeltaExtractor   statute / bulletin text  -> List[RegulatoryEvent]
Agent B  GapAnalysisEngine         contract + events        -> List[ComplianceGap]
Agent C  RemediationVerifier       gap                      -> RemediationPatch (+ judge)
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
    FeeCapSpec,
    FeeKind,
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

_WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_WORD_NUM_RE = r"(?:(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen)"


def _words_to_number(text: str) -> Optional[float]:
    parts = re.split(r"[- ]", text.strip().lower())
    total = 0
    for p in parts:
        if p not in _WORD_NUM:
            return None
        total += _WORD_NUM[p]
    return float(total)


_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:percent|per centum|%)", re.IGNORECASE)
_PCT_WORD_RE = re.compile(rf"\b({_WORD_NUM_RE})\s+(?:percent|per centum)\b", re.IGNORECASE)
_USD_RE = re.compile(r"\$\s?(\d+(?:,\d{3})*(?:\.\d{1,2})?)")
_CENTS_PER_DOLLAR_RE = re.compile(rf"\b({_WORD_NUM_RE}|\d+)\s+cents?\s+(?:for\s+each|per)\s+(?:\$1|dollar)\b", re.IGNORECASE)
_DAYS_RE = re.compile(r"(?:(\d+)|\b(" + _WORD_NUM_RE + r")\b)\s*(?:\((\d+)\))?\s*(?:calendar\s+|business\s+)?days?\b", re.IGNORECASE)
_ORDINAL_DAY_RE = re.compile(r"after the (\d+)(?:st|nd|rd|th) day", re.IGNORECASE)
_MONTHS_RE = re.compile(r"(\d+)\s*months?\b", re.IGNORECASE)
_HOURS_RE = re.compile(r"(?:(\d+)|\b(" + _WORD_NUM_RE + r")\b)\s*(?:\((\d+)\))?\s*hours?\b", re.IGNORECASE)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_BLANK_RE = re.compile(r"_{3,}")

_CODE_NAMES = {
    "TX": "Tex. Fin. Code",
    "CA": "Cal. Fin. Code",
    "NY": "N.Y. Gen. Oblig. Law",
    "FED": "U.S.C.",
}
_CITE_INLINE_RE = re.compile(
    r"((?:Tex(?:as)?\.?\s+Fin(?:ance)?\.?\s+Code|California Financial Code|Cal\.?\s+Fin\.?\s+Code|"
    r"N\.Y\.\s+Gen\.\s+Oblig\.\s+Law|N\.Y\.\s+Banking\s+Law|N\.Y\.\s+Penal\s+Law|N\.Y\.\s+Fin\.\s+Serv\.\s+Law|"
    r"Business\s+&\s+Commerce\s+Code|Cal\.?\s+Code\s+Regs\.[^§]*)"
    r"\s*§\s*([\d.\-]+(?:\([a-z0-9]+\))*))",
    re.IGNORECASE,
)
_CITE_SEC_RE = re.compile(r"\bSec\.\s*(\d+[A-Za-z]?\.\d+)\.")
_CITE_BARE_RE = re.compile(r"(?:^|\n)\s*(\d{4,5}(?:\.\d+)?)\.\s")
_CITE_SYMBOL_RE = re.compile(r"§\s*(\d+(?:[.\-][\dA-Za-z]+)*(?:\([a-z0-9]+\))*)")


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]
    return f"{prefix}-{digest}"


def _percents(text: str) -> List[float]:
    """Percentages in textual order, digits or words ('five percent')."""
    found: List[Tuple[int, float]] = [(m.start(), float(m.group(1))) for m in _PCT_RE.finditer(text)]
    for m in _PCT_WORD_RE.finditer(text):
        v = _words_to_number(m.group(1))
        if v is not None:
            found.append((m.start(), v))
    return [v for _, v in sorted(found)]


def _dollars(text: str) -> List[float]:
    return [float(m.group(1).replace(",", "")) for m in _USD_RE.finditer(text)]


def _days(text: str) -> List[float]:
    out: List[float] = []
    for m in _DAYS_RE.finditer(text):
        if m.group(3):
            out.append(float(m.group(3)))
        elif m.group(1):
            out.append(float(m.group(1)))
        elif m.group(2):
            v = _words_to_number(m.group(2))
            if v is not None:
                out.append(v)
    out += [float(m.group(1)) for m in _ORDINAL_DAY_RE.finditer(text)]
    return out


def _hours(text: str) -> List[float]:
    out: List[float] = []
    for m in _HOURS_RE.finditer(text):
        if m.group(3):
            out.append(float(m.group(3)))
        elif m.group(1):
            out.append(float(m.group(1)))
        elif m.group(2):
            v = _words_to_number(m.group(2))
            if v is not None:
                out.append(v)
    return out


def _cents_per_dollar(text: str) -> Optional[float]:
    m = _CENTS_PER_DOLLAR_RE.search(text)
    if not m:
        return None
    raw = m.group(1)
    return float(raw) if raw.isdigit() else _words_to_number(raw)


def _normalize_citation(raw: str) -> str:
    raw = re.sub(r"\s+", " ", raw).strip()
    raw = re.sub(r"(?i)^tex(?:as)?\.?\s+fin(?:ance)?\.?\s+code", "Tex. Fin. Code", raw)
    raw = re.sub(r"(?i)^california financial code", "Cal. Fin. Code", raw)
    raw = re.sub(r"(?i)^cal\.?\s+fin\.?\s+code", "Cal. Fin. Code", raw)
    return raw


def _sentence_containing(para: str, needle: re.Pattern) -> str:
    sentences = re.split(r"(?<=[.;])\s+(?=[A-Z(])", para)
    for s in sentences:
        if needle.search(s):
            return s.strip()
    return sentences[0].strip()


# ---------------------------------------------------------------------------
# Fee formulas: shared by the extractor (statute side) and the gap engine
# (contract side)
# ---------------------------------------------------------------------------


@dataclass
class FeeFormula:
    kind: FeeKind
    combinator: str  # FLAT_USD | FLAT_PCT | LESSER_OF | GREATER_OF | UNQUANTIFIED
    usd: Optional[float]
    pct: Optional[float]
    grace_days: Optional[float]
    once: bool
    repeats: bool

    def amount(self, installment: float) -> Optional[float]:
        usd = self.usd
        pct_amt = installment * self.pct / 100.0 if self.pct is not None else None
        if self.combinator == "GREATER_OF":
            return max(v for v in (usd, pct_amt) if v is not None)
        if self.combinator == "LESSER_OF":
            return min(v for v in (usd, pct_amt) if v is not None)
        if self.combinator == "FLAT_USD":
            return usd
        if self.combinator == "FLAT_PCT":
            return pct_amt
        return None

    def describe(self) -> str:
        if self.combinator == "GREATER_OF":
            return f"greater of ${self.usd:.2f} or {self.pct:g}% of the payment"
        if self.combinator == "LESSER_OF":
            return f"lesser of ${self.usd:.2f} or {self.pct:g}% of the payment"
        if self.combinator == "FLAT_USD":
            return f"${self.usd:.2f} flat"
        if self.combinator == "FLAT_PCT":
            return f"{self.pct:g}% of the payment"
        return "unquantified"


def _fee_kind(text: str) -> Optional[FeeKind]:
    low = text.lower()
    if re.search(r"insufficient funds|returned (?:payment|check|item)|dishonored|nsf\b|failed automated withdrawal", low):
        return "NSF"
    if re.search(r"\blate (?:charge|fee|payment charge)|delinquen|default charge|additional interest for default", low):
        return "LATE"
    if "origination fee" in low:
        return "ORIGINATION"
    if "administrative fee" in low:
        return "ADMIN"
    return None


_FEE_SENTENCE_KEYS = {
    "LATE": r"late (?:charge|fee|payment charge)|delinquen|default charge|additional interest(?: for default)?|cents for each \$1|cents per dollar|not paid|past due|in default",
    "NSF": r"insufficient funds|returned|dishonored|nsf\b|failed automated withdrawal|processing fee",
    "ORIGINATION": r"origination fee",
    "ADMIN": r"administrative fee",
    "OTHER": r"charge",
}


def _fee_sentences(text: str, kind: FeeKind) -> str:
    """Only the sentences that talk about this fee kind, so unrelated dollar
    figures elsewhere in a long clause cannot masquerade as the fee."""
    key = re.compile(_FEE_SENTENCE_KEYS[kind], re.IGNORECASE)
    sentences = re.split(r"(?<=[.;])\s+(?=[A-Z(\u201c\"])", text)
    picked = [s for s in sentences if key.search(s)]
    return " ".join(picked) if picked else ""


def parse_fee_formula(text: str, kind: Optional[FeeKind] = None) -> Optional[FeeFormula]:
    kind = kind or _fee_kind(text)
    if kind is None:
        return None
    scope = _fee_sentences(text, kind)
    if not scope:
        return FeeFormula(kind, "UNQUANTIFIED", None, None, None, False, False)
    low = scope.lower()
    cents = _cents_per_dollar(scope)
    scope_for_usd = _CENTS_PER_DOLLAR_RE.sub(" ", scope)
    usd = _dollars(scope_for_usd)
    pct = _percents(scope)
    if cents is not None:
        pct = [cents] + pct
    # A cap sentence ("not to exceed", "greater of") is the binding one when present.
    cap = _sentence_containing(scope, re.compile(r"not to exceed|may not exceed|not in excess of|not exceeding|greater of|lesser of|whichever is less|equal to", re.IGNORECASE))
    comb_m = re.search(r"(?i)(?:greater|lesser) of|whichever is less", cap)
    cap_tail = cap[comb_m.start():] if comb_m and comb_m.group(0).lower() != "whichever is less" else cap
    cap_usd = _dollars(_CENTS_PER_DOLLAR_RE.sub(" ", cap_tail))
    cap_pct = ([_cents_per_dollar(cap_tail)] if _cents_per_dollar(cap_tail) is not None else []) + _percents(cap_tail)
    usd_v = (cap_usd or usd or [None])[0]
    pct_v = (cap_pct or pct or [None])[0]
    if re.search(r"greater of", low) and usd_v is not None and pct_v is not None:
        comb = "GREATER_OF"
    elif re.search(r"lesser of|whichever is less", low) and usd_v is not None and pct_v is not None:
        comb = "LESSER_OF"
    elif cents is not None:
        comb, usd_v = "FLAT_PCT", None
    elif usd_v is not None and pct_v is None:
        comb = "FLAT_USD"
    elif pct_v is not None and usd_v is None:
        comb = "FLAT_PCT"
    elif usd_v is not None and pct_v is not None:
        comb = "LESSER_OF" if ("not exceed" in low or "not in excess" in low) else "GREATER_OF"
    else:
        comb = "UNQUANTIFIED"
    days = _days(scope)
    grace = min(days) if days else None
    once = bool(re.search(r"only (?:one|once)|not (?:be )?collected more than once|may not be collected more than once|only be charged once|no more than once", low))
    repeats = bool(re.search(r"(?:for )?each (?:month|period)|per month", low)) and not once
    return FeeFormula(kind, comb, usd_v, pct_v, grace, once, repeats)


def statute_fee_amount(spec: FeeCapSpec, installment: float) -> Optional[float]:
    pct_amt = installment * spec.pct_max / 100.0 if spec.pct_max is not None else None
    if spec.combinator == "PROHIBITED":
        return 0.0
    if spec.combinator == "GREATER_OF":
        return max(v for v in (spec.usd_max, pct_amt) if v is not None)
    if spec.combinator == "LESSER_OF":
        return min(v for v in (spec.usd_max, pct_amt) if v is not None)
    if spec.combinator == "FLAT_USD":
        return spec.usd_max
    if spec.combinator == "FLAT_PCT":
        return pct_amt
    return None


def describe_cap(spec: FeeCapSpec) -> str:
    if spec.combinator == "PROHIBITED":
        base = "no charge permitted"
    elif spec.combinator == "GREATER_OF":
        base = f"greater of ${spec.usd_max:.2f} or {spec.pct_max:g}% of the installment"
    elif spec.combinator == "LESSER_OF":
        base = f"lesser of ${spec.usd_max:.2f} or {spec.pct_max:g}% of the installment"
    elif spec.combinator == "FLAT_USD":
        base = f"${spec.usd_max:.2f} maximum"
    else:
        base = f"{spec.pct_max:g}% of the installment maximum"
    if spec.min_grace_days:
        base += f", only after {spec.min_grace_days} days past due"
    if spec.once_per_installment:
        base += ", once per installment"
    return base


_INSTALLMENT_SIZES = (50.0, 100.0, 200.0, 300.0, 500.0, 1000.0, 2000.0)


# ---------------------------------------------------------------------------
# Agent A: Statutory Delta Extractor
# ---------------------------------------------------------------------------

_RULE_KEYWORDS: Sequence[Tuple[RuleType, Tuple[str, ...]]] = (
    ("FEE_CAP", ("delinquency", "late charge", "late fee", "default charge", "additional interest for default", "administrative fee", "processing fee", "dishonored", "delinquency fee", "cents for each $1", "cents per dollar", "any interest or charge of any nature unless a loan is made")),
    ("PREPAYMENT_PENALTY", ("prepayment penalty", "prepay")),
    ("TERM_LIMIT", ("term of the loan", "maximum term", "term that exceeds", "months and 15 days", "term of less than")),
    ("DISCLOSURE_MANDATE", ("disclos", "deliver to the borrower", "statement showing", "written notice", "opt-out", "shall disclose")),
    ("REPORTING_DEADLINE", ("report to", "annual report", "file with the commissioner", "reporting agency")),
    ("USURY_CAP", ("rate of interest", "interest", "per centum per annum", "ceiling", "usury", "usurious", "annual simple interest")),
)


class StatutoryDeltaExtractor:
    """Agent A. Parses raw statute or bulletin text into RegulatoryEvent records."""

    SYSTEM = (
        "You are a statutory extraction engine for US consumer-lending regulators. "
        "Read the text and emit one RegulatoryEvent per distinct rule. "
        "statute_citation must be copied exactly as it appears. raw_source_snippet must be a "
        "verbatim substring of the text. numerical_threshold is the binding number for the rule "
        "(dollar cap, APR percent, percent of installment, hours, days, months). Never invent rules that are not in the text."
    )

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm

    def run(
        self,
        jurisdiction: Jurisdiction,
        agency: str,
        raw_text: str,
        published_date: Optional[str] = None,
        code_name: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> Tuple[List[RegulatoryEvent], str]:
        deterministic = self._extract_deterministic(jurisdiction, agency, raw_text, published_date, code_name, source_url)
        if self.llm is None:
            return deterministic, "deterministic"
        try:
            user = f"Jurisdiction: {jurisdiction}\nAgency: {agency}\nCitation prefix: {code_name or _CODE_NAMES[jurisdiction]}\n\nTEXT:\n{raw_text}"
            result: _EventList = self.llm.structured(_EventList, self.SYSTEM, user)
            events = [e for e in result.events if self._snippet_is_verbatim(e, raw_text)]
            if not events:
                log.warning("LLM extractor returned no verbatim-grounded events; using deterministic")
                return deterministic, "deterministic"
            for e in events:
                e.jurisdiction = jurisdiction
                e.agency = agency
                e.verification.source_url = source_url
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
            if d is None:
                continue
            if d.numerical_threshold is not None and e.numerical_threshold != d.numerical_threshold:
                log.info("threshold conflict on %s: llm=%s det=%s", e.statute_citation, e.numerical_threshold, d.numerical_threshold)
                e.numerical_threshold = d.numerical_threshold
                e.threshold_unit = d.threshold_unit
            if d.fee_cap is not None:
                e.fee_cap = d.fee_cap
        return llm_events

    # -- deterministic extractor -------------------------------------------

    def _extract_deterministic(
        self,
        jurisdiction: Jurisdiction,
        agency: str,
        raw_text: str,
        published_date: Optional[str],
        code_name: Optional[str],
        source_url: Optional[str],
    ) -> List[RegulatoryEvent]:
        code = code_name or _CODE_NAMES[jurisdiction]
        effective = self._effective_date(raw_text, published_date)
        events: List[RegulatoryEvent] = []
        for citation, block in self._blocks(raw_text, code):
            for sub_cite, para in self._subsections(citation, block):
                rule_type = self._classify(para)
                if rule_type is None:
                    continue
                threshold, unit, snippet, fee_cap = self._threshold(rule_type, para, block)
                if threshold is None and fee_cap is None and rule_type in ("FEE_CAP", "USURY_CAP", "TERM_LIMIT"):
                    continue
                events.append(
                    RegulatoryEvent(
                        event_id=_stable_id("evt", jurisdiction, sub_cite, rule_type),
                        jurisdiction=jurisdiction,
                        agency=agency,
                        statute_citation=sub_cite,
                        effective_date=effective,
                        rule_type=rule_type,
                        summary=self._summary(rule_type, threshold, unit, sub_cite, fee_cap),
                        raw_source_snippet=snippet,
                        numerical_threshold=threshold,
                        threshold_unit=unit,
                        fee_cap=fee_cap,
                        verification={"status": "UNVERIFIED", "confidence": 0.6, "source_url": source_url, "notes": "machine-extracted; not yet checked by a human"},
                    )
                )
        # collapse duplicates that share citation + rule type
        seen = {}
        for e in events:
            seen.setdefault((e.statute_citation, e.rule_type), e)
        return list(seen.values())

    @staticmethod
    def _blocks(raw_text: str, code: str) -> List[Tuple[str, str]]:
        """Split text into (citation, text) blocks by whichever citation style the source uses."""
        text = raw_text.replace("\r\n", "\n")
        sec_hits = list(_CITE_SEC_RE.finditer(text))
        if sec_hits:
            return [
                (f"{code} § {m.group(1)}", text[m.start(): sec_hits[i + 1].start() if i + 1 < len(sec_hits) else len(text)])
                for i, m in enumerate(sec_hits)
            ]
        bare_hits = list(_CITE_BARE_RE.finditer(text))
        if bare_hits:
            return [
                (f"{code} § {m.group(1)}", text[m.start(): bare_hits[i + 1].start() if i + 1 < len(bare_hits) else len(text)])
                for i, m in enumerate(bare_hits)
            ]
        blocks: List[Tuple[str, str]] = []
        for para in re.split(r"\n\s*\n|\n(?=\d+\.\s)", text):
            if not para.strip():
                continue
            inline = [_normalize_citation(m.group(1)) for m in _CITE_INLINE_RE.finditer(para)]
            if inline:
                blocks.append((inline[0], para))
                continue
            sym = _CITE_SYMBOL_RE.search(para)
            if sym:
                blocks.append((f"{code} § {sym.group(1)}", para))
        return blocks

    @staticmethod
    def _subsections(citation: str, block: str) -> List[Tuple[str, str]]:
        """Split a section into lettered subsections so each rule keeps a precise citation."""
        parts = re.split(r"(?=\((?:[a-z]|[a-z]-\d)\)\s)", block)
        if len(parts) <= 2:
            return [(citation, re.sub(r"\s+", " ", block).strip())]
        out: List[Tuple[str, str]] = []
        for p in parts:
            m = re.match(r"\(([a-z](?:-\d)?)\)\s", p)
            if not m:
                continue
            base = citation.split("(")[0].strip()
            out.append((f"{base}({m.group(1)})", re.sub(r"\s+", " ", p).strip()))
        return out or [(citation, re.sub(r"\s+", " ", block).strip())]

    @staticmethod
    def _effective_date(raw_text: str, published_date: Optional[str]) -> str:
        m = re.search(r"Effective\s+(\d{4}-\d{2}-\d{2})", raw_text, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"eff\.\s+(?:(\w+)\.?\s+(\d{1,2}),\s+(\d{4}))", raw_text)
        if m:
            months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
            mo = months.get(m.group(1).lower()[:4]) or months.get(m.group(1).lower()[:3])
            if mo:
                return f"{m.group(3)}-{mo:02d}-{int(m.group(2)):02d}"
        if published_date:
            return published_date
        m = _DATE_RE.search(raw_text)
        return m.group(1) if m else "1970-01-01"

    @staticmethod
    def _classify(para: str) -> Optional[RuleType]:
        low = para.lower()
        if len(low) < 40:
            return None
        for rule_type, keys in _RULE_KEYWORDS:
            if any(k in low for k in keys):
                if rule_type == "USURY_CAP" and not (_percents(para) or "usur" in low):
                    continue
                return rule_type
        return None

    def _threshold(self, rule_type: RuleType, para: str, block: str = ""):
        if rule_type == "FEE_CAP":
            low = para.lower()
            block_low = (block or para).lower()
            kind: FeeKind = "NSF" if re.search(r"dishonored|returned|insufficient", low) else ("ADMIN" if "administrative fee" in low else "LATE")
            prohibited = "unless a loan is made" in low
            formula = parse_fee_formula(para, kind)
            cap_sentence = _sentence_containing(para, re.compile(r"may not exceed|not to exceed|not in excess of|not exceeding|maximum|greater of|lesser of|unless a loan is made", re.IGNORECASE))
            if prohibited:
                spec = FeeCapSpec(fee_kind="OTHER", combinator="PROHIBITED", once_per_installment=False)
                return None, None, cap_sentence, spec
            if formula is None or formula.combinator == "UNQUANTIFIED":
                return None, None, cap_sentence, None
            if formula.combinator in ("GREATER_OF", "LESSER_OF") and re.search(r"(?i)10 percent a year or less", para):
                pass  # § 302.001(d) style: the 10% is the loan-rate scope, not the fee; formula already scoped to the cap sentence
            grace = None
            days = _days(para) or _days(block or "")
            if days:
                grace = int(min(days))
            comb = formula.combinator
            usd_max, pct_max = formula.usd, formula.pct
            if kind == "LATE" and re.search(r"not less than (\d+) days|not less than \d+ days", low):
                # CA § 22320.5 style: tiered flat dollar caps by days in default; take the highest tier
                tiers = re.findall(r"not less than (\d+) days, an amount not in excess of [a-z ]*\(\$(\d+)\)", low)
                if tiers:
                    grace = int(min(int(t[0]) for t in tiers))
                    usd_max = max(float(t[1]) for t in tiers)
                    comb, pct_max = "FLAT_USD", None
            once = formula.once or bool(re.search(r"more than once|only once|only one", block_low))
            spec = FeeCapSpec(fee_kind=kind, combinator=comb, usd_max=usd_max, pct_max=pct_max, min_grace_days=grace, once_per_installment=once)
            threshold = pct_max if comb in ("FLAT_PCT",) else usd_max if comb == "FLAT_USD" else (usd_max if usd_max is not None else pct_max)
            unit = "PERCENT_OF_INSTALLMENT" if comb == "FLAT_PCT" else "USD"
            return threshold, unit, cap_sentence, spec
        if rule_type == "USURY_CAP":
            binding = re.compile(r"maximum|may not exceed|not exceeding|not exceed|ceiling is|shall be|exceeding", re.IGNORECASE)
            snippet = _sentence_containing(para, binding)
            local = _percents(snippet)
            pcts = local or _percents(para)
            if not pcts:
                return None, None, snippet, None
            monthly = bool(re.search(r"per month|a month", snippet, re.IGNORECASE))
            return max(pcts), ("PERCENT_PER_MONTH" if monthly else "PERCENT_APR"), snippet, None
        if rule_type == "PREPAYMENT_PENALTY":
            snippet = _sentence_containing(para, re.compile(r"prepay", re.IGNORECASE))
            pcts = _percents(snippet)
            return (pcts[0] if pcts else 0.0), ("PERCENT_APR" if pcts else None), snippet, None
        if rule_type == "TERM_LIMIT":
            snippet = _sentence_containing(para, re.compile(r"months?", re.IGNORECASE))
            months = [float(m.group(1)) for m in _MONTHS_RE.finditer(snippet)]
            return (months[0] if months else None), ("MONTHS" if months else None), snippet, None
        if rule_type == "DISCLOSURE_MANDATE":
            hrs = _hours(para)
            snippet = _sentence_containing(para, re.compile(r"hours?|disclos|deliver|statement|notice", re.IGNORECASE))
            return (hrs[0] if hrs else None), ("HOURS" if hrs else None), snippet, None
        days = _days(para)
        snippet = _sentence_containing(para, re.compile(r"days?|deadline|report", re.IGNORECASE))
        return (days[0] if days else None), ("DAYS" if days else None), snippet, None

    @staticmethod
    def _summary(rule_type: RuleType, threshold, unit, citation: str, fee_cap: Optional[FeeCapSpec]) -> str:
        if rule_type == "FEE_CAP" and fee_cap is not None:
            return f"{fee_cap.fee_kind.title()} fee limited to {describe_cap(fee_cap)} under {citation}."
        if rule_type == "USURY_CAP" and threshold is not None:
            per = "per month" if unit == "PERCENT_PER_MONTH" else "per annum"
            return f"Maximum permissible interest rate is {threshold:g}% {per} under {citation}."
        if rule_type == "PREPAYMENT_PENALTY":
            return f"Prepayment penalty restricted under {citation}."
        if rule_type == "TERM_LIMIT" and threshold is not None:
            return f"Loan term limit of {threshold:g} months under {citation}."
        if rule_type == "DISCLOSURE_MANDATE":
            return f"Disclosure or notice mandate under {citation}."
        if rule_type == "REPORTING_DEADLINE":
            return f"Reporting obligation under {citation}."
        return f"{rule_type.replace('_', ' ').title()} rule under {citation}."


# ---------------------------------------------------------------------------
# Agent B: Gap Analysis & Policy Diff Engine
# ---------------------------------------------------------------------------


class GapAnalysisEngine:
    """Agent B. Diffs every contract clause against every active rule."""

    SYSTEM = (
        "You are a compliance gap analyst. For each active RegulatoryEvent, decide whether any "
        "contract clause violates it. Emit a ComplianceGap ONLY when the clause text contains a "
        "term (rate, fee, notice period, prepayment term, loan term) that conflicts with the statute. "
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
        handler = {
            "USURY_CAP": self._check_usury,
            "FEE_CAP": self._check_fee,
            "DISCLOSURE_MANDATE": self._check_disclosure,
            "PREPAYMENT_PENALTY": self._check_prepayment,
            "TERM_LIMIT": self._check_term,
            "REPORTING_DEADLINE": self._check_reporting,
        }[event.rule_type]
        return handler(document, clause, event)

    # USURY --------------------------------------------------------------

    def _check_usury(self, document, clause, event) -> Optional[ComplianceGap]:
        text, low = clause.verbatim_text, clause.verbatim_text.lower()
        if not re.search(r"\b(?:interest|per annum|apr)\b", low) or re.search(r"\blate\b|delinquen|dishonor|insufficient", low):
            return None
        if not re.search(r"rate of|at a rate|per annum|fixed rate|interest rate", low):
            return None
        if event.numerical_threshold is None:
            return None
        cap = event.numerical_threshold
        cap_txt = f"{cap:g}% {'per month' if event.threshold_unit == 'PERCENT_PER_MONTH' else 'per annum'}"
        rates = _percents(text)
        if not rates:
            if _BLANK_RE.search(text) and re.search(r"percent|%", low):
                return self._gap(
                    document, clause, event, severity="WARNING",
                    reason=(
                        f"The interest rate is a blank to be completed at origination. For {event.jurisdiction} borrowers "
                        f"the completed rate may not exceed {cap_txt} under {event.statute_citation}"
                        + (f" ({event.applicability})" if event.applicability else "") + "."
                    ),
                    threshold=cap_txt, patch=self._usury_patch(text, event), confidence=0.55,
                )
            return None
        rate = max(rates)
        if event.threshold_unit == "PERCENT_PER_MONTH":
            rate_cmp, cap_cmp = rate / 12.0, cap
        else:
            rate_cmp, cap_cmp = rate, cap
        if rate_cmp <= cap_cmp:
            return self._gap(document, clause, event, severity="COMPLIANT", reason=f"Stated rate {rate:g}% is within the {cap_txt} ceiling of {event.statute_citation}.", threshold=cap_txt, patch=text, confidence=0.9)
        return self._gap(
            document, clause, event, severity="CRITICAL",
            reason=f"Clause sets interest at {rate:g}% per annum; {event.statute_citation} caps the rate at {cap_txt} for {event.jurisdiction} borrowers" + (f" ({event.applicability})" if event.applicability else "") + ".",
            threshold=cap_txt, patch=self._usury_patch(text, event), confidence=0.97,
        )

    # FEES ---------------------------------------------------------------

    def _check_fee(self, document, clause, event) -> Optional[ComplianceGap]:
        spec = event.fee_cap
        if spec is None:
            return None
        text = clause.verbatim_text
        kind = _fee_kind(text)
        if kind is None:
            return None
        if spec.combinator == "PROHIBITED":
            if re.search(r"(?i)whether or not (?:a|the) loan is (?:made|funded)|application fee|regardless of whether", text):
                return self._gap(document, clause, event, severity="CRITICAL", reason=f"Clause charges a fee whether or not a loan is made, contrary to {event.statute_citation}.", threshold="no charge unless a loan is made", patch=self._prohibited_fee_patch(text, event), confidence=0.9)
            return None
        if kind != spec.fee_kind:
            return None
        formula = parse_fee_formula(text, kind)
        cap_txt = describe_cap(spec)
        if formula is None or formula.combinator == "UNQUANTIFIED":
            if kind in ("ORIGINATION", "ADMIN") and spec.usd_max is not None:
                return self._gap(document, clause, event, severity="WARNING", reason=f"The {kind.lower()} fee amount is not stated in the clause; for {event.jurisdiction} borrowers it may not exceed {cap_txt} under {event.statute_citation}" + (f" ({event.applicability})" if event.applicability else "") + ".", threshold=cap_txt, patch=self._fee_cap_note_patch(text, event), confidence=0.6)
            return None
        problems: List[str] = []
        worst: Optional[Tuple[float, float, float]] = None
        for size in _INSTALLMENT_SIZES:
            c_amt = formula.amount(size)
            s_amt = statute_fee_amount(spec, size)
            if c_amt is None or s_amt is None:
                continue
            if c_amt > s_amt + 1e-9 and (worst is None or c_amt - s_amt > worst[1] - worst[2]):
                worst = (size, c_amt, s_amt)
        if worst is not None:
            size, c_amt, s_amt = worst
            problems.append(f"the contract formula ({formula.describe()}) yields ${c_amt:.2f} on a ${size:.0f} installment, above the statutory maximum of ${s_amt:.2f}")
        if spec.min_grace_days is not None and formula.grace_days is not None and formula.grace_days < spec.min_grace_days:
            problems.append(f"the charge is assessed after {formula.grace_days:g} days but the statute permits it only after {spec.min_grace_days} days")
        if spec.once_per_installment and formula.repeats:
            problems.append("the charge repeats each month but only one charge per installment is permitted")
        if not problems:
            return self._gap(document, clause, event, severity="COMPLIANT", reason=f"{kind.title()} fee ({formula.describe()}) stays within {cap_txt} under {event.statute_citation}.", threshold=cap_txt, patch=text, confidence=0.85)
        return self._gap(
            document, clause, event, severity="CRITICAL",
            reason=f"Under {event.statute_citation}: " + "; ".join(problems) + (f" (applies to {event.applicability})" if event.applicability else "") + ".",
            threshold=cap_txt, patch=self._fee_patch(text, event, formula), confidence=0.96,
        )

    # DISCLOSURE ---------------------------------------------------------

    def _check_disclosure(self, document, clause, event) -> Optional[ComplianceGap]:
        text, low = clause.verbatim_text, clause.verbatim_text.lower()
        snippet_low = event.raw_source_snippet.lower()
        if "opt-out" in snippet_low or "opt out" in snippet_low:
            if not re.search(r"automatically enrolled|auto-?enrol", low):
                return None
            hrs = _hours(text)
            has_notice = "opt-out notice" in low or "written notice" in low
            window_ok = bool(hrs) and event.numerical_threshold is not None and max(hrs) >= event.numerical_threshold
            if has_notice and window_ok:
                return None
            return self._gap(document, clause, event, severity="CRITICAL", reason=f"Automatic enrollment in an optional product without the notice and opt-out window required by {event.statute_citation}.", threshold=f"{event.numerical_threshold:g}-hour opt-out window" if event.numerical_threshold else "written opt-out notice", patch=self._disclosure_patch(text, event), confidence=0.9)
        if "license number" in snippet_low or "annual percentage rate" in snippet_low:
            # CA § 22337(a): the note itself must carry or be accompanied by the statement; check the preamble / rate clause.
            if not re.search(r"promise to pay|principal sum|bears interest", low):
                return None
            has_license = "license" in low
            has_apr = "annual percentage rate" in low or "truth in lending" in low
            if has_license and has_apr:
                return self._gap(document, clause, event, severity="COMPLIANT", reason=f"Clause carries the lender identity and APR disclosure required by {event.statute_citation}.", threshold="statement at time of loan", patch=text, confidence=0.7)
            missing = [m for m, ok in (("finance lender license number", has_license), ("annual percentage rate per Regulation Z", has_apr)) if not ok]
            return self._gap(document, clause, event, severity="WARNING", reason=f"The note does not itself state the {' or '.join(missing)}; {event.statute_citation} requires a statement with these items delivered when the loan is made, so confirm it is delivered separately for {event.jurisdiction} borrowers.", threshold="statement at time of loan", patch=self._disclosure_note_patch(text, event), confidence=0.6)
        if "copy of each document" in snippet_low or "written statement" in snippet_low:
            if "receipt of a completely filled-in copy" in low or "copy of this note" in low or "copy of each document" in low:
                return self._gap(document, clause, event, severity="COMPLIANT", reason=f"Borrower acknowledges receipt of a copy of the note as {event.statute_citation} requires.", threshold="copy delivered to borrower", patch=text, confidence=0.7)
            return None
        if "credit education" in snippet_low or "consumer reporting agency" in snippet_low:
            if not re.search(r"credit bureau|credit report|consumer reporting agency", low):
                return None
            if re.search(r"report (?:information about )?(?:your|borrower's|my) (?:account|payment)|report.*to (?:one or more )?(?:credit bureaus|consumer reporting)", low):
                return self._gap(document, clause, event, severity="COMPLIANT", reason=f"Clause provides for reporting payment performance to consumer reporting agencies as {event.statute_citation} requires.", threshold="report to at least one nationwide consumer reporting agency", patch=text, confidence=0.7)
            return None
        return None

    # PREPAYMENT ---------------------------------------------------------

    def _check_prepayment(self, document, clause, event) -> Optional[ComplianceGap]:
        text, low = clause.verbatim_text, clause.verbatim_text.lower()
        if "prepay" not in low:
            return None
        penalty = re.search(r"prepayment (?:penalty|premium|fee|charge)", low) and not re.search(r"without (?:penalty|premium|prepayment penalty)|no prepayment penalty|not (?:be )?(?:charged|subject to) (?:a |any )?prepayment", low)
        if penalty:
            pcts = _percents(text)
            return self._gap(document, clause, event, severity="CRITICAL", reason=f"Clause imposes a prepayment penalty" + (f" of {pcts[0]:g}%" if pcts else "") + f", which {event.statute_citation} prohibits" + (f" for {event.applicability}" if event.applicability else "") + ".", threshold="no prepayment penalty", patch=self._prepayment_patch(text, event), confidence=0.9)
        if re.search(r"without penalty|without penalty or premium|no penalty", low):
            return self._gap(document, clause, event, severity="COMPLIANT", reason=f"Borrower may prepay without penalty, consistent with {event.statute_citation}.", threshold="no prepayment penalty", patch=text, confidence=0.9)
        return None

    # TERM ---------------------------------------------------------------

    def _check_term(self, document, clause, event) -> Optional[ComplianceGap]:
        text, low = clause.verbatim_text, clause.verbatim_text.lower()
        if not re.search(r"monthly installments|period of|term of|months", low) or event.numerical_threshold is None:
            return None
        months = [float(m.group(1)) for m in _MONTHS_RE.finditer(text)]
        installments = re.search(r"payable in (\d+) monthly installments", low)
        n = float(installments.group(1)) if installments else (months[0] if months else None)
        is_min = "less than" in event.raw_source_snippet.lower() or "minimum" in event.raw_source_snippet.lower()
        limit = f"{'at least' if is_min else 'at most'} {event.numerical_threshold:g} months"
        if n is None:
            if _BLANK_RE.search(text):
                return self._gap(document, clause, event, severity="WARNING", reason=f"The repayment term is a blank to be completed at origination; for {event.jurisdiction} borrowers it must be {limit} under {event.statute_citation}" + (f" ({event.applicability})" if event.applicability else "") + ".", threshold=limit, patch=self._term_patch(text, event, is_min), confidence=0.55)
            return None
        bad = n < event.numerical_threshold if is_min else n > event.numerical_threshold
        if bad:
            return self._gap(document, clause, event, severity="CRITICAL", reason=f"Term of {n:g} months violates the {limit} requirement of {event.statute_citation}" + (f" ({event.applicability})" if event.applicability else "") + ".", threshold=limit, patch=self._term_patch(text, event, is_min), confidence=0.9)
        return self._gap(document, clause, event, severity="COMPLIANT", reason=f"Term of {n:g} months satisfies {limit} under {event.statute_citation}.", threshold=limit, patch=text, confidence=0.85)

    # REPORTING ----------------------------------------------------------

    def _check_reporting(self, document, clause, event) -> Optional[ComplianceGap]:
        if "report" not in clause.verbatim_text.lower():
            return None
        return self._gap(document, clause, event, severity="WARNING", reason=f"Clause references reporting obligations; confirm alignment with {event.statute_citation}.", threshold=None, patch=clause.verbatim_text, confidence=0.5)

    # helpers ------------------------------------------------------------

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
            is_grounded_in_citation=event.statute_citation in patch or severity == "COMPLIANT",
            jurisdiction=event.jurisdiction,
            rule_type=event.rule_type,
            statutory_source_snippet=event.raw_source_snippet,
        )

    @staticmethod
    def _usury_patch(text: str, event: RegulatoryEvent) -> str:
        cap = event.numerical_threshold
        per = "per month" if event.threshold_unit == "PERCENT_PER_MONTH" else "per annum"
        return (
            f"{text} Notwithstanding the foregoing, for Borrowers residing in {event.jurisdiction}, the interest "
            f"rate shall not exceed {cap:g}% {per}, the maximum rate permitted under {event.statute_citation}, "
            f"and any rate stated above in excess of {cap:g}% shall be reduced to {cap:g}% for such Borrowers."
        )

    @staticmethod
    def _fee_patch(text: str, event: RegulatoryEvent, formula: FeeFormula) -> str:
        """Rewrite the offending formula in place so the corrected clause re-audits clean."""
        spec = event.fee_cap
        assert spec is not None
        patched = text
        if spec.combinator == "FLAT_PCT":
            patched = re.sub(r"(?i)the (?:greater|lesser) of \$\s?[\d,.]+ or (\d+(?:\.\d+)?\s?(?:percent|%)|[a-z ]+percent(?: \(\d+%\))?) of", r"\1 of", patched)
            patched = _PCT_RE.sub(lambda m: f"{spec.pct_max:g}%" if float(m.group(1)) > spec.pct_max else m.group(0), patched)
            patched = _USD_RE.sub("", patched) if "greater of" not in patched.lower() and "lesser of" not in patched.lower() and formula.combinator in ("GREATER_OF", "LESSER_OF", "FLAT_USD") and _USD_RE.search(patched) and spec.usd_max is None else patched
            patched = re.sub(r"(?i)a late charge of the  of", "a late charge of", patched)
        elif spec.combinator == "FLAT_USD":
            patched = re.sub(r"(?i)the (?:greater|lesser) of (\$\s?[\d,.]+) or \d+(?:\.\d+)?\s?(?:percent|%) of (?:the )?(?:late |outstanding |overdue )?(?:payment|installment)", lambda m: m.group(1), patched)
            patched = re.sub(r"(?i)the (?:greater|lesser) of \d+(?:\.\d+)?\s?(?:percent|%) of (?:the )?(?:late |outstanding |overdue )?(?:payment|installment) or (\$\s?[\d,.]+)", lambda m: m.group(1), patched)
            patched = _USD_RE.sub(lambda m: f"${spec.usd_max:.2f}" if float(m.group(1).replace(",", "")) > spec.usd_max else m.group(0), patched)
        else:
            if spec.combinator == "LESSER_OF":
                patched = re.sub(r"(?i)\bgreater of\b", "lesser of", patched)
            if spec.usd_max is not None:
                patched = _USD_RE.sub(lambda m: f"${spec.usd_max:.2f}" if float(m.group(1).replace(",", "")) > spec.usd_max else m.group(0), patched)
            if spec.pct_max is not None:
                patched = _PCT_RE.sub(lambda m: f"{spec.pct_max:g}%" if float(m.group(1)) > spec.pct_max else m.group(0), patched)
        if spec.min_grace_days is not None and formula.grace_days is not None and formula.grace_days < spec.min_grace_days:
            patched = _DAYS_RE.sub(lambda m: f"{spec.min_grace_days} days", patched, count=1)
        if spec.once_per_installment:
            patched = re.sub(r"(?i)[^.]*\b(?:each|per) month\b[^.]*\.", "", patched).strip()
            if not re.search(r"(?i)only (?:one|once)", patched):
                patched += " Only one such charge may be collected on any one installment."
        patched = re.sub(r"\s{2,}", " ", patched).strip()
        return f"{patched} This charge is limited as required by {event.statute_citation}."

    @staticmethod
    def _fee_cap_note_patch(text: str, event: RegulatoryEvent) -> str:
        spec = event.fee_cap
        cap = describe_cap(spec) if spec else "the statutory maximum"
        return f"{text} For Borrowers residing in {event.jurisdiction}, this fee shall not exceed {cap}, as required by {event.statute_citation}."

    @staticmethod
    def _prohibited_fee_patch(text: str, event: RegulatoryEvent) -> str:
        return f"{text} No interest or charge of any nature shall be charged, contracted for, or received unless a loan is made, as required by {event.statute_citation}."

    @staticmethod
    def _disclosure_patch(text: str, event: RegulatoryEvent) -> str:
        hrs = int(event.numerical_threshold or 48)
        return (
            f"Borrower may elect to enroll in the optional product described above. Where Borrower is enrolled, Lender "
            f"shall deliver a written opt-out notice separately from this Agreement and shall not assess any charge "
            f"until at least {hrs} hours after delivery of that notice, during which Borrower may opt out "
            f"without charge, as required by {event.statute_citation}."
        )

    @staticmethod
    def _disclosure_note_patch(text: str, event: RegulatoryEvent) -> str:
        return f"{text} For Borrowers residing in {event.jurisdiction}, Lender shall deliver, at the time the loan is made, a statement showing Lender's name, address, and license number and the annual percentage rate, as required by {event.statute_citation}."

    @staticmethod
    def _prepayment_patch(text: str, event: RemediationPatch) -> str:
        patched = re.sub(r"(?i)[^.]*prepayment (?:penalty|premium|fee|charge)[^.]*\.", "", text).strip()
        return f"{patched} Borrower may prepay this loan in whole or in part at any time without penalty, as required by {event.statute_citation}."

    @staticmethod
    def _term_patch(text: str, event: RegulatoryEvent, is_min: bool) -> str:
        n = event.numerical_threshold
        bound = "not less than" if is_min else "not more than"
        return f"{text} For Borrowers residing in {event.jurisdiction}, the repayment term shall be {bound} {n:g} months, as required by {event.statute_citation}."

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
        "statute. Cite the statute inline. Use ONLY numbers that appear in the statute snippet or the original clause. "
        "Do not add obligations the statute does not impose. Keep every compliant term of the original clause."
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
            | set(_word_numbers(snippet))
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


def _word_numbers(text: str) -> List[float]:
    out: List[float] = []
    for m in re.finditer(rf"\b({_WORD_NUM_RE})\b", text or "", re.IGNORECASE):
        v = _words_to_number(m.group(1))
        if v is not None:
            out.append(v)
    cents = _cents_per_dollar(text or "")
    if cents is not None:
        out.append(cents)
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
