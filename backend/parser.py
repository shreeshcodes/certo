"""Clause parser for real loan agreements.

Real promissory notes come in two common shapes:

* numbered paragraphs   ``4. Late Charge. If the full amount ...``
* run-in bold headings  ``Late fee. If any part of a payment ...`` on its own line

The parser tries the numbered strategy first, then the heading strategy, then
falls back to paragraphs. Clause text is the verbatim source text with
whitespace collapsed; words are never altered.

Real-document quirks handled deliberately:

* numbered markers must run in sequence (1, 2, 3 ...) so a sub-list such as
  "1. Do not sign this paper" inside an Iowa notice is not a new clause;
* a numbered paragraph without a run-in heading ("22. By signing this Note")
  still becomes a clause, named by its first words;
* a run-in heading is only accepted when the previous line ended a sentence,
  so a wrapped line that happens to start with "Lender." is body text;
* a "State Notices" block is split into one clause per state, matching both
  "New Jersey Residents" and "NEW JERSEY RESIDENTS:" forms without breaking
  two-word state names.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from schemas import ContractClause, ContractDocument

_MARKER = re.compile(r"(?:^|\n)[ \t]*(\d{1,2})\.[ \t]+")
_RUN_IN_HEADING = re.compile(r"^([A-Z][^\n.]{1,70}?)\.(?=\s)")
_HEADING_LINE = re.compile(r"(?:^|\n)([A-Z][A-Za-z0-9 ,;'&/()-]{2,70})\.(?=[ \t])")
_STATE_NAMES = (
    "Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|"
    "Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|"
    "Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|"
    "Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|"
    "Washington|West Virginia|Wisconsin|Wyoming|District of Columbia"
)
_STATE = re.compile(
    rf"(?:{_STATE_NAMES})(?:,? and (?:{_STATE_NAMES}))? Residents:?",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"[.:;!?\"”')\]]\s*$")


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _numbered(raw: str) -> List[Tuple[str, str]]:
    hits = []
    expected = 1
    for m in _MARKER.finditer(raw):
        if int(m.group(1)) != expected:
            continue
        hits.append(m)
        expected += 1
    if len(hits) < 3:
        return []
    out: List[Tuple[str, str]] = []
    for i, h in enumerate(hits):
        start = h.start() if h.start() == 0 else h.start() + 1
        end = hits[i + 1].start() if i + 1 < len(hits) else len(raw)
        body = raw[h.end():end]
        first_line = body.split("\n", 1)[0]
        run_in = _RUN_IN_HEADING.match(body)
        if run_in:
            heading = run_in.group(1)
        elif 0 < len(first_line.strip()) <= 60 and "." not in first_line:
            heading = first_line.strip()
        else:
            heading = " ".join(_collapse(body).split()[:6]) + " …"
        out.append((f"{h.group(1)}. {_collapse(heading)}", _collapse(raw[start:end])))
    preamble = _collapse(raw[: hits[0].start()])
    if preamble:
        out.insert(0, ("Preamble", preamble))
    return out


def _headings(raw: str) -> List[Tuple[str, str]]:
    lines_before: List[int] = [0] + [m.end() for m in re.finditer(r"\n", raw)]
    hits = []
    for h in _HEADING_LINE.finditer(raw):
        if len(h.group(1).split()) > 6:
            continue
        line_start = h.start() + 1 if raw[h.start()] == "\n" else h.start()
        prev_line = raw[: line_start].rstrip("\n").split("\n")[-1] if line_start else ""
        if prev_line and not _SENTENCE_END.search(prev_line):
            continue
        hits.append((line_start, h.group(1)))
    if len(hits) < 3:
        return []
    out: List[Tuple[str, str]] = []
    for i, (start, heading) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(raw)
        out.append((_collapse(heading), _collapse(raw[start:end])))
    preamble = _collapse(raw[: hits[0][0]])
    if preamble:
        out.insert(0, ("Preamble", preamble))
    return out


def _paragraphs(raw: str) -> List[Tuple[str, str]]:
    paras = [p for p in re.split(r"\n\s*\n", raw) if _collapse(p)]
    return [(f"Paragraph {i + 1}", _collapse(p)) for i, p in enumerate(paras)]


def _split_state_notices(sections: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for heading, text in sections:
        marks = [m for m in _STATE.finditer(text) if m.start() == 0 or text[m.start() - 1] == " "]
        if len(marks) < 2:
            out.append((heading, text))
            continue
        lead = _collapse(text[: marks[0].start()])
        if lead:
            out.append((heading, lead))
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            label = m.group(0).rstrip(":").title()
            out.append((f"{heading} · {label}", _collapse(text[m.start():end])))
    return out


def parse_contract_text(
    document_id: str,
    title: str,
    raw_text: str,
    jurisdiction: str = "MULTI",
    source_url: Optional[str] = None,
    source_type: Optional[str] = None,
) -> ContractDocument:
    raw = raw_text.replace("\r\n", "\n")
    sections = _numbered(raw) or _headings(raw) or _paragraphs(raw)
    sections = _split_state_notices(sections)
    clauses = [
        ContractClause(clause_id=f"cl-{i + 1}", section_name=h, verbatim_text=t)
        for i, (h, t) in enumerate(sections)
        if t
    ]
    return ContractDocument(
        document_id=document_id,
        title=title,
        jurisdiction=jurisdiction,
        clauses=clauses,
        source_url=source_url,
        source_type=source_type,
        retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
