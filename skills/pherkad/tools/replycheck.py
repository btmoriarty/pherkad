#!/usr/bin/env python3
"""replycheck: preflight an assistant's chat reply before it is shown.

Roadmap item 2. Most of the AI-speak the author objects to arrives in chat
replies from a coding assistant, where nothing ran the linter. This is the
check for that gap: both scanners over a drafted reply, under a surface overlay
that carries the chat-specific rules, with one verdict line and an exit code.

    replycheck.py -                          # the reply on stdin
    replycheck.py draft.md                   # or a file
    replycheck.py --surface assistant-chat - # the default surface
    replycheck.py --json -                   # machine-readable
    replycheck.py --strict -                 # warnings fail too
    replycheck.py --no-structure -           # voicelint only
    replycheck.py --question q.txt draft.md  # scale the length budget to the question

Length is advisory. The surface's ``length_budget`` sets a prose word budget
(code masked), scaled to the question when one is given; a reply over it gets
an advisory line and never a FIX, because a full printout the author asked for
is sometimes long and must not be cut to pass.

Verdict: PASS when there is no error-level finding (or no warning under
--strict), else FIX. Exit 0 on PASS, 1 on FIX, 2 when the check could not run.
The recipe for the assistant (docs/reply-preflight.md): draft the reply to a
file, run this, revise while it says FIX, bound the attempts, send the exact
buffer that passed, and never treat a check that failed to run as a pass.

Surfaces resolve through pherkad.py (a user surfaces.json first, then
surfaces/<name>.json beside this script), or --surface may be a path. The overlay is merged onto the shipped voice_config.json by voicelint's
own loader, so nothing here restates a rule. Structural findings (structlint)
are advisory: they never change the verdict, because the structure checks
over-fire by design on short replies, and a checker that fails every terse
answer gets switched off.

Stdlib only.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import voicelint  # noqa: E402
import pherkad  # noqa: E402
import mdmask  # noqa: E402

SURFACES = os.path.join(HERE, "surfaces")
DEFAULT_SURFACE = "assistant-chat"


def surface_path(name: str) -> str:
    """The surface's overlay path, through pherkad's resolution (user map first,
    then the shipped surfaces/<name>.json). An unknown surface is an error."""
    info = pherkad.resolve_surface(name)
    if not info["overlay"]:
        sys.stderr.write(f"replycheck: surface '{name}' has no overlay\n")
        sys.exit(2)
    return info["overlay"]


_DIRECTIVE = re.compile(r"<!--(\s*)(voicelint|structlint)", re.IGNORECASE)
_BLOCKQUOTE = re.compile(r"(?m)^([ \t]{0,3})>[ \t]?")


def unshield(text: str) -> tuple[str, list[dict]]:
    """A reply the assistant wrote cannot exempt itself. Its voicelint and
    structlint directives are made inert and each is reported as an error,
    and its blockquote markers are dropped so quoted lines are linted like any
    other. To mention a banned phrase, a reply quotes it in backticks, which
    stay masked, so a directive named in a code span or fence is not one."""
    findings = []
    live = list(_DIRECTIVE.finditer(mdmask.mask(text, ("code",))))  # same offsets, code blanked
    for m in live:
        line = text.count("\n", 0, m.start()) + 1
        findings.append({"line": line, "col": m.start() - (text.rfind("\n", 0, m.start()) + 1) + 1,
                         "severity": "error", "rule": "directive", "rule_id": "directive.in-reply",
                         "match": m.group(0), "engine": "voice",
                         "message": "a reply cannot carry a linter directive; it would exempt itself"})
    for m in reversed(live):
        text = text[:m.start()] + "<!--" + m.group(1) + "inert-" + m.group(2) + text[m.end():]
    return _BLOCKQUOTE.sub(r"\1", text), findings


_WORD = re.compile(r"[A-Za-z0-9][\w'’-]*")


def prose_words(text: str) -> int:
    """Words a reader has to read: code spans and fences are masked out."""
    return len(_WORD.findall(mdmask.mask(text, ("code",))))


def length_check(text: str, budget: dict | None, question: str | None) -> dict | None:
    """The reply's prose word count against the surface's advisory budget.
    None when the surface sets no budget. Never part of the verdict."""
    if not budget:
        return None
    words = prose_words(text)
    if question is None:
        limit, q = int(budget.get("default", 250)), None
    else:
        q = prose_words(question)
        limit = min(int(budget.get("max", 600)),
                    int(budget.get("base", 150)) + int(budget.get("per_question_word", 4)) * q)
    return {"words": words, "budget": limit, "question_words": q, "over": words > limit}


def length_note(length: dict | None) -> str | None:
    if not length or not length["over"]:
        return None
    basis = f"a {length['question_words']}-word question" if length["question_words"] is not None else "no question given"
    return f"length: {length['words']} words against a budget of {length['budget']} ({basis}); cut the wrapper, keep the work"


def check_reply(text: str, surface: str = DEFAULT_SURFACE, structure: bool = True, cwd: bool = True,
                question: str | None = None) -> dict:
    """Run both scanners over ``text`` and return the result as a dict:
    surface, verdict, errors, warnings, findings (voicelint), structure (structlint),
    length (the advisory word budget, or None when the surface sets none).
    ``question`` is the message being answered; the budget scales with it.
    cwd=False ignores a surfaces.json in the working directory (the Stop hook)."""
    cfg, info = pherkad.load_layers(surface, None, cwd=cwd)
    length = length_check(text, (info or {}).get("length_budget"), question)
    shield_findings = []
    if (info or {}).get("speaker") == "assistant":
        text, shield_findings = unshield(text)
    # One run of both engines (pherkad.run_text), then split by engine: the
    # voice findings decide the verdict, the structural ones are advisory.
    # A reply is short, so the combined density never applies and is dropped.
    all_findings, suppressed = pherkad.run_text(text, cfg, structure=structure)
    findings = shield_findings + [f for f in all_findings if f["engine"] == "voice"]
    structural = [f for f in all_findings if f["engine"] == "structure"]
    errors = sum(f["severity"] == "error" for f in findings)
    warnings = sum(f["severity"] == "warning" for f in findings)
    return {
        "surface": surface,
        "errors": errors,
        "warnings": warnings,
        "suppressed": suppressed,
        "findings": findings,
        "structure": structural,
        "length": length,
    }


def verdict(result: dict, strict: bool = False) -> str:
    if result["errors"] or (strict and result["warnings"]):
        return "FIX"
    return "PASS"


def render(result: dict, strict: bool = False) -> str:
    lines = []
    for f in result["findings"]:
        lines.append(f"{f['line']}:{f['col']} [{f['severity']}] {f['rule_id']}: {f['message']}  ->  {f['match']!r}")
    for f in result["structure"]:
        lines.append(f"{f['line']}:{f['col']} [advisory] {f['rule_id']}: {f['message']}  ->  {f['match']!r}")
    note = length_note(result.get("length"))
    if note:
        lines.append(f"[advisory] {note}")
    v = verdict(result, strict)
    n_struct = len(result["structure"])
    tail = f", {n_struct} structural advisory" if n_struct else ""
    lines.append(f"replycheck: {v} ({result['errors']} error(s), {result['warnings']} warning(s){tail}; "
                 f"surface {result['surface']})")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Preflight an assistant reply against the voice rules.")
    ap.add_argument("file", help="the drafted reply, or - for stdin")
    ap.add_argument("--surface", default=DEFAULT_SURFACE, help="surface name under surfaces/, or a path (default: assistant-chat)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="warnings make the verdict FIX")
    ap.add_argument("--no-structure", action="store_true", help="skip the structural (advisory) checks")
    ap.add_argument("--question", help="the message being answered, as text or a file path; scales the length budget")
    args = ap.parse_args(argv)

    try:
        text = voicelint.read_source(args.file, False)  # the reader the linter uses, HTML included (I102)
    except OSError as exc:
        sys.stderr.write(f"replycheck: {exc}\n")
        return 2
    question = args.question
    if question is not None and os.path.isfile(question):
        with open(question, encoding="utf-8", errors="replace") as fh:
            question = fh.read()

    result = check_reply(text, args.surface, structure=not args.no_structure, question=question)
    result["verdict"] = verdict(result, args.strict)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render(result, args.strict))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # a crash must not look like a verdict
        sys.stderr.write(f"replycheck: unexpected error: {exc}\n")
        sys.exit(2)
