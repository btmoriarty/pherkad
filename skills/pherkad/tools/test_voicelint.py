#!/usr/bin/env python3
"""Regression tests for voicelint. Dependency-free.

Run from anywhere:  python3 /path/to/test_voicelint.py
Also collected by ``python3 -m unittest`` and by pytest. Exit 0 if all pass.

Covers the core rules, CLI behavior, and documented examples: word-boundary
and Unicode-edge false positives, load-bearing literal-versus-figurative
context, code masking (inline spans, backtick and tilde fences, unclosed
fences), dash and density modes with the 150-word / 3-hit floor, config
layering (shipped base plus one overlay, add_/remove_ list ops), host-versus-
path domain matching, HTML stripping, inline suppression, the rules-file
marker, JSON output, --strict, exit codes, invalid config, and line/column
accuracy. It is not exhaustive; the judgment layer is not tested here.
"""
import json
import os
import subprocess
import sys
import tempfile
import unicodedata
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import voicelint  # noqa: E402

SCRIPT = os.path.join(HERE, "voicelint.py")
DEFAULT = voicelint.load_config(None)


def rules(text, cfg=DEFAULT):
    """The set of rule names voicelint fires on a string."""
    return {f.rule for f in voicelint.check(text, cfg)}


def run(args, text=None):
    proc = subprocess.run([sys.executable, SCRIPT, *args],
                          input=text, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def write(d, name, content):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(content)
    return p


# ---------------------------------------------------------------------------
# 1. Rule firing and word-boundary false positives
# ---------------------------------------------------------------------------
# (description, text, rule, should_fire)
FIRING = [
    ("banned phrase fires", "This is a game-changer for the team.", "banned-phrase", True),
    ("banned phrase mid-word does not fire",
     "The paradigm shifts the debate.", "banned-phrase", False),
    ("banned phrase fires as a whole phrase",
     "That was a paradigm shift.", "banned-phrase", True),
    ("engagement bait fires", "Here's the thing: nobody cares.", "engagement-bait", True),
    ("banned phrase with trailing punct still fires",
     "In conclusion, we won.", "banned-phrase", True),
    ("filler fires on whole word", "A significant result.", "filler", True),
    ("filler does not fire inside a word",
     "The signification of the sign.", "filler", False),
    ("load-bearing + non-structural object is a context warning",
     "The load-bearing assumption fails.", "load-bearing-context", True),
    ("load-bearing never emits a hard error (judgment layer decides figurative)",
     "The load-bearing assumption fails.", "load-bearing", False),
    ("load-bearing + ambiguous noun emits a context warning",
     "This is the load-bearing structure of the argument.", "load-bearing-context", True),
    ("load-bearing frame is a context warning (the one physical noun used figuratively)",
     "The load-bearing frame of the argument failed.", "load-bearing-context", True),
    ("predicate load-bearing is a context warning",
     "That claim is load-bearing.", "load-bearing-context", True),
    ("engineering member is fully exempt (no finding)",
     "The load-bearing member failed inspection.", "load-bearing-context", False),
    ("literal load-bearing wall is exempt",
     "The load-bearing wall held.", "load-bearing-context", False),
    ("literal load-bearing beam is exempt",
     "The load-bearing beam passed inspection.", "load-bearing-context", False),
    ("dash fires by default", "We shipped it — then paused.", "dash", True),
    ("mathematical minus is not a dash", "The result is 5 − 3.", "dash", False),
    ("clause-final quietly warns by default (on since 0.5.2)",
     "The project was shut down quietly.", "loaded-adverb", True),
    ("pre-modifier quietly is silent",
     "A quietly skeptical engineer watched.", "loaded-adverb", False),
    ("numeric en-dash range is not a dash hit", "Pages 10–12 and 1914–18.", "dash", False),
    ("en dash between words is still a dash", "We shipped – then paused.", "dash", True),
    ("worth nothing is not worth [verb]", "It is worth nothing to us.", "soft-cliche", False),
    ("worth noting without that is still banned", "It is worth noting the gap.", "banned-phrase", True),
    ("honest family: any determiner", "One Honest First Look at the data.", "honest-framing", True),
    ("honest family: optional adjective", "An honest first take on it.", "honest-framing", True),
    ("honest family: copular form with any noun",
     "The honest obstacle is that nobody checked.", "honest-framing", True),
    ("honest subject-matter noun does not fire", "It was an honest assessment.", "honest-framing", False),
    ("honest broker does not fire", "He is an honest broker.", "honest-framing", False),
    ("honest literal adjective draws no warning either", "An honest dog, an honest animal.", "soft-cliche", False),
    ("literal placement does not fire", "The plane lands at noon.", "soft-cliche", False),
    ("abstract landing still fires", "That is where it lands.", "soft-cliche", True),
    ("desert landscape is literal", "The desert landscape changes after rain.", "soft-cliche", False),
    ("abstract landscape fires", "In the current landscape, nobody checks.", "soft-cliche", True),
    ("the one that is an ordinary relative clause", "The one that got out.", "soft-cliche", False),
    ("rhymes with is a warning now", "Cat rhymes with hat.", "banned-phrase", False),
    ("rhymes with still warns", "Cat rhymes with hat.", "soft-cliche", True),
    ("truth-is opener with comma is bait", "The truth is, it failed.", "engagement-bait", True),
    ("truth-is as a sentence is not bait", "The truth is stupider than the myth.", "engagement-bait", False),
    ("comma-tagged frankly warns", "Frankly, it failed.", "soft-cliche", True),
    ("literal truthfully does not warn", "He answers it truthfully.", "soft-cliche", False),
    ("in all honesty is banned", "In all honesty it was fine.", "banned-phrase", True),
    ("boosters are filler", "This is very important.", "filler", True),
    ("paragraph connective warns", "Moreover, the build passed.", "soft-cliche", True),
    ("watch-word overuse fires past the cap",
     "quietly quietly quietly it went", "overuse", True),
    ("no aggregator domains in the generic defaults",
     "See https://www.msn.com/story for more.", "source", False),
]


class RuleFiring(unittest.TestCase):
    def test_firing_table(self):
        for desc, text, rule, should in FIRING:
            with self.subTest(desc):
                self.assertEqual(rule in rules(text), should)

    def test_unicode_phrase_edges(self):
        nfc = unicodedata.normalize("NFC", "égame-changeré here")
        nfd = unicodedata.normalize("NFD", "égame-changer here")
        self.assertNotIn("banned-phrase", rules(nfc),
                         "phrase between precomposed accented letters must not fire")
        self.assertNotIn("banned-phrase", rules(nfd),
                         "phrase after a decomposed accent must not fire")
        self.assertIn("banned-phrase", rules("that game-changer café"))

    def test_quietly_rule_can_be_switched_off(self):
        off = dict(voicelint.load_config(None))
        off["flag_loaded_quietly"] = False
        self.assertNotIn("loaded-adverb", rules("The project was shut down quietly.", off))

    def test_overlapping_phrase_hits_collapse_to_one(self):
        fs = voicelint.check("This is what it buys you.", DEFAULT)
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0].match, "what it buys you")
        fs = voicelint.check("The honest answer is no.", DEFAULT)
        self.assertEqual([f.rule for f in fs], ["honest-framing"])

    def test_counting_rules_survive_an_overlap(self):
        # A soft phrase must not swallow the overuse count on a word inside it.
        cfg = dict(DEFAULT)
        cfg["watch_words"] = {"quietly": 0}
        cfg["soft_phrases"] = ["went quietly"]
        self.assertEqual(rules("It went quietly.", cfg), {"soft-cliche", "overuse", "loaded-adverb"})

    def test_dash_density_floor(self):
        relaxed = dict(DEFAULT)
        relaxed["no_dashes"] = False
        relaxed["dash_density_cap"] = 1.0

        def dense(words, dashes):
            text = ("word " * words) + " ".join(["—"] * dashes)
            return "dash-density" in rules(text, relaxed)

        self.assertFalse(dense(149, 3), "below the word floor, silent")
        self.assertTrue(dense(150, 3), "at the floor, warns")
        self.assertFalse(dense(150, 2), "below the hit floor, silent")
        self.assertFalse(dense(5, 2), "short text raises nothing")

    def test_line_and_column(self):
        fs = voicelint.check("ok ok\nhere game-changer now", DEFAULT)
        self.assertTrue(any(f.rule == "banned-phrase" and f.line == 2 and f.col == 6 for f in fs))


