# Deploy — slop-scanner

TL;DR: a public URL in about five minutes on Streamlit Community Cloud, free. There is no API key to set up (the scoring core is stdlib-only), so the demo is live as soon as it builds.

## 0. Prerequisites
- A GitHub account.
- A Streamlit Community Cloud account — sign in at [share.streamlit.io](https://share.streamlit.io) with GitHub (free).

## 1. Put this folder in its own public GitHub repo
Keep each demo in its own repo for a clean URL. These folders contain no client IP.
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
3. Click **Deploy**. The first build installs `requirements.txt` (`streamlit` and `pdfplumber`, about a minute).
4. You get a permanent URL: `https://<app-name>.streamlit.app`. Put it on your resume, LinkedIn and portfolio.
5. On the GitHub repo page, click the gear next to **About** and paste the URL into **Website**, so the demo link sits at the top of the repo.

No secrets needed. The app is offline and deterministic.

## What a reviewer sees
A box to paste any draft or upload a PDF, PowerPoint or Word file. They get a SLOP INDEX with a four-tier verdict, a 13-rule breakdown and the exact flagged spans. The "Heavy slop" sample scores about 200 and the "Clean human draft" scores in single digits. It is the same gate that took a real draft from 81 to 3.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Alternative host: Hugging Face Spaces
Create a new **Space** → SDK **Streamlit** → push these files (or connect the GitHub repo). HF serves it automatically.

---
*Christian Macion — AI / Agent Engineer.*
