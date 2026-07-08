"""
slop_engine.py — importable scoring core for the AI-Slop Scanner.

Refactored from `slop_scan.py` (a 290-line stdlib AI-slop linter built for the
Medium content pipeline) so it takes a STRING and returns STRUCTURED results
(no printing, no file I/O) — the shape a web UI or an eval harness can consume.

No single metric proves AI authorship; what matters is DENSITY and CO-OCCURRENCE.
Treat flags as "go look," not "delete on sight." The human reader is the judge.

Public API:
    score_text(text: str) -> dict   # metrics, per-rule rows, SLOP INDEX, verdict, flagged spans
"""

import re
import statistics

# ---------------------------------------------------------------------------
# Word / phrase lists (from the AI-tells guardrail checklist)
# ---------------------------------------------------------------------------
BLOCKLIST = [
    "delve", "navigate", "leverage", "underscore", "showcase", "foster",
    "harness", "unlock", "elevate", "embark", "unleash", "spearhead",
    "illuminate", "resonate", "streamline",
    "robust", "comprehensive", "nuanced", "pivotal", "holistic", "seamless",
    "transformative", "intricate", "multifaceted", "ever-evolving",
    "cutting-edge", "game-changing", "unparalleled",
    "tapestry", "testament", "realm", "landscape", "ecosystem", "paradigm",
    "synergy", "confluence", "trajectory",
]

BLOCK_PHRASES = [
    "in today's fast-paced world", "in an ever-changing landscape",
    "it's worth noting", "it's important to note", "that being said",
    "needless to say", "at the end of the day", "moreover", "furthermore",
    "in conclusion", "in summary", "to sum up", "a deep dive into",
    "shed light on", "stands as a testament", "let's dive in", "buckle up",
    "what does this mean for you", "in a world where", "the short answer is",
]

INTENT_FRAMING = [
    "this article aims", "this article will explore", "this article will",
    "this post will", "this piece will", "aims to explore", "in this article",
    "we'll explore", "this guide will", "by the end of this article",
]

FINANCE_VAGUE = [
    "experts say", "experts believe", "analysts say", "analysts believe",
    "studies show", "research shows", "many believe", "it is widely believed",
    "the markets reacted", "markets reacted", "stocks reacted",
    "the market shrugged", "investors digested", "the market responded",
    "some argue", "others believe", "it could go either way",
]

READER_CMDS = [
    "stay with me", "sit with that", "sit with this", "read that twice",
    "read that slowly", "follow the logic", "stop and look", "hold onto",
    "let that sink", "notice what your body", "picture two", "run it forward",
]

ASSISTANT_RESIDUE = [
    "certainly!", "i hope this helps", "great question", "would you like me to",
    "here's a breakdown", "as an ai", "as a language model",
]

CONTRASTIVE = [
    (r"\bnot\b[^.?!\n]{0,40}?,?\s*not\b[^.?!\n]{0,40}?,?\s*but\b", "False Reframe: not X, not Y, but Z"),
    (r"\bnot just\b[^.?!\n]{0,60}?\bbut\b", "not just X but Y"),
    (r"\b(isn't|aren't|wasn't|weren't)\b[^.?!\n]{0,55}?\bit'?s\b", "isn't X ... it's Y"),
    (r"\bit'?s not\b[^.?!\n]{0,55}?[.,]\s*it'?s\b", "it's not X. it's Y"),
    (r"\bnever\b[^.?!\n]{0,45}?\bit'?s\b", "never X ... it's Y"),
    (r"\bnot a\b[^.?!\n]{0,30}?[.,]\s*it'?s a\b", "not a X. it's a Y"),
    (r"\bless\b[^.?!\n]{0,25}?\bmore\b", "less X, more Y"),
]

ING_STOP = {
    "nothing", "something", "anything", "everything", "morning", "evening",
    "during", "spring", "string", "thing", "king", "ring", "wing", "ceiling",
    "willing", "ongoing",
}


def _norm(text):
    return (text.replace("’", "'").replace("‘", "'")
                .replace("“", '"').replace("”", '"'))


