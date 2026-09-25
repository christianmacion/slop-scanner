"""
AI-Slop Scanner — a live demo of an LLM-output evaluation gate.

Paste a draft → get a single SLOP INDEX, a 4-tier verdict, a per-rule breakdown,
and the exact flagged spans. Built by Christian Macion as the public, IP-free
slice of a content-production pipeline's quality gate (it drove a real draft from
81 → 3). The same idea — define quality numerically, measure honestly, let the
number gate the work — is how I build eval harnesses for agent systems.

Deploy free on Streamlit Community Cloud (point it at this repo's app.py) or run
locally with `streamlit run app.py`.
"""

import streamlit as st

from slop_engine import score_text
from samples import SAMPLES

st.set_page_config(page_title="AI-Slop Scanner", page_icon="🛡️", layout="wide")

TIER_COLOR = {
    "clean": "#1a7f4b",
    "minor": "#b8860b",
    "reads_ai": "#d2691e",
    "heavy": "#b22222",
    "unscored": "#6b7280",
}
STATUS_BADGE = {"ok": "🟢 ok", "warn": "🟡 warn", "FLAG": "🔴 FLAG", "n/a": "⚪ n/a"}

# ----------------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------------
st.title("🛡️ AI-Slop Scanner")
st.markdown(
    "An **LLM-output evaluation gate**: paste a draft and get a numeric **SLOP INDEX**, "
    "a 4-tier verdict, a per-rule breakdown, and the exact flagged spans. "
    "13 literature-grounded metrics, **zero dependencies in the scoring core**. "
    "*No single metric proves AI authorship — density and co-occurrence do. Flags mean "
    "“go look,” not “delete on sight.” The human reader is the judge.*"
)

with st.expander("What is this, and why does it matter?"):
    st.markdown(
        "This is the public, IP-free slice of a quality gate from a content-production "
        "pipeline I built. In that system it drove a real draft from a SLOP INDEX of "
        "**81 (“HEAVY SLOP”) to 3 (“CLEAN”)** across one guardrailed rewrite.\n\n"
        "The reason it's in my portfolio: it's the same engineering idea as the "
        "evaluation harnesses I build for multi-agent systems — **define quality "
        "numerically, measure it honestly, and let the number gate the work.** "
        "An eval gate, not a vibe.\n\n"
        "— Christian Macion · AI / Agent Engineer"
    )

# ----------------------------------------------------------------------------
# Input
# ----------------------------------------------------------------------------
left, right = st.columns([3, 2])

with left:
    choice = st.selectbox("Load a sample, or paste your own:", list(SAMPLES.keys()))
    default_text = SAMPLES[choice]
    text = st.text_area(
        "Draft (Markdown or plain text)",
        value=default_text,
        height=320,
        placeholder="Paste a blog draft, article, or any prose here…",
        key=choice,  # reset the box when a sample is picked
    )
    scan = st.button("Scan draft →", type="primary", use_container_width=True)

if not (scan or text.strip()):
    st.info("Load a sample on the left (try **Heavy slop** vs **Clean human draft**) or paste your own, then **Scan**.")
    st.stop()

if not text.strip():
    st.warning("Nothing to scan — paste some text first.")
    st.stop()

result = score_text(text)

# ----------------------------------------------------------------------------
# Verdict
# ----------------------------------------------------------------------------
with right:
    color = TIER_COLOR[result["tier"]]
    index = result["slop_index"] if result["scored"] else "—"
    st.markdown(
        f"""
        <div style="border:1px solid #d9d9d9;border-radius:10px;padding:18px 20px;
                    border-left:8px solid {color};background:#fafafa;">
          <div style="font-size:13px;color:#666;letter-spacing:.5px;">SLOP INDEX (lower is better)</div>
          <div style="font-size:54px;font-weight:700;line-height:1.05;color:{color};">{index}</div>
          <div style="font-size:20px;font-weight:600;color:{color};">{result['verdict']}</div>
          <div style="font-size:12px;color:#888;margin-top:6px;">
            {result['n_words']} words · {result['n_sentences']} sentences
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Tiers: <15 CLEAN · 15–39 MINOR TELLS · 40–79 READS AI · 80+ HEAVY SLOP")
    for note in result["notes"]:
        st.caption(f"ⓘ {note}")

# ----------------------------------------------------------------------------
# Per-rule breakdown
# ----------------------------------------------------------------------------
st.subheader("Per-rule breakdown")
table = [
    {"Metric": r["metric"], "Value": r["value"],
     "Status": STATUS_BADGE[r["status"]], "What it catches": r["note"]}
    for r in result["rows"]
]
st.dataframe(table, use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------------
# Flagged spans
# ----------------------------------------------------------------------------
if result["hits"]:
    st.subheader("Flagged spans")
    for title, hits in result["hits"].items():
        with st.expander(f"{title} — {len(hits)} hit(s)", expanded=False):
            for ln, what, txt in hits[:40]:
                st.markdown(f"**L{ln}** · `{what}` — {txt}")
            if len(hits) > 40:
                st.caption(f"… +{len(hits) - 40} more")
elif result["scored"]:
    st.success("No flagged spans — the prose reads clean against all 13 rules.")

st.divider()
st.caption(
    "Built by **Christian Macion** — AI / Agent Engineer · "
    "[linkedin.com/in/christianmacion](https://linkedin.com/in/christianmacion). "
    "Scoring core is stdlib-only and importable (`slop_engine.score_text`). "
    "Heuristic by design — a calibrated quality gate, not an AI-detection oracle."
)
