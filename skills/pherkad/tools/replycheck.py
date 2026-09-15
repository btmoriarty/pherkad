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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import voicelint  # noqa: E402
import pherkad  # noqa: E402

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


def check_reply(text: str, surface: str = DEFAULT_SURFACE, structure: bool = True) -> dict:
    """Run both scanners over ``text`` and return the result as a dict:
    surface, verdict, errors, warnings, findings (voicelint), structure (structlint)."""
    cfg, _info = pherkad.load_layers(surface, None)
    # One run of both engines (pherkad.run_text), then split by engine: the
    # voice findings decide the verdict, the structural ones are advisory.
    # A reply is short, so the combined density never applies and is dropped.
    all_findings, suppressed = pherkad.run_text(text, cfg, structure=structure)
    findings = [f for f in all_findings if f["engine"] == "voice"]
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
    args = ap.parse_args(argv)

    try:
        text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        sys.stderr.write(f"replycheck: {exc}\n")
        return 2

    result = check_reply(text, args.surface, structure=not args.no_structure)
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
