# 🛡️ AI-Slop Scanner

**A live, clickable demo of an LLM-output evaluation gate.** Paste a draft → get a numeric **SLOP INDEX**, a 4-tier verdict (`CLEAN` / `MINOR TELLS` / `READS AI` / `HEAVY SLOP`), a per-rule breakdown, and the exact flagged spans.

It scores prose on **13 literature-grounded metrics** — em-dash density, a contrastive-negation regex for the "not X, it's Y" tic, sentence-length burstiness (coefficient of variation), monotony runs, `-ing`-participle openers, blocklist words/phrases, intent-framing, reader-commands, assistant residue, and title colon-formulas — combined by **density and co-occurrence**, not any single tell.

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

**Option A — Streamlit Community Cloud (recommended, zero-config):**
1. Push this folder to a public GitHub repo.
2. Go to [share.streamlit.io](https://share.streamlit.io), "New app," point it at your repo and `app.py`.
3. You get a permanent `https://<app>.streamlit.app` link to put on your resume/portfolio.

**Option B — Hugging Face Spaces:** create a new **Streamlit** Space, push these files; HF serves it automatically.

## What's in the repo

| File | Purpose |
|---|---|
| `app.py` | The Streamlit UI. |
| `slop_engine.py` | The **importable** scoring core — `score_text(text) -> dict`. Stdlib-only; no dependencies. Drop it into any pipeline or eval harness. |
| `samples.py` | One-click "heavy slop" vs "clean human draft" examples. |
| `requirements.txt` | Just `streamlit` (the engine itself needs nothing). |
| `.streamlit/config.toml` | Theme. |

## Use the engine directly (no UI)

```python
from slop_engine import score_text

r = score_text(open("draft.md").read())
print(r["slop_index"], r["verdict"])     # e.g. 3 CLEAN
for row in r["rows"]:
    print(row["metric"], row["value"], row["status"])
```

## Honest scope

This is a **calibrated heuristic quality gate, not an AI-detection oracle.** It surfaces stylistic tells for a human to judge; thresholds are deliberately conservative, and good writing should never be sanded down to game a detector. It is intentionally explainable — every point in the SLOP INDEX traces to a named rule and a flagged span.

*Part of [Christian Macion's AI / Agent Engineer portfolio](../../). Built from `slop_scan.py`, originally a 290-line stdlib linter in a Medium content pipeline.*
