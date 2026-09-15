#!/usr/bin/env python3
"""Tests for mdmask, the shared reading of Markdown structure. Dependency-free.

Run from anywhere:  python3 /path/to/test_mdmask.py
Also collected by ``python3 -m unittest`` and by pytest.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mdmask  # noqa: E402


class LineKinds(unittest.TestCase):
    def kinds(self, text):
        return mdmask.line_kinds(text)

    def test_every_kind(self):
        text = ("# Title\n"
                "prose here\n"
                "\n"
                "> quoted\n"
                "| a | b |\n"
                "|---|---|\n"
                "- item\n"
                "1. step\n"
                "**Type:** **Title:** x\n"
                "```\n"
                "code\n"
                "```\n"
                "after")
        self.assertEqual(self.kinds(text), [
            "heading", "prose", "blank", "blockquote", "table", "table", "list", "list",
            "field", "code", "code", "code", "prose"])

    def test_tilde_fence_and_longer_closer(self):
        self.assertEqual(self.kinds("~~~\nx\n~~~~\ny"), ["code", "code", "code", "prose"])

    def test_shorter_closer_does_not_close(self):
        self.assertEqual(self.kinds("````\nx\n```\ny"), ["code"] * 4)

    def test_unclosed_fence_runs_to_the_end(self):
        self.assertEqual(self.kinds("```\nx\ny"), ["code"] * 3)

    def test_blockquote_inside_a_fence_is_code(self):
        self.assertEqual(self.kinds("```\n> x\n```"), ["code"] * 3)

    def test_backtick_fence_info_string_may_not_contain_a_backtick(self):
        # CommonMark: ``` foo ` bar is not a fence opener.
        self.assertEqual(self.kinds("``` a ` b\nx"), ["prose", "prose"])

    def test_nested_blockquote(self):
        self.assertEqual(self.kinds("> > deep"), ["blockquote"])

    def test_count_matches_split(self):
        text = "a\n\n\nb\n"
        self.assertEqual(len(self.kinds(text)), len(text.split("\n")))


class Mask(unittest.TestCase):
    def test_length_and_newlines_preserved(self):
        text = "prose `code` here\n```\nfenced\n```\n> quote\nend"
        m = mdmask.mask(text, ("code", "blockquote"))
        self.assertEqual(len(m), len(text))
        self.assertEqual(m.count("\n"), text.count("\n"))
        self.assertEqual([i for i, c in enumerate(text) if c == "\n"],
                         [i for i, c in enumerate(m) if c == "\n"])

    def test_masks_named_kinds_only(self):
        text = "prose\n> quote\n| t |\n"
        self.assertEqual(mdmask.mask(text, ("blockquote",)).split("\n"), ["prose", "       ", "| t |", ""])
        self.assertEqual(mdmask.mask(text, ("blockquote", "table")).split("\n"), ["prose", "       ", "     ", ""])

    def test_inline_code_blanked_on_remaining_lines(self):
        self.assertEqual(mdmask.mask("say `x` now", ()), "say     now")
        self.assertEqual(mdmask.mask("say `x` now", (), inline_code=False), "say `x` now")

    def test_fence_lines_themselves_are_masked(self):
        self.assertEqual(mdmask.mask("```py\nx\n```", ("code",)), "     \n \n   ")

    def test_helpers(self):
        self.assertEqual(mdmask.heading_text("## The Title ##"), "The Title")
        self.assertIsNone(mdmask.heading_text("not a heading"))
        self.assertTrue(mdmask.is_list_item("- x"))
        self.assertTrue(mdmask.is_list_item("12) x"))
        self.assertFalse(mdmask.is_list_item("x - y"))
        self.assertEqual(mdmask.strip_inline_code("a `b` c"), "a     c")


if __name__ == "__main__":
    unittest.main()