# ---------------------------------------------------------------------------
# 2. Code masking
# ---------------------------------------------------------------------------
class CodeMasking(unittest.TestCase):
    def test_inline_span(self):
        self.assertNotIn("banned-phrase", rules("The `game-changer` phrase is an example."))

    def test_backtick_fence(self):
        self.assertNotIn("banned-phrase", rules("```\ngame-changer\n```\n"))

    def test_tilde_fence(self):
        self.assertNotIn("banned-phrase", rules("~~~\ngame-changer\n~~~\n"))

    def test_unclosed_fence_masks_to_end(self):
        self.assertNotIn("banned-phrase", rules("```\ngame-changer\n"))

    def test_prose_after_a_closed_fence_still_fires(self):
        self.assertIn("banned-phrase", rules("```\ncode\n```\n\nThis is a game-changer.\n"))

    def test_same_phrase_in_prose_fires(self):
        self.assertIn("banned-phrase", rules("that game-changer here"))

    def test_blockquote_is_someone_elses_words(self):
        # voice-rules.md exempts direct quotations; structlint already skipped
        # blockquotes and voicelint did not, until the shared masking layer.
        self.assertNotIn("banned-phrase", rules("> This is a game-changer.\n"))
        self.assertNotIn("banned-phrase", rules("> > This is a game-changer.\n"))
        fs = voicelint.check("> quoted\n\nThis is a game-changer.\n", DEFAULT)
        self.assertEqual([(f.rule, f.line, f.col) for f in fs], [("banned-phrase", 3, 11)])

    def test_inline_quotation_is_still_prose(self):
        # Dialogue is the author's voice; adjudicating a direct quote is the judgment layer's.
        self.assertIn("banned-phrase", rules('She said, "this is a game-changer," and left.'))

    def test_masking_preserves_offsets(self):
        fs = voicelint.check("```\nx\n```\nhere game-changer now", DEFAULT)
        self.assertTrue(any(f.rule == "banned-phrase" and f.line == 4 and f.col == 6 for f in fs))


