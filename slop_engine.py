"""
slop_engine.py — importable scoring core for the AI-Slop Scanner.

Refactored from `slop_scan.py` (a 290-line stdlib AI-slop linter built for the
Medium content pipeline) so it takes a STRING and returns STRUCTURED results
(no printing, no file I/O) — the shape a web UI or an eval harness can consume.

No single metric proves AI authorship; what matters is DENSITY and CO-OCCURRENCE.
Treat flags as "go look," not "delete on sight." The human reader is the judge.

The text is read two ways, from one cleaned copy:
  * lexical view: every line of natural language (prose, headings, lists,
    quotes, table cells). Word and phrase rules match here, once per
    occurrence, across line wraps.
  * rhythm view: paragraphs of running prose, split into sentences inside
    each paragraph. Density and sentence-shape rules measure here. Labels
    and captions (a line with no full stop) are left out, and so are
    bullets, unless a bullet holds two or more sentences of its own.
Neither view sees code, frontmatter, HTML tags, URLs or inline code, and the
lexical view also skips double-quoted spans: writing about "delve" is not
using it.

Public API:
    score_text(text: str) -> dict   # metrics, per-rule rows, SLOP INDEX, verdict, flagged spans

When the text cannot be judged (no readable text, or not in a Latin script)
result["scored"] is False and result["slop_index"] is None, so a gate such as
`r["slop_index"] < 15` fails loudly instead of passing text nobody read.
"""

import bisect
import re
import statistics

# ---------------------------------------------------------------------------
# Word / phrase lists (from the AI-tells guardrail checklist)
# ---------------------------------------------------------------------------
BLOCKLIST = [
    "delve", "navigate", "underscore", "showcase", "foster",
    "unlock", "elevate", "embark", "unleash", "spearhead",
    "illuminate", "resonate", "streamline",
    "robust", "comprehensive", "nuanced", "pivotal", "holistic", "seamless",
    "transformative", "intricate", "multifaceted", "ever-evolving",
    "cutting-edge", "game-changing", "unparalleled",
    "tapestry", "testament", "realm", "landscape", "ecosystem", "paradigm",
    "synergy", "confluence", "trajectory",
]

