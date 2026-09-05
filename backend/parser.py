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

Form-style agreements (the OneMain sample loan agreements) add four more:

* an itemization table ("1. $NONE Paid To", "2. $ Paid To" ...) is not a
  numbered clause list, so the numbered strategy is rejected when fewer than
  half of its items carry a sentence;
* an all-caps form label ending in a colon at the start of a line
  ("LATE CHARGE:", "PREPAYMENT:") is a heading, and a short all-caps section
  title with no terminal punctuation ("ITEMIZATION OF AMOUNT FINANCED",
  "B. LOAN TERMS AND CONDITIONS") is one too; neither needs the previous line
  to have ended a sentence, and a title that is immediately followed by
  another heading is folded into that heading's clause;
* a numbered all-caps run-in heading inside a headings-style document
  ("1. ADDITIONAL DEFINITIONS.", "2. WHAT CLAIMS ARE COVERED?") is a heading;
* an all-caps heading may run to nine words, a mixed-case one still to six.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from schemas import ContractClause, ContractDocument

_MARKER = re.compile(r"(?:^|\n)[ \t]*(\d{1,2})\.[ \t]+")
_RUN_IN_HEADING = re.compile(r"^([A-Z][^\n.]{1,70}?)\.(?=\s)")
_HEADING_LINE = re.compile(r"(?:^|\n)((?:\d{1,2}\.[ \t]+)?[A-Z][A-Za-z0-9 ,;'&/()-]{2,70})[.?](?=[ \t])")
_LABEL_LINE = re.compile(r"(?:^|\n)([A-Z][A-Z0-9 ,;'&/()-]{2,40}?) ?:(?=[ \t])")
_TITLE_LINE = re.compile(r"^[A-Z][A-Z ,;'&/()-]*(?:\. [A-Z][A-Z ,;'&/()-]*)?$")
_NUMBER_PREFIX = re.compile(r"^\d{1,2}\.\s+")
# A mixed-case line that opens with one of these is a sentence, not a heading
# ("The FAA governs this Arbitration Agreement.").
_SENTENCE_OPENERS = {"the", "a", "an", "if", "you", "i", "we", "this", "that", "any", "in", "for", "to", "by", "no", "nor", "it", "unless", "after", "before", "my", "your", "all", "each", "such", "these", "those", "as", "at", "on", "or", "and", "see"}
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
_STATE_LEAD = re.compile(rf"^(?:{_STATE_NAMES})\b", re.IGNORECASE)  # state notices belong to _split_state_notices
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
    worded = 0
    for i, h in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(raw)
        if len(re.findall(r"[A-Za-z]{2,}", raw[h.end():end])) >= 6:
            worded += 1
    if worded < max(3, len(hits) // 2):
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


def _is_title(line: str) -> bool:
    words = line.split()
    real = [w for w in words if len(re.sub(r"[^A-Za-z]", "", w)) >= 3]
    return bool(line) and 2 <= len(words) <= 6 and len(real) >= 2 and bool(_TITLE_LINE.match(line))


def _mostly_upper(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 3 and sum(c.isupper() for c in letters) / len(letters) > 0.7


def _headings(raw: str) -> List[Tuple[str, str]]:
    # (position, heading, kind) for every candidate boundary
    found: List[Tuple[int, str, str]] = []
    for h in _HEADING_LINE.finditer(raw):
        heading = h.group(1)
        body = _NUMBER_PREFIX.sub("", heading)
        if body != heading and not body.isupper():
            continue
        if len(body.split()) > (9 if body.isupper() else 6):
            continue
        if not body.isupper() and body.split()[0].lower() in _SENTENCE_OPENERS:
            continue
        line_start = h.start() + 1 if raw[h.start()] == "\n" else h.start()
        found.append((line_start, heading, "heading"))
    for h in _LABEL_LINE.finditer(raw):
        if _STATE_LEAD.match(h.group(1)):
            continue
        line_start = h.start() + 1 if raw[h.start()] == "\n" else h.start()
        found.append((line_start, h.group(1).strip(), "label"))
    for m in re.finditer(r"(?:^|\n)([^\n]+)", raw):
        line = m.group(1).strip()
        if _is_title(line) and not _STATE_LEAD.match(line):
            found.append((m.start(1), line, "title"))
    found.sort()
    hits: List[Tuple[int, str, str]] = []
    for line_start, heading, kind in found:
        if hits and hits[-1][0] == line_start:
            continue
        prev_line = raw[:line_start].rstrip("\n").split("\n")[-1].strip() if line_start else ""
        if kind == "heading" and prev_line and not _SENTENCE_END.search(prev_line) and not _is_title(prev_line):
            # a wrapped line can start with "Lender." but not with an all-caps
            # heading, unless the wrapped text is itself all caps (a notice block)
            if not (_mostly_upper(_NUMBER_PREFIX.sub("", heading)) and not _mostly_upper(prev_line)):
                continue
        hits.append((line_start, heading, kind))
    # a title immediately followed by another heading names nothing of its own
    folded: List[Tuple[int, str, str]] = []
    for i, (start, heading, kind) in enumerate(hits):
        if kind == "title" and i + 1 < len(hits):
            nxt = hits[i + 1]
            between = raw[start + len(heading):nxt[0]]
            if not between.strip():
                hits[i + 1] = (start, nxt[1], nxt[2])
                continue
        folded.append((start, heading, kind))
    hits = folded
    if len([h for h in hits if h[2] != "title"]) < 3:
        return []
    out: List[Tuple[str, str]] = []
    for i, (start, heading, _kind) in enumerate(hits):
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