def strip_frontmatter(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def is_prose_line(line):
    s = line.strip()
    if not s:
        return False
    if s.startswith(("#", ">", "|", "---", "***", "- ", "* ", "1.", "!")):
        return False
    if s.lower().startswith(("sources:", "*sources", "_sources", "(sources")):
        return False
    if re.match(r"^\[[^\]]+\]\(", s):
        return False
    return True


def clean_inline(s):
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"[*_`]", "", s)
    return s


def split_sentences(prose):
    parts = re.split(r"(?<=[.!?])\s+", prose)
    out = []
    for p in parts:
        words = re.findall(r"[A-Za-z0-9']+", p)
        if len(words) >= 2:
            out.append(words)
    return out


def analyze_text(raw):
    """Compute the raw metric dict from a text string."""
    raw = raw or ""
    body = strip_frontmatter(_norm(raw))
    body = re.sub(r"```.*?```", "", body, flags=re.S)

    lines = body.splitlines()
    prose_lines = [clean_inline(l) for l in lines if is_prose_line(l)]
    prose = " ".join(prose_lines)

    words = re.findall(r"[A-Za-z0-9']+", prose)
    n_words = len(words)
    per1k = (lambda c: round(c * 1000 / n_words, 1) if n_words else 0)

    emdash = sum(l.count("—") for l in lines if is_prose_line(l))
    bold = body.count("**") // 2

    sents = split_sentences(prose)
    lens = [len(w) for w in sents]
    if len(lens) >= 2:
        mean = statistics.mean(lens)
        sd = statistics.pstdev(lens)
        cv = round(sd / mean, 2) if mean else 0
    else:
        mean = sd = cv = 0
    longest_run = run = 1
    for i in range(1, len(lens)):
        if abs(lens[i] - lens[i - 1]) <= 3:
            run += 1
            longest_run = max(longest_run, run)
        else:
            run = 1

    participle = 0
    for w in sents:
        first = w[0].lower()
        if first.endswith("ing") and len(first) >= 5 and first not in ING_STOP:
            participle += 1
    part_pct = round(participle * 100 / len(sents), 1) if sents else 0

    def find(patterns, is_regex=False):
        hits = []
        for i, l in enumerate(raw.splitlines(), 1):
            ll = _norm(l).lower()
            for pat in patterns:
                if is_regex:
                    if re.search(pat[0], ll):
                        hits.append((i, pat[1], l.strip()[:120]))
                else:
                    if pat in ll:
                        hits.append((i, pat, l.strip()[:120]))
        return hits

    contra_hits = find(CONTRASTIVE, is_regex=True)
    block_word_hits = find([(r"\b" + re.escape(w) + r"\b", w) for w in BLOCKLIST], True)
    block_phrase_hits = find(BLOCK_PHRASES)
    intent_hits = find(INTENT_FRAMING)
    finance_hits = find(FINANCE_VAGUE)
    reader_hits = find(READER_CMDS)
    residue_hits = find(ASSISTANT_RESIDUE)

    title = next((l for l in lines if l.strip().startswith("# ")), "")
    title_colon = bool(re.search(r":", title)) and bool(
        re.search(r"(guide|everything you need|explained|mastering|demystifying|ultimate|complete)",
                  title.lower()))

    return dict(
        n_words=n_words, n_sentences=len(lens),
        emdash=emdash, emdash_per1k=per1k(emdash),
        bold=bold, bold_per1k=per1k(bold),
        mean_len=round(mean, 1), sd_len=round(sd, 1), cv=cv,
        longest_run=longest_run, participle=participle, part_pct=part_pct,
        contra=contra_hits, blockw=block_word_hits, blockp=block_phrase_hits,
        intent=intent_hits, finance=finance_hits,
        reader=reader_hits, residue=residue_hits,
        title_colon=title_colon, title=title.strip(),
    )


def _status(value, warn, bad):
    if value >= bad:
        return "FLAG"
    if value >= warn:
        return "warn"
    return "ok"


