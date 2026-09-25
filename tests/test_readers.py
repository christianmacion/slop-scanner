"""Tests for readers.py. Every document is built in memory, so there are no
fixture files to keep in sync."""
import io
import unittest
import zipfile

import readers
from slop_engine import score_text

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

try:
    import pdfplumber  # noqa: F401
    HAVE_PDFPLUMBER = True
except ImportError:
    HAVE_PDFPLUMBER = False


def pptx(*slides):
    """Each slide is (title, [paragraph, ...])."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, (title, paras) in enumerate(slides, 1):
            body = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in paras)
            z.writestr(f"ppt/slides/slide{n}.xml",
                       f'<p:sld xmlns:a="{A}" xmlns:p="{P}"><p:cSld><p:spTree>'
                       f'<p:sp><p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>'
                       f'<p:txBody><a:p><a:r><a:t>{title}</a:t></a:r></a:p></p:txBody></p:sp>'
                       f'<p:sp><p:txBody>{body}</p:txBody></p:sp>'
                       f'</p:spTree></p:cSld></p:sld>')
    buf.seek(0)
    return buf


def docx(*paras):
    """Each paragraph is (style, text); style is "", a style name, or "list"."""
    def par(style, text):
        if style == "list":
            ppr = '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
        elif style:
            ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
        else:
            ppr = ""
        return f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"
    body = "".join(par(s, t) for s, t in paras)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>')
    buf.seek(0)
    return buf


def pdf(*lines):
    """A one-page PDF with one string per line. No lines means no text layer,
    like a scanned page."""
    ops = "".join(f"({line}) Tj T* " for line in lines)
    content = f"BT /F1 12 Tf 14 TL 72 720 Td {ops}ET" if lines else "0 0 m 100 100 l S"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return io.BytesIO(out)


class Pptx(unittest.TestCase):
    def test_titles_become_headings_and_slides_stay_in_order(self):
        deck = pptx(*[(f"Slide {n}", [f"Point {n}."]) for n in range(1, 12)])
        text = readers.read_file(deck, "deck.pptx")
        self.assertTrue(text.startswith("# Slide 1\n\nPoint 1."))
        self.assertLess(text.index("# Slide 2\n"), text.index("# Slide 10\n"))

    def test_slop_in_a_deck_is_found(self):
        deck = pptx(("Quarterly review", ["We delve into the robust tapestry."]))
        r = score_text(readers.read_file(deck, "deck.pptx"))
        self.assertEqual(len(r["hits"]["Blocklist words"]), 3)


class Docx(unittest.TestCase):
    def test_headings_and_lists_are_marked(self):
        doc = docx(("Heading1", "Overview"), ("", "A paragraph."), ("list", "An item"))
        self.assertEqual(readers.read_file(doc, "notes.docx"),
                         "# Overview\n\nA paragraph.\n\n- An item")


class Guards(unittest.TestCase):
    def test_unsupported_extension(self):
        with self.assertRaises(ValueError):
            readers.read_file(io.BytesIO(b"x"), "photo.jpg")

    def test_not_a_zip(self):
        with self.assertRaises(ValueError):
            readers.read_file(io.BytesIO(b"not a zip"), "deck.pptx")

    def test_dtd_is_refused(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", '<!DOCTYPE x [<!ENTITY a "aaaa">]><w:document/>')
        buf.seek(0)
        with self.assertRaises(ValueError):
            readers.read_file(buf, "evil.docx")

    def test_text_files_pass_through(self):
        self.assertEqual(readers.read_file(io.BytesIO("café".encode()), "draft.md"), "café")


@unittest.skipUnless(HAVE_PDFPLUMBER, "pdfplumber not installed")
class Pdf(unittest.TestCase):
    def test_text_is_extracted(self):
        text = readers.read_file(pdf("We delve into it.", "Then we stop."), "a.pdf")
        self.assertIn("We delve into it.", text)
        self.assertIn("Then we stop.", text)

    def test_scanned_pdf_is_not_scored(self):
        r = score_text(readers.read_file(pdf(), "scan.pdf"))
        self.assertFalse(r["scored"])


if __name__ == "__main__":
    unittest.main()
