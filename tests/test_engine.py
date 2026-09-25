"""Behaviour tests for slop_engine. Run: python -m unittest discover -s tests

Most of these pin a bug that was found by scoring real documents, so the
test name says what used to go wrong.
"""
import textwrap
import unittest

from samples import SAMPLES
from slop_engine import score_text

HEAVY = SAMPLES["Heavy slop (scores ~80+)"]
CLEAN = SAMPLES["Clean human draft (scores low)"]


def hits(text, group):
    return len(score_text(text)["hits"].get(group, []))


class Samples(unittest.TestCase):
    def test_heavy_sample_is_heavy(self):
        self.assertEqual(score_text(HEAVY)["tier"], "heavy")

    def test_clean_sample_is_clean(self):
        self.assertEqual(score_text(CLEAN)["tier"], "clean")


class Unscorable(unittest.TestCase):
    """Text the engine cannot read must not come back as a confident CLEAN."""

    def assertUnscored(self, text):
        r = score_text(text)
        self.assertFalse(r["scored"])
        self.assertIsNone(r["slop_index"])
        self.assertEqual(r["tier"], "unscored")
        self.assertTrue(r["notes"])

    def test_empty_input(self):
        for text in ("", None, "   \n\n "):
            with self.subTest(text=text):
                self.assertUnscored(text)

    def test_code_only(self):
        self.assertUnscored("```\ndelve into the robust tapestry\n```")

    def test_unclosed_fence_runs_to_the_end(self):
        self.assertUnscored("```\ndelve into the robust tapestry")

    def test_non_latin_scripts(self):
        for text in ("我们必须深入研究这种变革性范式的强大框架。这是一个测试文档。",
                     "Мы должны углубиться в надёжную структуру этой преобразующей парадигмы."):
            with self.subTest(text=text[:8]):
                self.assertUnscored(text)

    def test_accented_latin_is_scored(self):
        r = score_text("Le café était naïf, et le résumé aussi. On a ri.")
        self.assertTrue(r["scored"])
        self.assertEqual(r["n_words"], 11)


class ShortText(unittest.TestCase):
    def test_one_em_dash_does_not_decide_a_short_note(self):
        # used to score 98, HEAVY SLOP
        r = score_text("The plan is simple — we ship on Friday. The team meets on Tuesday.")
        self.assertEqual(r["tier"], "clean")

    def test_same_prose_gets_the_same_verdict_at_any_length(self):
        base = "The plan is simple — we ship on Friday. "
        filler = ["The team meets on Tuesday.",
                  "Budget review happens quarterly and nobody enjoys it.",
                  "She filed the report.",
                  "We moved the deadline back two weeks after the client called."]
        for n in (1, 4, 12, 40):
            with self.subTest(filler_sentences=n):
                text = base + " ".join(filler[i % 4] for i in range(n))
                self.assertEqual(score_text(text)["tier"], "clean")

    def test_a_real_pile_still_counts_in_short_text(self):
        text = "We **ship** it. We **test** it. We **love** it. We **own** it. We **sell** it."
        self.assertIn("Bold emphasis", score_text(text)["contributions"])


class MentionVersusUse(unittest.TestCase):
    def test_quoted_pattern_is_a_mention(self):
        # used to cost 25 points
        text = 'The phrase "As an AI language model" is near-conclusive.'
        self.assertEqual(hits(text, "Assistant residue"), 0)

    def test_inline_code_is_a_mention(self):
        self.assertEqual(hits("Add `delve` to the blocklist.", "Blocklist words"), 0)

    def test_real_use_still_fires(self):
        self.assertEqual(hits("Certainly! I hope this helps.", "Assistant residue"), 2)
        self.assertEqual(hits("We must delve into the robust tapestry.", "Blocklist words"), 3)


class Precision(unittest.TestCase):
    def test_noun_adjunct_is_not_a_participle_opener(self):
        # "Trading systems..." was the whole score of a profile README
        m = score_text("Trading systems in one window. Trading infrastructure on CFDs.")["metrics"]
        self.assertEqual(m["participle"], 0)

    def test_participle_opener_with_an_object_counts(self):
        m = score_text("Leveraging the concept works. Navigating the maze is hard.")["metrics"]
        self.assertEqual(m["participle"], 2)

    def test_harness_and_leverage_as_nouns(self):
        text = "Drop it into any eval harness. The fund ran 2x leverage through a leveraged ETF."
        self.assertEqual(hits(text, "Blocklist words"), 0)

    def test_harness_and_leverage_as_verbs(self):
        text = "Harnessing the wind helps. We leverage this idea."
        self.assertEqual(hits(text, "Blocklist words"), 2)


class Structure(unittest.TestCase):
    def test_markup_urls_and_code_are_not_language(self):
        text = ('<img src="./robust.svg" alt="logo"/>\n\n'
                "See https://example.com/delve-into-synergy for details.\n\n"
                "```\nrobust = True\n```\n")
        self.assertEqual(hits(text, "Blocklist words"), 0)

    def test_html_tags_are_not_words(self):
        r = score_text('<p align="center">\n  <em>Two words.</em>\n</p>')
        self.assertEqual(r["n_words"], 2)

    def test_headings_and_lists_are_scanned(self):
        self.assertEqual(hits("# A robust plan\n\n- delve deeper\n", "Blocklist words"), 2)

    def test_every_occurrence_counts(self):
        self.assertEqual(hits("We delve, then delve, then delve again.", "Blocklist words"), 3)

    def test_hits_point_at_the_source_line(self):
        r = score_text("# Title\n\nFirst line is fine.\nSecond line has robust in it.\n")
        self.assertEqual(r["hits"]["Blocklist words"][0][0], 4)

    def test_hyphenated_line_break_is_rejoined(self):
        # PDFs split compounds at line ends: "cutting-" / "edge"
        self.assertEqual(hits("This is truly cutting-\nedge work.", "Blocklist words"), 1)

    def test_a_long_numbered_step_is_a_paragraph(self):
        step = "1. " + " ".join(["We open the dashboard and check the logs."] * 5)
        self.assertEqual(score_text(step)["n_sentences"], 5)


class LineWrapping(unittest.TestCase):
    def test_score_does_not_depend_on_where_lines_break(self):
        # used to range from 172 to 200 for the same words
        paras = HEAVY.strip().split("\n\n")
        wrap = (lambda width: "\n\n".join(
            p if p.startswith("#") else textwrap.fill(" ".join(p.split()), width) for p in paras))
        scores = {score_text(wrap(w))["slop_index"] for w in (30, 50, 80, 1000)}
        self.assertEqual(len(scores), 1, scores)


class ResultShape(unittest.TestCase):
    def test_public_fields(self):
        r = score_text(HEAVY)
        for key in ("scored", "slop_index", "verdict", "tier", "n_words", "n_prose_words",
                    "n_sentences", "notes", "rows", "hits", "contributions", "metrics"):
            self.assertIn(key, r)
        self.assertEqual(len(r["rows"]), 13)
        self.assertAlmostEqual(r["slop_index"], sum(r["contributions"].values()), delta=1)

    def test_statistical_rules_are_capped(self):
        text = " ".join(["The **bold** move is ours."] * 60)
        self.assertLessEqual(score_text(text)["contributions"]["Bold emphasis"], 30)


if __name__ == "__main__":
    unittest.main()