# ---------------------------------------------------------------------------
# 3. Config layering: shipped base, one overlay, list ops
# ---------------------------------------------------------------------------
class ConfigLayering(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        with open(os.path.join(HERE, "voice_config.json"), encoding="utf-8") as fh:
            self.shipped = json.load(fh)

    def tearDown(self):
        self.tmp.cleanup()

    def test_overlay_keeps_every_shipped_rule(self):
        # The regression: a user config used to merge onto a stale Python copy
        # of the defaults and silently drop most shipped rules.
        p = write(self.d, "c.json", json.dumps({"add_banned_phrases": ["circle back"]}))
        cfg = voicelint.load_config(p)
        self.assertEqual(len(cfg["banned_phrases"]), len(self.shipped["banned_phrases"]) + 1)
        self.assertEqual(len(cfg["soft_phrases"]), len(self.shipped["soft_phrases"]))
        self.assertEqual(len(cfg["engagement_bait"]), len(self.shipped["engagement_bait"]))
        self.assertIn("that's the news", cfg["banned_phrases"])
        self.assertIn("banned-phrase", rules("That's the news.", cfg))

    def test_deep_merge_and_list_ops(self):
        p = write(self.d, "c.json", json.dumps({
            "watch_words": {"live": 5},
            "add_banned_phrases": ["circle back"],
            "remove_banned_phrases": ["game-changer"],
        }))
        cfg = voicelint.load_config(p)
        self.assertEqual(cfg["watch_words"].get("quietly"), 2, "sibling default watch word kept")
        self.assertEqual(cfg["watch_words"].get("live"), 5)
        self.assertIn("circle back", cfg["banned_phrases"])
        self.assertNotIn("game-changer", cfg["banned_phrases"])
        self.assertNotIn("add_banned_phrases", cfg)
        self.assertNotIn("remove_banned_phrases", cfg)

    def test_explicit_shipped_path_equals_defaults(self):
        self.assertEqual(voicelint.load_config(os.path.join(HERE, "voice_config.json")), DEFAULT)

    def test_loaded_config_is_not_shared_state(self):
        a = voicelint.load_config(None)
        a["banned_phrases"].append("state leak probe")
        a["watch_words"]["quietly"] = 99
        b = voicelint.load_config(None)
        self.assertNotIn("state leak probe", b["banned_phrases"])
        self.assertEqual(b["watch_words"]["quietly"], 2)

    def test_cwd_config_is_the_overlay_when_no_flag(self):
        write(self.d, "voice_config.json", json.dumps({"add_banned_phrases": ["circle back"]}))
        write(self.d, "t.md", "We should circle back. That's the news.\n")
        proc = subprocess.run([sys.executable, SCRIPT, "--json", "t.md"],
                              cwd=self.d, capture_output=True, text=True)
        found = {f["rule"] + ":" + f["match"].lower() for f in json.loads(proc.stdout)["files"]["t.md"]}
        self.assertIn("banned-phrase:circle back", found, "cwd overlay applied")
        self.assertIn("banned-phrase:that's the news", found, "shipped rules kept")

    def test_print_config_shows_the_effective_set(self):
        p = write(self.d, "c.json", json.dumps({"no_dashes": False}))
        code, out, _ = run(["--config", p, "--print-config"])
        self.assertEqual(code, 0)
        cfg = json.loads(out)
        self.assertFalse(cfg["no_dashes"])
        self.assertEqual(len(cfg["soft_phrases"]), len(self.shipped["soft_phrases"]))


# ---------------------------------------------------------------------------
# 3b. Stable rule ids
# ---------------------------------------------------------------------------
class RuleIds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, body):
        return voicelint.load_config(write(self.d, "c.json", json.dumps(body)))

    def test_every_rule_has_a_unique_id(self):
        ids = [r["id"] for r in voicelint.all_rules(DEFAULT)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(voicelint._ID_RE.match(i) for i in ids))

    def test_string_entries_derive_ids(self):
        self.assertEqual(voicelint._derive_id("banned_phrases", "game-changer"), "banned.game-changer")
        self.assertEqual(voicelint._derive_id("soft_phrases", "worth more to [word] than"),
                         "soft.worth-more-to-word-than")
        self.assertTrue(voicelint._derive_id("soft_phrases", r"re:\bx\b").startswith("soft.re-"))

    def test_colliding_slugs_stay_distinct(self):
        ids = {r["id"] for r in voicelint.all_rules(DEFAULT)}
        self.assertIn("soft.gut-check", ids)
        self.assertEqual(sum(1 for i in ids if i.startswith("soft.gut-check")), 2)

    def test_findings_carry_the_id(self):
        fs = voicelint.check("This is a game-changer. In the current landscape, nobody checks.", DEFAULT)
        self.assertEqual({f.rule_id for f in fs}, {"banned.game-changer", "soft.abstract-landscape"})
        fs = voicelint.check("We shipped — then paused. quietly quietly quietly it went.", DEFAULT)
        self.assertIn("dash", {f.rule_id for f in fs})
        self.assertIn("overuse.quietly", {f.rule_id for f in fs})

    def test_remove_by_id(self):
        # The point of the change: an overlay drops a shipped regex without pasting it.
        cfg = self.load({"remove_soft_phrases": ["soft.abstract-landscape"]})
        self.assertNotIn("soft-cliche", rules("In the current landscape, nobody checks.", cfg))
        self.assertIn("soft-cliche", rules("The landscape of the field.", cfg), "other rules untouched")

    def test_remove_by_pattern_still_works(self):
        cfg = self.load({"remove_banned_phrases": ["game-changer"]})
        self.assertNotIn("banned-phrase", rules("This is a game-changer.", cfg))

    def test_add_an_object_rule(self):
        cfg = self.load({"add_banned_phrases": [
            {"id": "banned.circle-back", "pattern": "circle back", "rationale": "meeting filler",
             "fires": ["Let us circle back."], "clean": ["The circle is back."]}]})
        fs = voicelint.check("Let us circle back.", cfg)
        self.assertEqual([f.rule_id for f in fs], ["banned.circle-back"])

    def test_add_skips_a_duplicate_by_id_or_pattern(self):
        cfg = self.load({"add_banned_phrases": ["game-changer", {"id": "banned.game-changer", "pattern": "gamechanger"}]})
        n = sum(1 for e in voicelint.rule_entries(cfg, "banned_phrases") if e["id"] == "banned.game-changer")
        self.assertEqual(n, 1)

    def test_duplicate_explicit_ids_are_a_config_error(self):
        p = write(self.d, "dup.json", json.dumps({"banned_phrases": [
            {"id": "banned.x", "pattern": "one"}, {"id": "banned.x", "pattern": "two"}]}))
        self.assertEqual(run(["--config", p, "-"], "ok")[0], 2)

    def test_bad_rule_objects_are_config_errors(self):
        for desc, body in {
            "no pattern": {"banned_phrases": [{"id": "banned.x"}]},
            "bad id": {"banned_phrases": [{"id": "Banned X", "pattern": "x"}]},
            "unknown key": {"banned_phrases": [{"pattern": "x", "why": "y"}]},
            "fires not a list": {"banned_phrases": [{"pattern": "x", "fires": "x"}]},
        }.items():
            with self.subTest(desc):
                p = write(self.d, "bad.json", json.dumps(body))
                self.assertEqual(run(["--config", p, "-"], "ok")[0], 2)

    def test_ignore_line_by_id(self):
        kept, dropped = voicelint.check_counting(
            "This is a game-changer. <!-- voicelint: ignore-line banned.game-changer -->", DEFAULT)
        self.assertEqual((kept, dropped), ([], 1))

    def test_json_output_has_rule_id(self):
        p = write(self.d, "t.md", "This is a game-changer.\n")
        code, out, _ = run(["--json", p])
        self.assertEqual(json.loads(out)["files"][p][0]["rule_id"], "banned.game-changer")

    def test_list_rules(self):
        code, out, _ = run(["--list-rules"])
        self.assertEqual(code, 0)
        self.assertIn("banned.game-changer\tbanned-phrase\terror\tgame-changer", out)
        code, out, _ = run(["--list-rules", "--json"])
        self.assertTrue(any(r["id"] == "honest-framing" for r in json.loads(out)))

    def test_shipped_examples_hold(self):
        # Every rule object that carries examples is a tested rule.
        for field in voicelint._LIST_FIELDS:
            for e in voicelint.rule_entries(DEFAULT, field):
                for text in e.get("fires", []):
                    with self.subTest(rule=e["id"], fires=text):
                        self.assertIn(e["id"], {f.rule_id for f in voicelint.check(text, DEFAULT)})
                for text in e.get("clean", []):
                    with self.subTest(rule=e["id"], clean=text):
                        self.assertNotIn(e["id"], {f.rule_id for f in voicelint.check(text, DEFAULT)})


