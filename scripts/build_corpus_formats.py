"""Generate the non-Markdown renditions of selected corpus documents.

The policy corpus is authored in Markdown. A few documents are shipped in other
formats so the ingestion pipeline exercises multi-format parsing (Markdown, HTML,
PDF, and plain text):

    06-data-security-and-acceptable-use            -> PDF
    09-benefits-guide                              -> PDF
    12-workplace-conduct-and-grievance-procedure   -> HTML
    17-information-classification-standard         -> authored directly as .txt

Run from the repo root:  python scripts/build_corpus_formats.py

This rewrites the target files deterministically from the Markdown sources and
removes the source .md for the converted documents so each document has exactly
one canonical file in ``corpus/``.
"""

from __future__ import annotations

import html
import re
import textwrap
import zlib
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[1] / "corpus"

TO_PDF = [
    "06-data-security-and-acceptable-use",
    "09-benefits-guide",
]
TO_HTML = [
    "12-workplace-conduct-and-grievance-procedure",
]


def parse_markdown(md: str) -> tuple[str, list[tuple[str, int]]]:
    """Return (title, blocks) where each block is (text, kind).

    kind: 0 = h1, 1 = h2, 2 = paragraph, 3 = list item, 4 = table row.
    """
    title = ""
    blocks: list[tuple[str, int]] = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("# "):
            title = line[2:].strip()
            blocks.append((title, 0))
        elif line.startswith("## "):
            blocks.append((line[3:].strip(), 1))
        elif line.startswith(("- ", "* ")):
            blocks.append((line[2:].strip(), 3))
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            blocks.append((" | ".join(cells), 4))
        else:
            blocks.append((line.strip(), 2))
    return title, blocks


def strip_inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    return text


# --------------------------------------------------------------------------- HTML


def to_html(title: str, blocks: list[tuple[str, int]]) -> str:
    out = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{html.escape(title)}</title>",
        "</head>",
        "<body>",
    ]
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for text, kind in blocks:
        text = strip_inline(text)
        if kind == 3:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"  <li>{html.escape(text)}</li>")
            continue
        close_list()
        if kind == 0:
            out.append(f"<h1>{html.escape(text)}</h1>")
        elif kind == 1:
            out.append(f"<h2>{html.escape(text)}</h2>")
        elif kind == 4:
            out.append(f"<p>{html.escape(text)}</p>")
        else:
            out.append(f"<p>{html.escape(text)}</p>")
    close_list()
    out += ["</body>", "</html>", ""]
    return "\n".join(out)


# ---------------------------------------------------------------------------- PDF


def _pdf_escape(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def to_pdf(title: str, blocks: list[tuple[str, int]]) -> bytes:
    """Minimal, dependency-free PDF writer for left-aligned text."""
    lines: list[str] = []
    for text, kind in blocks:
        text = strip_inline(text)
        prefix = {0: "", 1: "", 3: "  - ", 4: "  "}.get(kind, "")
        width = 95 if kind in (2, 4) else 100
        wrapped = textwrap.wrap(text, width=width) or [""]
        if kind in (0, 1):
            lines.append("")
        for i, chunk in enumerate(wrapped):
            lines.append((prefix if i == 0 else "    ") + chunk)
        if kind == 0:
            lines.append("=" * min(len(text), 100))
        lines.append("")

    per_page = 54
    pages = [lines[i : i + per_page] for i in range(0, len(lines), per_page)] or [[""]]

    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    # Layout: one content stream + one page object per page, then the Pages
    # object, then the Catalog. The Pages object id is known in advance because
    # object numbering is sequential.
    content_ids: list[int] = []
    page_ids: list[int] = []
    for page_lines in pages:
        stream_lines = ["BT", "/F1 9 Tf", "54 760 Td", "11 TL"]
        for ln in page_lines:
            stream_lines.append(f"({_pdf_escape(ln)}) Tj")
            stream_lines.append("T*")
        stream_lines.append("ET")
        raw = "\n".join(stream_lines).encode("latin-1", "replace")
        comp = zlib.compress(raw)
        obj = b"<< /Length %d /Filter /FlateDecode >>\nstream\n%s\nendstream" % (
            len(comp),
            comp,
        )
        content_ids.append(add(obj))

    pages_obj_index = len(objects) + len(pages) + 1  # after we add the page objs

    for cid in content_ids:
        page_obj = (
            b"<< /Type /Page /Parent %d 0 R "
            b"/MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 %d 0 R >> >> "
            b"/Contents %d 0 R >>" % (pages_obj_index, font_id, cid)
        )
        page_ids.append(add(page_obj))

    kids_str = " ".join(f"{pid} 0 R" for pid in page_ids).encode()
    pages_id = add(
        b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids_str, len(page_ids))
    )
    assert pages_id == pages_obj_index, (pages_id, pages_obj_index)

    catalog_id = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    # Assemble file with xref.
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (len(objects) + 1)
    for i, obj in enumerate(objects, start=1):
        offsets[i] = len(out)
        out += b"%d 0 obj\n" % i
        out += obj
        out += b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for i in range(1, len(objects) + 1):
        out += b"%010d 00000 n \n" % offsets[i]
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\n" % (len(objects) + 1, catalog_id)
    out += b"startxref\n%d\n%%%%EOF\n" % xref_pos
    return bytes(out)


# --------------------------------------------------------------------------- main


def _convert(stem: str, ext: str) -> None:
    src = CORPUS / f"{stem}.md"
    target = CORPUS / f"{stem}.{ext}"
    if not src.exists():
        status = "already converted" if target.exists() else "MISSING SOURCE"
        print(f"skip {stem}: {status}")
        return
    title, blocks = parse_markdown(src.read_text(encoding="utf-8"))
    if ext == "html":
        target.write_text(to_html(title, blocks), encoding="utf-8")
    else:
        target.write_bytes(to_pdf(title, blocks))
    src.unlink()
    print(f"wrote {stem}.{ext} and removed {stem}.md")


def main() -> None:
    for stem in TO_HTML:
        _convert(stem, "html")
    for stem in TO_PDF:
        _convert(stem, "pdf")


if __name__ == "__main__":
    main()
