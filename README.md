# 🛡️ AI-Slop Scanner

[![tests](https://github.com/christianmacion/slop-scanner/actions/workflows/tests.yml/badge.svg)](https://github.com/christianmacion/slop-scanner/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A live, clickable demo of an LLM-output evaluation gate. Paste a draft or upload a PDF, PowerPoint or Word file, and get a numeric SLOP INDEX, a four-tier verdict (`CLEAN` / `MINOR TELLS` / `READS AI` / `HEAVY SLOP`), a per-rule breakdown, and the exact flagged spans.

It scores prose on 13 literature-grounded metrics: em-dash density, a contrastive-negation regex for the "not X, it's Y" tic, sentence-length burstiness (coefficient of variation), monotony runs, `-ing` participle openers, blocklist words and phrases, intent framing, reader commands, assistant residue, and title colon-formulas. They are combined by density and co-occurrence, so no single tell decides the verdict.

> **Why this exists.** It's the public, IP-free slice of a quality gate from a content-production pipeline I built. In that system it drove a real draft from a SLOP INDEX of **81 ("HEAVY SLOP") to 3 ("CLEAN")** across one guardrailed rewrite. The point for a hiring reviewer: it's the same engineering idea as the evaluation harnesses I build for multi-agent systems — **define quality numerically, measure it honestly, and let the number gate the work.** An eval gate, not a vibe.
>
> — Christian Macion · AI / Agent Engineer · [linkedin.com/in/christianmacion](https://linkedin.com/in/christianmacion)

---

## Run it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the URL Streamlit prints (default http://localhost:8501).

## Deploy a public URL (free)

**Option A: Streamlit Community Cloud (recommended, zero-config).**
1. Push this folder to a public GitHub repo.
2. Go to [share.streamlit.io](https://share.streamlit.io), "New app," point it at your repo and `app.py`.
3. You get a permanent `https://<app>.streamlit.app` link to put on your resume/portfolio.

**Option B: Hugging Face Spaces.** Create a new Streamlit Space and push these files; HF serves it automatically.

Step-by-step notes are in [DEPLOY.md](DEPLOY.md).

## What's in the repo

| File | Purpose |
|---|---|
| `app.py` | The Streamlit UI. |
| `slop_engine.py` | The importable scoring core, `score_text(text) -> dict`. Stdlib-only; drop it into any pipeline or eval harness. |
| `readers.py` | Text out of PDF, PPTX and DOCX files. PPTX and DOCX use only the stdlib; PDF uses `pdfplumber`. |
| `samples.py` | One-click "heavy slop" vs "clean human draft" examples. |
| `tests/` | 39 tests, stdlib `unittest`. Run with `python -m unittest discover -s tests`. |
| `requirements.txt` | `streamlit` and `pdfplumber`. The engine itself needs nothing. |

## Use the engine directly (no UI)

```python
from slop_engine import score_text
from readers import read_file

r = score_text(read_file("draft.pdf"))      # or score_text(any_string)
if r["scored"]:
    print(r["slop_index"], r["verdict"])     # e.g. 3 CLEAN
    for row in r["rows"]:
        print(row["metric"], row["value"], row["status"])
else:
    print(r["verdict"], r["notes"])          # empty, scanned or non-Latin text
```

`slop_index` is `None` when the text can't be judged, so a gate written as `r["slop_index"] < 15` fails loudly rather than waving through text nobody read.

## How it reads a document

Word and phrase rules scan every line of natural language, including headings, lists and table cells, and count each occurrence. Sentence rules (length variance, monotony, `-ing` openers) and density rules (em-dashes, bold) only look at paragraphs of running prose. Neither sees code, HTML tags, URLs or inline code. Quoted spans are skipped by the word lists, because writing *about* "delve" is not using it.

Rates are measured over at least 150 words and 10 sentences, so one em-dash in a two-line note can't produce a verdict. A rule shown as `n/a` wasn't scored, and the notes under the verdict say why.

## Honest scope

This is a calibrated heuristic quality gate, not an AI-detection oracle. It surfaces stylistic tells for a human to judge; thresholds are deliberately conservative, and good writing should never be sanded down to game a detector. Every point in the SLOP INDEX traces to a named rule and a flagged span.

Two limits worth knowing. The rules cover English; text mostly in another script is reported as not scored. And the sentence rules assume running prose, so an agenda or form written to a template will show uniform sentence lengths because it is uniform by design. Read those flags as a description of the genre.

## License

MIT. See [LICENSE](LICENSE).

*Part of [Christian Macion's AI / Agent Engineer portfolio](../../). Built from `slop_scan.py`, originally a 290-line stdlib linter in a Medium content pipeline.*