# ---------------------------------------------------------------------------
# 4. Domain matching reads the host, not the whole URL
# ---------------------------------------------------------------------------
class DomainMatching(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.news = voicelint.load_config(os.path.join(HERE, "examples", "news-brief.json"))

    def fires(self, text):
        return "source" in rules(text, self.news)

    def test_hosts(self):
        self.assertTrue(self.fires("See https://www.msn.com/story here."))
        self.assertTrue(self.fires("See https://timesofindia.indiatimes.com/x here."))
        self.assertTrue(self.fires("See https://www.msn.com./story here."), "trailing dot")
        self.assertFalse(self.fires("See https://example.com/path/msn.com/story here."), "path")
        self.assertFalse(self.fires("See https://example.com/?u=https://msn.com/x here."), "query")
        self.assertFalse(self.fires("See https://www.congress.gov/bill here."))
        self.assertFalse(self.fires("See https://msn.com@evil.example/x here."), "userinfo")


# ---------------------------------------------------------------------------
# 5. HTML
# ---------------------------------------------------------------------------
class Html(unittest.TestCase):
    def test_strip_preserves_line_numbers(self):
        fs = voicelint.check(voicelint.strip_html("<p>ok</p>\n<p>This is a game-changer.</p>"), DEFAULT)
        self.assertTrue(any(f.rule == "banned-phrase" and f.line == 2 for f in fs))

    def test_directive_survives_stripping(self):
        # The regression: strip_html removed every comment, so ignore-line was dead in HTML.
        text = voicelint.strip_html(
            "<p>This is a game-changer. <!-- voicelint: ignore-line --></p>\n"
            "<p>This is a game-changer.</p>")
        kept, dropped = voicelint.check_counting(text, DEFAULT)
        self.assertEqual(dropped, 1)
        self.assertEqual([f.line for f in kept], [2])


# ---------------------------------------------------------------------------
# 6. Inline suppression, whole-file allowances, the rules-file marker
# ---------------------------------------------------------------------------
class Suppression(unittest.TestCase):
    def counting(self, text):
        return voicelint.check_counting(text, DEFAULT)

    def test_ignore_line(self):
        kept, dropped = self.counting("This is a game-changer. <!-- voicelint: ignore-line banned-phrase -->")
        self.assertEqual((kept, dropped), ([], 1))

    def test_ignore_next_line(self):
        kept, dropped = self.counting("<!-- voicelint: ignore-next-line -->\nThis is a game-changer.")
        self.assertEqual((kept, dropped), ([], 1))

    def test_rule_specific_ignore_leaves_others(self):
        kept, dropped = self.counting("This is a game-changer. <!-- voicelint: ignore-line filler -->")
        self.assertEqual((len(kept), dropped), (1, 0))

    def test_backticked_directive_does_not_suppress(self):
        kept, dropped = self.counting("This is a game-changer. `voicelint: ignore-line`")
        self.assertEqual((len(kept), dropped), (1, 0))

    def test_directive_in_prose_does_not_suppress(self):
        kept, dropped = self.counting("This is a game-changer and the words voicelint: ignore-line appear.")
        self.assertEqual((len(kept), dropped), (1, 0))

    def test_rules_file_marker_silences_the_file(self):
        kept, dropped = self.counting("<!-- voicelint: rules-file -->\n\nThis is a game-changer.\n")
        self.assertEqual((kept, dropped), ([], 0))

    def test_rules_file_marker_in_code_is_text(self):
        # The regression: the marker was matched on raw text before code masking.
        kept, _ = self.counting("`<!-- voicelint: rules-file -->`\n\nThis is a game-changer.\n")
        self.assertEqual(len(kept), 1)
        kept, _ = self.counting("```\n<!-- voicelint: rules-file -->\n```\n\nThis is a game-changer.\n")
        self.assertEqual(len(kept), 1)

    def test_rules_file_marker_in_prose_is_text(self):
        kept, _ = self.counting("Add <!-- voicelint: rules-file --> to opt in. This is a game-changer.\n")
        self.assertEqual(len(kept), 1)

    def test_allow_marker_is_whole_words(self):
        # The regression: allowing "land" used to swallow a "landscape" finding.
        kept, dropped = self.counting(
            "<!-- voicelint-allow: land (literal: aircraft) -->\n\nIn the current landscape, nobody checks.\n")
        self.assertEqual((len(kept), dropped), (1, 0))

    def test_allow_marker_exempts_the_phrase(self):
        kept, dropped = self.counting(
            "<!-- voicelint-allow: rhymes with (literal: two names that rhyme) -->\n\nCat rhymes with hat.\n")
        self.assertEqual(kept, [])
        self.assertGreaterEqual(dropped, 1)


# ---------------------------------------------------------------------------
# 7. CLI contract: exit codes, --strict, --json, invalid config
# ---------------------------------------------------------------------------
class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.clean = write(d, "clean.md", "A short, clean sentence about the weather.\n")
        self.dirty = write(d, "dirty.md", "This is a game-changer.\n")
        self.warnonly = write(d, "warn.md", "A significant result.\n")  # filler = warning only
        self.d = d

    def tearDown(self):
        self.tmp.cleanup()

    def cfg(self, name, body):
        return write(self.d, name, body)

    def test_exit_codes(self):
        self.assertEqual(run([self.clean])[0], 0, "clean file exits 0")
        self.assertEqual(run([self.dirty])[0], 1, "error finding exits 1")
        self.assertEqual(run(["/no/such/file.md"])[0], 2, "missing file exits 2")
        self.assertEqual(run([self.warnonly])[0], 0, "warning-only exits 0 without --strict")
        self.assertEqual(run(["--strict", self.warnonly])[0], 1, "warning-only exits 1 with --strict")
        self.assertEqual(run([])[0], 2, "no files is a usage error")

    def test_json_output(self):
        code, out, _ = run(["--json", self.dirty])
        parsed = json.loads(out)
        self.assertIn("files", parsed)
        self.assertIn("suppressed", parsed)
        self.assertTrue(any(x["rule"] == "banned-phrase" for x in parsed["files"][self.dirty]))

    def test_invalid_configs_exit_2(self):
        cases = {
            "not a list": '{"banned_phrases": "not a list"}',
            "string in a boolean field": '{"no_dashes": "false"}',
            "unknown key": '{"no_dash": false}',
            "negative watch-word cap": '{"watch_words": {"quietly": -1}}',
            "empty configured phrase": '{"add_banned_phrases": [""]}',
            "empty watch-word key": '{"watch_words": {"": 1}}',
        }
        for desc, body in cases.items():
            with self.subTest(desc):
                self.assertEqual(run(["--config", self.cfg("bad.json", body), self.clean])[0], 2)

    def test_comment_key_is_allowed(self):
        p = self.cfg("ok.json", '{"no_dashes": false, "_note": "fine"}')
        self.assertEqual(run(["--config", p, self.clean])[0], 0)

    def test_html_by_extension(self):
        p = write(self.d, "page.html", "<p>ok</p>\n<p>This is a game-changer.</p>\n")
        code, out, _ = run(["--json", p])
        self.assertEqual(code, 1)
        self.assertTrue(any(f["line"] == 2 for f in json.loads(out)["files"][p]))


# ---------------------------------------------------------------------------
# 8. Example fixtures behave as shipped
# ---------------------------------------------------------------------------
class Examples(unittest.TestCase):
    EX = os.path.join(HERE, "examples")

    def test_good_is_clean(self):
        p = os.path.join(self.EX, "good.md")
        if not os.path.exists(p):
            self.skipTest("no examples/good.md")
        self.assertEqual(run([p])[0], 0)

    def test_bad_has_findings(self):
        p = os.path.join(self.EX, "bad.md")
        if not os.path.exists(p):
            self.skipTest("no examples/bad.md")
        self.assertEqual(run([p])[0], 1)


if __name__ == "__main__":
    unittest.main()
