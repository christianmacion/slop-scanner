# Deploy — slop-scanner

**TL;DR:** a public URL in ~5 minutes on Streamlit Community Cloud (free). Works with **no API key** (the scoring core is stdlib-only), so the demo is live the instant it builds.

## 0. Prerequisites
- A GitHub account.
- A Streamlit Community Cloud account — sign in at [share.streamlit.io](https://share.streamlit.io) with GitHub (free).

## 1. Put this folder in its own public GitHub repo
Keep each demo as its **own** repo for a clean URL — these folders contain no client IP.
```bash
cd "05_live_demo/slop-scanner"
git init && git add . && git commit -m "slop-scanner: AI-slop evaluation gate"
gh repo create slop-scanner --public --source=. --push
# No gh CLI? Create an empty repo on github.com, then:
#   git remote add origin https://github.com/<you>/slop-scanner.git
#   git branch -M main && git push -u origin main
```

## 2. Deploy on Streamlit Community Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io) → **Create app** → **Deploy from GitHub**.
2. Repository: `<you>/slop-scanner` · Branch: `main` · **Main file path: `app.py`**.
3. Click **Deploy**. The first build installs `requirements.txt` (just `streamlit`, ~1 min).
4. You get a permanent URL: `https://<app-name>.streamlit.app` — put it on your resume / LinkedIn / portfolio.

No secrets needed — this app is fully offline/deterministic.

## What a reviewer sees
A box to paste any draft → a big **SLOP INDEX** with a 4-tier verdict, a 13-rule breakdown, and the exact flagged spans. Click the **"Heavy slop"** sample to watch it score ~190, then **"Clean human draft"** to watch it score single digits — the same gate that drove a real draft **81 → 3**.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Alternative host: Hugging Face Spaces
Create a new **Space** → SDK **Streamlit** → push these files (or connect the GitHub repo). HF serves it automatically.

---
*Christian Macion — AI / Agent Engineer.*
