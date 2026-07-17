#!/usr/bin/env python3
"""Regression tests for voicelint. Dependency-free.

Run from this directory:  python3 test_voicelint.py
Exit 0 if all pass, 1 otherwise. Safe to wire into CI.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import voicelint  # noqa: E402

CFG = voicelint.load_config(os.path.join(HERE, "voice_config.json"))


def rules(text):
    """Return the set of rule names voicelint fires on a string."""
    return {f.rule for f in voicelint.check(text, CFG)}


# (description, text, rule, should_fire)
CASES = [
    ("trailing quietly (verb-final)", "The project was shut down quietly.", "loaded-adverb", True),
    ("trailing quietly (clause-final)", "The numbers moved quietly.", "loaded-adverb", True),
    ("pre-modifier stance", "A quietly skeptical engineer watched the queue.", "loaded-adverb", False),
    ("pre-modifier verb", "They were quietly building a competitor.", "loaded-adverb", False),
    ("em dash", "We shipped it, then paused, like this it stalled.", "dash", False),
    ("banned phrase", "This is a game-changer for the team.", "banned-phrase", True),
]


def run():
    failures = []
    for desc, text, rule, should in CASES:
        fired = rule in rules(text)
        if fired != should:
            failures.append(
                f"  {desc!r}: expected {rule} {'to fire' if should else 'not to fire'}, "
                f"got {'fired' if fired else 'silent'}\n    text: {text!r}"
            )
    if failures:
        print("FAIL ({} of {} cases):".format(len(failures), len(CASES)))
        print("\n".join(failures))
        return 1
    print("ok: {} cases passed".format(len(CASES)))
    return 0


if __name__ == "__main__":
    sys.exit(run())
