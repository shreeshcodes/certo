#!/usr/bin/env python3
"""Extract the text layer of a lender's PDF loan agreement, verbatim, for backend/data/.

    python scripts/extract_pdf_text.py SOURCE.pdf OUT.txt

Requires poppler's ``pdftotext`` on PATH and ``pip install pymupdf``.

What it does, and nothing else:

1. ``pdftotext -layout`` page by page. Layout mode keeps the row order of the
   Truth in Lending box; the default reading-order mode scrambles it.
2. Drops the glyph runs of the ``AllAndNone`` barcode font (located with PyMuPDF
   and matched by their alphanumeric fingerprint) and Lucida Grande bar runs
   (``I lll lll ...``). They are barcodes, not text.
3. Drops recurring page furniture, matched exactly: the ``SEE ADDITIONAL PAGES``
   banner, ``Initials ____`` lines, ``(Initials required for physical form)``,
   the ``(MM-DD-YY) C.E. Agreement Page N FORMCODE`` footer, the ``Account Number
   ____ / TBD`` page header, ``UXAAE1`` print codes, and ``NNNNNNNN-TEST-...``
   sample stamps.
4. Collapses runs of spaces, strips line edges, and squeezes blank lines.
5. A page whose text layer is empty after steps 2 and 3 is replaced by a
   bracketed marker naming the page (the source page is a scanned image). A page
   with only a few stray fill-in values gets the marker plus those values.

No words are changed, reordered, or added, other than the bracketed markers.
The script prints the sha256 of the output and every removed string so they can
be recorded in ``backend/data/sources.json``.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pymupdf

FURNITURE = [
    re.compile(r"^SEE ADDITIONAL PAGES FOR IMPORTANT INFORMATION(?: Initials(?: _+)+)?$"),
    re.compile(r"^Initials(?: _+)+$"),
    re.compile(r"^_+$"),
    re.compile(r"^\(Initials required for physical form\)$"),
    re.compile(r"^\(\d\d-\d\d-\d\d\) C\.E\. Agreement(?: Page \d+)?(?: [A-Z]{2}STLA\d{4})?(?: \(Initials required for physical form\))?$"),
    re.compile(r"^Page \d+(?: [A-Z]{2}STLA\d{4})?$"),
    re.compile(r"^[A-Z]{2}STLA\d{4}$"),
    re.compile(r"^\d{8}-?TEST-?C61K4E0-?\d{4}$"),
    re.compile(r"^Account Number _+$"),
    re.compile(r"^UXAAE1$"),
]
# tokens that can share a line with barcode bars in the page-1 footer
FOOTER_TOKENS = re.compile(r"UXAAE1|\(\d\d-\d\d-\d\d\)|C\.E\. Agreement|SEE ADDITIONAL PAGES FOR IMPORTANT INFORMATION|Page \d+|[A-Z]{2}STLA\d{4}")
BARS = re.compile(r"^[Il1 ]+$")


def barcode_keys(page: pymupdf.Page) -> list[str]:
    keys = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["font"] == "AllAndNone":
                    keys.append(re.sub(r"[^A-Za-z0-9]", "", span["text"]))
    return [k for k in keys if k]


def strip_barcodes(line: str, keys: list[str], removed: list[str]) -> str:
    for key in keys:
        pattern = r"[^A-Za-z0-9 .,;:]*" + r"[^A-Za-z0-9]*".join(re.escape(ch) for ch in key) + r"[^A-Za-z0-9 .,;:]*"
        m = re.search(pattern, line)
        if m and len(m.group(0)) <= 2 * len(key) + 8:
            removed.append(m.group(0))
            line = (line[: m.start()] + line[m.end():]).strip()
    return line


def extract(pdf: Path) -> tuple[str, list[str]]:
    doc = pymupdf.open(pdf)
    removed: list[str] = []
    pages_out: list[str] = []
    for pno in range(1, len(doc) + 1):
        raw = subprocess.run(["pdftotext", "-layout", "-f", str(pno), "-l", str(pno), str(pdf), "-"], check=True, capture_output=True, text=True).stdout
        keys = barcode_keys(doc[pno - 1])
        lines: list[str] = []
        after_account_header = False
        for line in raw.split("\n"):
            line = re.sub(r"[ \t]+", " ", line).strip()
            line = strip_barcodes(line, keys, removed)
            if line and not re.search(r"[A-Za-z0-9]", line):  # punctuation left behind by a barcode run
                removed.append(line)
                continue
            probe = FOOTER_TOKENS.sub(" ", line).strip()
            if probe and BARS.match(probe):
                removed.append(line)
                continue
            if any(p.match(line) for p in FURNITURE):
                removed.append(line)
                after_account_header = line.startswith("Account Number")
                continue
            if line == "TBD" and after_account_header:  # the header's bare account-number placeholder
                removed.append(line)
                continue
            if line:
                after_account_header = False
            lines.append(line)
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip("\n")
        words = re.findall(r"\S+", text)
        if not words:
            text = f"[Page {pno} of the source PDF is a scanned image with no text layer.]"
        elif len(words) < 20:
            text = f"[Page {pno} of the source PDF is a scanned image; only these overlaid fill-in values carry a text layer:]\n{text}"
        pages_out.append(text)
    return "\n\n".join(pages_out) + "\n", removed


def main() -> None:
    pdf, out = Path(sys.argv[1]), Path(sys.argv[2])
    text, removed = extract(pdf)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(text.split())} words, {text.count(chr(10))} lines)")
    print("sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())
    print("removed strings:")
    for r in removed:
        print("  ", repr(r))


if __name__ == "__main__":
    main()