# Ordinary nouns in engineering and finance ("eval harness", "2x leverage",
# "a leveraged ETF") that only read as slop as verbs taking an object:
# "harnessing the power", "leverage this concept".
_DET = r"(?:the|a|an|this|that|these|those|its|their|our|your|his|her|my)"
VERB_ONLY = [
    (r"\bharnessing\b|\bharness(?:es|ed)?\s+" + _DET + r"\b", "harness"),
    (r"\bleveraging\b|\bleverag(?:e|es|ed)\s+" + _DET + r"\b", "leverage"),
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

# A participial opener takes an object ("Leveraging THIS concept…"); a noun
# adjunct does not ("Trading systems…"). Only the first is the tell.
DETERMINERS = {
    "the", "a", "an", "this", "that", "these", "those", "your", "our", "its",
    "their", "his", "her", "my", "each", "every", "such", "another", "any",
}

# Rates are measured over at least this much text. Without a floor, one
# em-dash in twelve words is 83 per thousand and a one-sentence draft opening
# with "Leveraging the…" is 100% participle openers. With it, a single
# occurrence in a short text barely registers but a real pile still does.
RATE_FLOOR_WORDS = 150
RATE_FLOOR_SENTENCES = 10

# Rate and shape measurements are noisy, so none of them may carry a verdict
# on its own. Lexical hits are concrete, cited spans and stay uncapped.
STAT_CAP = 30


def _phrases(items):
    return [(r"(?<!\w)" + re.escape(p) + r"(?!\w)", p) for p in items]


LEXICAL_RULES = {
    key: [(re.compile(p, re.I), label) for p, label in pats]
    for key, pats in {
        "contra": CONTRASTIVE,
        "blockw": [(r"\b" + re.escape(w) + r"\b", w) for w in BLOCKLIST] + VERB_ONLY,
        "blockp": _phrases(BLOCK_PHRASES),
        "intent": _phrases(INTENT_FRAMING),
        "finance": _phrases(FINANCE_VAGUE),
        "reader": _phrases(READER_CMDS),
        "residue": _phrases(ASSISTANT_RESIDUE),
    }.items()
}

# ---------------------------------------------------------------------------
# Cleaning. Everything here keeps string length and line count unchanged, so
# a match offset in the cleaned text still points at the right source line.
# ---------------------------------------------------------------------------
_WORD = re.compile(r"[^\W_](?:[^\W_]|')*")
_FENCE = re.compile(r"^\s{0,3}(```|~~~)")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_LINK = re.compile(r"\[([^\]\n]*)\]\(([^)\n]*)\)")
_URL = re.compile(r"(?:https?://|www\.)[^\s<>()\[\]]*[^\s<>()\[\].,;:!?'\"]")
_QUOTED = re.compile(r'"[^"]{1,80}"')
_BOLD = re.compile(r"\*\*(?=\S)[^*\n]*?\S\*\*|__(?=\S)[^_\n]*?\S__")
_HEADING = re.compile(r"^\s*#{1,6}(?=\s|$)")
_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_SENT_END = re.compile(r"(?<=[.!?])\s+")
_TERMINAL = re.compile(r"[.!?:;][\"')\]]*$")

# Headings, list items and table rows are each a unit of their own. Prose and
# quote lines run together into paragraphs until a blank line.
_STANDALONE = {"heading", "list", "table", "rule", "image", "link", "sources"}
_LEXICAL_KINDS = {"prose", "heading", "list", "quote", "table"}


def _spaces(m):
    return re.sub(r"[^\n]", " ", m.group())


def _norm(text):
    return (text.replace("\r\n", "\n").replace("\r", "\n")
                .replace("’", "'").replace("‘", "'")
                .replace("“", '"').replace("”", '"')
                .replace(" ", " "))


def _mask_non_language(text):
    """Blank out frontmatter, fenced code, HTML comments and tags."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                lines[:i + 1] = [""] * (i + 1)
                break
    fence = None                      # an unclosed fence runs to the end
    for i, line in enumerate(lines):
        m = _FENCE.match(line)
        if fence or m:
            lines[i] = ""
            if fence and m and m.group(1) == fence:
                fence = None
            elif not fence:
                fence = m.group(1)
    text = _COMMENT.sub(_spaces, "\n".join(lines))
    return _TAG.sub(_spaces, text)


def _line_kind(line):
    s = line.strip()
    if not s:
        return "blank"
    if _RULE.match(s):
        return "rule"
    if _HEADING.match(s):
        return "heading"
    if s.startswith(">"):
        return "quote"
    if s.startswith("|"):
        return "table"
    if _LIST.match(s):
        return "list"
    if s.startswith("!["):
        return "image"
    if re.match(r"^\[[^\]]+\]\(", s):
        return "link"
    if s.lower().startswith(("sources:", "*sources", "_sources", "(sources")):
        return "sources"
    return "prose"


def _clean_line(line, kind):
    """Strip markup from one line without changing its length."""
    if kind == "heading":
        line = _HEADING.sub(_spaces, line, count=1)
    elif kind == "quote":
        line = re.sub(r"^[\s>]+", _spaces, line)
    elif kind == "list":
        line = _LIST.sub(_spaces, line, count=1)
    elif kind == "table":
        line = line.replace("|", " ")
    line = _INLINE_CODE.sub(_spaces, line)
    line = _LINK.sub(lambda m: " " + m.group(1) + " " * (len(m.group(2)) + 3), line)
    line = _URL.sub(_spaces, line)
    return re.sub(r"[*_]", " ", line)


def _blocks(lines):
    """Yield (kind, [(lineno, masked_line, clean_line), ...]) paragraphs."""
    block, current = [], None
    for lineno, line in enumerate(lines, 1):
        kind = _line_kind(line)
        if kind == "blank" or kind != current or kind in _STANDALONE:
            if block:
                yield current, block
            block, current = [], kind
        if kind != "blank":
            block.append((lineno, line, _clean_line(line, kind)))
    if block:
        yield current, block


def _join(block):
    """One string per paragraph, plus where each source line starts in it."""
    starts, pos = [], 0
    for _, _, clean in block:
        starts.append(pos)
        pos += len(clean) + 1
    return " ".join(clean for _, _, clean in block), starts


def _is_participle_opener(words):
    first = words[0].lower()
    if not (first.endswith("ing") and len(first) >= 5 and first not in ING_STOP):
        return False
    return len(words) > 1 and words[1].lower() in DETERMINERS


def analyze_text(raw):
    """Compute the raw metric dict from a text string."""
    source_lines = _norm(raw or "").split("\n")
    lines = _mask_non_language("\n".join(source_lines)).split("\n")
    blocks = list(_blocks(lines))

    # ---- lexical view -----------------------------------------------------
    hits = {key: [] for key in LEXICAL_RULES}
    lexical_text = []
    for kind, block in blocks:
        if kind not in _LEXICAL_KINDS:
            continue
        text, starts = _join(block)
        lexical_text.append(text)
        text = _QUOTED.sub(_spaces, text)          # mentions, not uses
        for key, rules in LEXICAL_RULES.items():
            for rx, label in rules:
                for m in rx.finditer(text):
                    lineno = block[bisect.bisect_right(starts, m.start()) - 1][0]
                    hits[key].append((lineno, label, source_lines[lineno - 1].strip()[:120]))
    for found in hits.values():
        found.sort(key=lambda h: h[0])

    lexical = " ".join(lexical_text)
    n_words = len(_WORD.findall(lexical))
    letters = [c for c in lexical if c.isalpha()]
    latin = sum(1 for c in letters if c <= "ɏ")
    unsupported_script = (len(letters) - latin) >= 20 and latin < len(letters) - latin

    # ---- rhythm view -------------------------------------------------------
    sents, emdash, bold, n_prose_words, fragments = [], 0, 0, 0, 0
    for kind, block in blocks:
        if kind not in ("prose", "list"):
            continue
        text, _ = _join(block)
        parts = [w for w in (_WORD.findall(p) for p in _SENT_END.split(text)) if len(w) >= 2]
        if len(parts) < 2:
            if kind == "list":
                continue                          # a bullet, not a paragraph
            if not _TERMINAL.search(text.rstrip()):
                fragments += 1                    # a label or caption
                continue
        sents += parts
        emdash += text.count("—")
        bold += sum(len(_BOLD.findall(masked)) for _, masked, _ in block)
        n_prose_words += len(_WORD.findall(text))

    per1k = (lambda c: round(c * 1000 / max(n_prose_words, RATE_FLOOR_WORDS), 1)
             if n_prose_words else 0)
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
    participle = sum(1 for w in sents if _is_participle_opener(w))
    part_pct = round(participle * 100 / max(len(sents), RATE_FLOOR_SENTENCES), 1) if sents else 0

    variance_ok = len(lens) >= RATE_FLOOR_SENTENCES

    title = next((l for l in lines if re.match(r"^\s*#\s", l)), "")
    title_colon = bool(re.search(r":", title)) and bool(
        re.search(r"(guide|everything you need|explained|mastering|demystifying|ultimate|complete)",
                  title.lower()))

    notes = []
    if not n_words:
        notes.append("No readable text found. A scanned PDF (pages saved as images) "
                     "has no text layer to read.")
    elif unsupported_script:
        notes.append("Most of this text is outside the Latin alphabet. The word "
                      "lists and sentence rules only cover English, so it was not scored.")
    else:
        if n_prose_words < RATE_FLOOR_WORDS:
            notes.append(f"Short text ({n_prose_words} words of running prose). Rates are "
                         f"measured over at least {RATE_FLOOR_WORDS} words, so a single "
                         "em-dash or bold phrase can't decide the verdict.")
        if fragments >= 3:
            notes.append(f"{fragments} fragments (labels, captions, lines with no full "
                         "stop) were left out of the sentence rules.")
        if not variance_ok:
            notes.append(f"Only {len(lens)} sentences. Sentence-length variance needs "
                         f"{RATE_FLOOR_SENTENCES} and was not scored.")

    return dict(
        n_words=n_words, n_prose_words=n_prose_words, n_sentences=len(lens),
        emdash=emdash, emdash_per1k=per1k(emdash),
        bold=bold, bold_per1k=per1k(bold),
        mean_len=round(mean, 1), sd_len=round(sd, 1), cv=cv,
        longest_run=longest_run, participle=participle, part_pct=part_pct,
        contra=hits["contra"], blockw=hits["blockw"], blockp=hits["blockp"],
        intent=hits["intent"], finance=hits["finance"],
        reader=hits["reader"], residue=hits["residue"],
        title_colon=title_colon, title=title.strip(),
        variance_ok=variance_ok, fragments=fragments,
        unsupported_script=unsupported_script, notes=notes,
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
         cv_status if m['variance_ok'] else "n/a", "CV<0.4 = too uniform; human ~0.5–0.8"),
        ("Monotony run", f"{m['longest_run']} sentences",
         _status(m['longest_run'], 4, 6), "consecutive sentences within 3 words"),
        ("-ing openers", f"{m['participle']} ({m['part_pct']}%)",
         _status(m['part_pct'], 6, 10), "'Leveraging the…' openers; human ~2–3%"),
        ("Bold emphasis", f"{m['bold']} ({m['bold_per1k']}/1k)",
         _status(m['bold_per1k'], 5, 10), "bolded punch-lines in prose; use sparingly"),
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


def contributions(m):
    """Points each rule adds to the SLOP INDEX. Unscored rules are absent."""
    c = {"Em-dashes": min(STAT_CAP, max(0, m['emdash_per1k'] - 5) * 1.2),
         "Contrastive / False Reframe": len(m['contra']) * 4}
    if m['variance_ok']:
        c["Sentence variance"] = 12 if (m['cv'] and m['cv'] < 0.4) else 0
    c["Monotony run"] = min(STAT_CAP, max(0, m['longest_run'] - 3) * 3)
    c["-ing openers"] = min(STAT_CAP, max(0, m['part_pct'] - 6) * 2)
    c["Bold emphasis"] = min(STAT_CAP, max(0, m['bold_per1k'] - 5) * 1.0)
    c["Blocklist words"] = len(m['blockw']) * 3
    c["Blocklist phrases"] = len(m['blockp']) * 4
    c["Intent framing"] = len(m['intent']) * 6
    c["Finance vagueness"] = len(m['finance']) * 6
    c["Reader commands"] = len(m['reader']) * 3
    c["Assistant residue"] = len(m['residue']) * 25
    c["Title colon-formula"] = 15 if m['title_colon'] else 0
    return c


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
    scored = bool(m["n_words"]) and not m["unsupported_script"]
    rows = [{"metric": r[0], "value": r[1], "status": r[2] if scored else "n/a", "note": r[3]}
            for r in _rows(m)]
    if scored:
        points = contributions(m)
        slop = round(sum(points.values()))
        label, tier = _verdict(slop)
    else:
        points, slop, tier = {}, None, "unscored"
        label = ("NOT SCORED — non-Latin script" if m["unsupported_script"]
                 else "NOT SCORED — no readable text")
    return {
        "scored": scored,
        "slop_index": slop,
        "verdict": label,
        "tier": tier,
        "n_words": m["n_words"],
        "n_prose_words": m["n_prose_words"],
        "n_sentences": m["n_sentences"],
        "notes": m["notes"],
        "rows": rows,
        "hits": {title: m[key] for title, key in HIT_GROUPS if m[key]},
        "contributions": {k: round(v, 1) for k, v in points.items() if v},
        "metrics": m,
    }
