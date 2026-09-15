#!/usr/bin/env python3
"""Tests for the eval harness scorer. Dependency-free.

Run from anywhere:  python3 /path/to/test_study.py
Also collected by ``python3 -m unittest`` and by pytest.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import study  # noqa: E402


def row(bid, writer, candidate, rating="", flag="", pick=""):
    return {"blind_id": bid, "writer": writer, "candidate": candidate,
            "rating": rating, "fidelity_flag": flag, "forced_choice_pick": pick}


class ReadRatings(unittest.TestCase):
    ROWS = [row("item-a", "brian", "a"), row("item-b", "brian", "b"), row("item-c", "brian", "c")]

    def test_pick_resolves_to_the_named_letter_not_the_row(self):
        # The regression: entering "b" on row "a" used to count as picking "a".
        rows = [row("item-a", "brian", "a", pick="b"), row("item-b", "brian", "b"), row("item-c", "brian", "c")]
        _, picks = study._read_ratings(rows)
        self.assertEqual(picks, {"brian": ["item-b"]})

    def test_pick_on_its_own_row_still_works(self):
        rows = [row("item-a", "brian", "a"), row("item-b", "brian", "b", pick="B"), row("item-c", "brian", "c")]
        _, picks = study._read_ratings(rows)
        self.assertEqual(picks, {"brian": ["item-b"]})

    def test_unknown_letter_stops_the_run(self):
        rows = [row("item-a", "brian", "a", pick="z"), row("item-b", "brian", "b")]
        with self.assertRaises(SystemExit):
            study._read_ratings(rows)

    def test_conflicting_picks_stop_the_run(self):
        rows = [row("item-a", "brian", "a", pick="a"), row("item-b", "brian", "b", pick="b")]
        with self.assertRaises(SystemExit):
            study._read_ratings(rows)

    def test_same_pick_on_two_rows_is_one_pick(self):
        rows = [row("item-a", "brian", "a", pick="b"), row("item-b", "brian", "b", pick="b")]
        _, picks = study._read_ratings(rows)
        self.assertEqual(picks, {"brian": ["item-b"]})

    def test_picks_are_per_writer(self):
        rows = [row("item-a", "brian", "a", pick="b"), row("item-b", "brian", "b"),
                row("item-x", "rosa", "a"), row("item-y", "rosa", "b", pick="a")]
        _, picks = study._read_ratings(rows)
        self.assertEqual(picks, {"brian": ["item-b"], "rosa": ["item-x"]})

    def test_ratings_parse_with_flag(self):
        rows = [row("item-a", "brian", "a", rating="4", flag="f"), row("item-b", "brian", "b")]
        ratings, _ = study._read_ratings(rows)
        self.assertEqual(ratings, {"item-a": (4.0, "F")})

    def test_rating_out_of_range_stops_the_run(self):
        with self.assertRaises(SystemExit):
            study._read_ratings([row("item-a", "brian", "a", rating="7")])

    def test_rating_not_a_number_stops_the_run(self):
        with self.assertRaises(SystemExit):
            study._read_ratings([row("item-a", "brian", "a", rating="four")])


if __name__ == "__main__":
    unittest.main()
