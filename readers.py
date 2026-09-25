"""
readers.py — plain text from PDF, PPTX and DOCX files, for slop_engine to score.

PPTX and DOCX are zipped XML and need only the standard library. PDF needs
pdfplumber (`pip install pdfplumber`).

Readers return Markdown-ish text: paragraphs separated by blank lines, titles
and headings as `# `, Word list items as `- `. The engine uses that structure
to keep a slide's bullets from being read as one long sentence.

    from readers import read_file
    text = read_file("deck.pptx")            # a path...
    text = read_file(uploaded, "deck.pptx")  # ...or a file object plus its name
"""

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

SUPPORTED = ("pdf", "pptx", "docx", "md", "txt")

_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# The app is public. Office parts never contain a DTD, so refusing one rules
# out entity-expansion attacks, and the size cap rules out zip bombs.
_MAX_PART_BYTES = 25 * 1024 * 1024


def _xml(z, name):
    info = z.getinfo(name)
    if info.file_size > _MAX_PART_BYTES:
        raise ValueError(f"{name} is too large to read ({info.file_size // 2**20} MB).")
    data = z.read(name)
    if b"<!DOCTYPE" in data[:4096].upper():
        raise ValueError("File contains a DTD, which Office files never do. Not reading it.")
    return ET.fromstring(data)


def _open_zip(src):
    try:
        return zipfile.ZipFile(src)
    except zipfile.BadZipFile:
        raise ValueError("Not a valid PPTX/DOCX file (it isn't a zip archive).") from None


def _runs(par, ns):
    """Text of one paragraph, keeping tabs and soft line breaks as spaces."""
    out = []
    for el in par.iter():
        if el.tag == ns + "t" and el.text:
            out.append(el.text)
        elif el.tag in (ns + "tab", ns + "br"):
            out.append(" ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


def read_pptx(src):
    """Slide text in slide order. Titles become headings; each paragraph
    (bullet, text box line, table cell) is its own block."""
    with _open_zip(src) as z:
        slides = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.search(r"\d+", n).group()))
        blocks = []
        for name in slides:
            for shape in _xml(z, name).iter(_P + "sp"):
                ph = shape.find(f".//{_P}ph")
                is_title = ph is not None and ph.get("type") in ("title", "ctrTitle")
                for par in shape.iter(_A + "p"):
                    text = _runs(par, _A)
                    if text:
                        blocks.append(("# " if is_title else "") + text)
            for frame in _xml(z, name).iter(_P + "graphicFrame"):   # tables
                for par in frame.iter(_A + "p"):
                    text = _runs(par, _A)
                    if text:
                        blocks.append(text)
    return "\n\n".join(blocks)


def read_docx(src):
    """Body paragraphs in order. Heading/Title styles become headings and
    numbered or bulleted paragraphs become list items."""
    with _open_zip(src) as z:
        body = _xml(z, "word/document.xml")
    blocks = []
    for par in body.iter(_W + "p"):
        text = _runs(par, _W)
        if not text:
            continue
        style = par.find(f"{_W}pPr/{_W}pStyle")
        style = style.get(_W + "val", "") if style is not None else ""
        if style.lower().startswith(("heading", "title")):
            text = "# " + text
        elif par.find(f"{_W}pPr/{_W}numPr") is not None:
            text = "- " + text
        blocks.append(text)
    return "\n\n".join(blocks)


def read_pdf(src):
    """Text of each page, split into paragraphs where the vertical gap between
    lines is larger than normal line spacing. Scanned PDFs have no text layer
    and come back empty."""
    try:
        import pdfplumber
    except ImportError:
        raise ValueError("Reading PDFs needs pdfplumber: pip install pdfplumber") from None
    pages = []
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            lines = page.extract_text_lines()
            if not lines:
                continue
            heights = sorted(l["bottom"] - l["top"] for l in lines)
            gap_limit = 0.6 * heights[len(heights) // 2]
            paras, current = [], [lines[0]["text"]]
            for prev, line in zip(lines, lines[1:]):
                if line["top"] - prev["bottom"] > gap_limit:
                    paras.append(" ".join(current))
                    current = []
                current.append(line["text"])
            paras.append(" ".join(current))
            pages.append("\n\n".join(p.strip() for p in paras if p.strip()))
    return "\n\n".join(pages)


def read_file(src, name=None):
    """Read a path, or a file object whose filename is given as `name`."""
    name = str(name or src)
    ext = Path(name).suffix.lower().lstrip(".")
    if ext not in SUPPORTED:
        raise ValueError(f"Can't read .{ext or '?'} files. Supported: "
                         + ", ".join("." + e for e in SUPPORTED))
    if ext in ("md", "txt"):
        data = src.read() if hasattr(src, "read") else Path(src).read_bytes()
        return data.decode("utf-8", errors="replace")
    return {"pdf": read_pdf, "pptx": read_pptx, "docx": read_docx}[ext](src)