def _rows(m):
    cv_status = "FLAG" if (m['cv'] and m['cv'] < 0.4) else ("warn" if m['cv'] and m['cv'] < 0.5 else "ok")
    return [
        ("Em-dashes", f"{m['emdash']} ({m['emdash_per1k']}/1k)",
         _status(m['emdash_per1k'], 5, 10), "≤5/1k good (weak signal alone)"),
        ("Contrastive / False Reframe", f"{len(m['contra'])} hits",
         _status(len(m['contra']), 2, 4), "'not X it's Y' family; ≤1"),
        ("Sentence variance", f"mean {m['mean_len']}w, CV {m['cv']}",
         cv_status, "CV<0.4 = too uniform; human ~0.5–0.8"),
        ("Monotony run", f"{m['longest_run']} sentences",
         _status(m['longest_run'], 4, 6), "consecutive sentences within 3 words"),
        ("-ing openers", f"{m['participle']} ({m['part_pct']}%)",
         _status(m['part_pct'], 6, 10), "participle openers; human ~2–3%"),
        ("Bold emphasis", f"{m['bold']} ({m['bold_per1k']}/1k)",
         _status(m['bold_per1k'], 5, 10), "bolded punch-lines; use sparingly"),
        ("Blocklist words", f"{len(m['blockw'])} hits",
         _status(len(m['blockw']), 2, 4), "delve / robust / tapestry / etc."),
        ("Blocklist phrases", f"{len(m['blockp'])} hits",
         _status(len(m['blockp']), 1, 3), "moreover / it's worth noting / etc."),
        ("Intent framing", f"{len(m['intent'])} hits",
         _status(len(m['intent']), 1, 2), "'this article will explore' (announce, don't assert)"),
        ("Finance vagueness", f"{len(m['finance'])} hits",
         _status(len(m['finance']), 1, 3), "'experts say' / 'markets reacted' / unsourced"),
        ("Reader commands", f"{len(m['reader'])} hits",
         _status(len(m['reader']), 2, 4), "'sit with this' / 'stay with me'"),
        ("Assistant residue", f"{len(m['residue'])} hits",
         "FLAG" if m['residue'] else "ok", "'certainly!' / 'here's a breakdown'"),
        ("Title colon-formula", "yes" if m['title_colon'] else "no",
         "FLAG" if m['title_colon'] else "ok", "'X: The Ultimate Guide to Y'"),
    ]


def _slop_index(m):
    pts = 0
    pts += max(0, m['emdash_per1k'] - 5) * 1.2
    pts += len(m['contra']) * 4
    pts += (12 if (m['cv'] and m['cv'] < 0.4) else 0)
    pts += max(0, m['longest_run'] - 3) * 3
    pts += max(0, m['part_pct'] - 6) * 2
    pts += max(0, m['bold_per1k'] - 5) * 1.0
    pts += len(m['blockw']) * 3 + len(m['blockp']) * 4
    pts += len(m['intent']) * 6 + len(m['finance']) * 6
    pts += len(m['reader']) * 3
    pts += len(m['residue']) * 25
    pts += (15 if m['title_colon'] else 0)
    return round(pts)


def _verdict(slop):
    if slop < 15:
        return "CLEAN", "clean"
    if slop < 40:
        return "MINOR TELLS", "minor"
    if slop < 80:
        return "READS AI — revise", "reads_ai"
    return "HEAVY SLOP — rewrite", "heavy"


HIT_GROUPS = [
    ("Contrastive / False Reframe", "contra"),
    ("Intent framing", "intent"),
    ("Finance vagueness / unattributed", "finance"),
    ("Blocklist words", "blockw"),
    ("Blocklist phrases", "blockp"),
    ("Reader commands", "reader"),
    ("Assistant residue", "residue"),
]


def score_text(text):
    """Full structured result for one text."""
    m = analyze_text(text)
    slop = _slop_index(m)
    label, tier = _verdict(slop)
    rows = [{"metric": r[0], "value": r[1], "status": r[2], "note": r[3]} for r in _rows(m)]
    hits = {title: m[key] for title, key in HIT_GROUPS if m[key]}
    return {
        "slop_index": slop,
        "verdict": label,
        "tier": tier,
        "n_words": m["n_words"],
        "n_sentences": m["n_sentences"],
        "rows": rows,
        "hits": hits,
        "metrics": m,
    }
