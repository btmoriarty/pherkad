#!/usr/bin/env python3
"""gate: the outbound voice gate, a Claude Code PreToolUse and PostToolUse hook.

Prose leaves a session through tools: an email draft, a Slack message, a Google
Doc, a published artifact, a prose file. This hook runs pherkad over the text a
tool call is about to send or save, under the surface that fits it, and denies
the call when an error-level rule fires, with the findings as the reason, so the
assistant revises and calls again. Design: docs/outbound-gate.md.

    gate.py --config /path/to/gate.json        # as the hook command; payload on stdin
    gate.py --config F --explain TOOL JSON     # what would be checked, for a payload by hand

What it checks, by tool (matched on the tool-name suffix, so a reconnected
connector with a new server id is still caught):

    Gmail   create_draft update_draft send_message reply forward   subject + body   email
    Slack   slack_send_message slack_send_message_draft
            slack_schedule_message                                 message          email
            slack_create_canvas slack_update_canvas                title + content  post
    Drive   create_file update_file                                textContent      post
    Docs    update_doc                                             inserted text    post
    Claude docs connector create update batch (mapped servers only)  body strings   post
    Artifact publish                                               the file's text  post
    Write Edit MultiEdit on a gated path                           added lines only by path

Only added lines are checked on Write and Edit, so a session is never blocked for
text the author wrote earlier. Headless runs (CLAUDE_CODE_ENTRYPOINT=sdk-cli) are
not gated on file writes; sends are gated in every run.

Bounded: a target denied twice within 15 minutes gets ``ask`` on the third call,
so the author decides in the permission dialog instead of the assistant
rewriting a false positive forever.

Fails open (the author's decision, 2026-11-12): a missing config, a broken
overlay or a crash lets the call through with a visible systemMessage and a log
line. Every gated call is logged, text included, to ``<log_dir>/gate-log.jsonl``;
PostToolUse adds what the tool returned (draft id, thread id, message ts) so the
nightly capture can find what was eventually sent.

The config (``gate.json``, kept outside this repository) holds the log folder,
the server-id map, the path rule and the private markers. See
``examples/gate.example.json``.

Stdlib only.
"""
from __future__ import annotations
import fnmatch
import html as htmlmod
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

GMAIL = ("create_draft", "update_draft", "send_message", "reply", "forward")
SLACK_MSG = ("slack_send_message", "slack_send_message_draft", "slack_schedule_message")
SLACK_CANVAS = ("slack_create_canvas", "slack_update_canvas")
DRIVE = ("create_file", "update_file")
GDOCS = ("update_doc",)
GENERIC = ("create", "update", "batch")
FILE_TOOLS = ("Write", "Edit", "MultiEdit")
ESCALATE_AFTER = 2
ESCALATE_WINDOW = 15 * 60


# --- config -------------------------------------------------------------------------------

def load_config(path: str | None) -> dict:
    path = path or os.environ.get("PHERKAD_GATE_CONFIG")
    if not path:
        raise RuntimeError("no gate config (pass --config or set PHERKAD_GATE_CONFIG)")
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    if not cfg.get("log_dir"):
        raise RuntimeError(f"{path} has no log_dir")
    cfg["_path"] = path
    return cfg


def log_path(cfg: dict) -> str:
    return os.path.join(cfg["log_dir"], "gate-log.jsonl")


def append_log(cfg: dict, entry: dict) -> None:
    os.makedirs(cfg["log_dir"], exist_ok=True)
    with open(log_path(cfg), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def recent_log(cfg: dict, max_bytes: int = 400_000) -> list[dict]:
    p = log_path(cfg)
    if not os.path.exists(p):
        return []
    with open(p, "rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - max_bytes))
        data = fh.read().decode("utf-8", "replace")
    out = []
    for line in data.splitlines()[1 if size > max_bytes else 0:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def is_private(cfg: dict, *texts: str) -> bool:
    priv = cfg.get("private") or {}
    blob = "\n".join(t for t in texts if t)
    low = blob.lower()
    if any(w and re.search(r"\b" + re.escape(w) + r"\b", blob) for w in priv.get("words", [])):
        return True
    return any(s and s.lower() in low for s in priv.get("paths", []) + priv.get("recipients", []))


# --- the path rule ------------------------------------------------------------------------

def path_rule(cfg: dict, path: str) -> dict | None:
    """None when the file is not gated, else {'surface', 'config'} (config: an overlay that
    replaces the surface, for the saga)."""
    rule = cfg.get("paths") or {}
    path = os.path.abspath(path)
    ext = os.path.splitext(path)[1].lower()
    if ext not in rule.get("extensions", [".md", ".txt", ".html", ".htm", ".eml"]):
        return None
    base = os.path.basename(path)
    if base in rule.get("exclude_names", []):
        return None
    for pat in rule.get("exclude", []):
        if fnmatch.fnmatch(path, pat):
            return None
    for route in rule.get("routes", []):
        if path.startswith(route["prefix"]):
            return {"surface": route.get("surface"), "config": route.get("config")}
    if base.lower() == "readme.md":
        return {"surface": "technical", "config": None}
    for root in rule.get("include_roots", []):
        if path.startswith(root):
            return {"surface": rule.get("default_surface", "post"), "config": None}
    code_root = rule.get("code_root")
    if code_root and path.startswith(code_root):
        segs = path[len(code_root):].split(os.sep)[:-1]
        if any(s in rule.get("code_folders", []) for s in segs):
            return {"surface": rule.get("default_surface", "post"), "config": None}
    return None


def read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def added_lines(old: str, new: str) -> str:
    seen = {ln.strip() for ln in old.splitlines() if ln.strip()}
    return "\n".join(ln for ln in new.splitlines() if ln.strip() and ln.strip() not in seen)


# --- what a tool call carries -------------------------------------------------------------

def html_text(s: str) -> str:
    s = re.sub(r"<(script|style)\b.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", s, flags=re.I)
    return htmlmod.unescape(re.sub(r"<[^>]+>", " ", s))


def _split_mcp(name: str) -> tuple[str, str] | None:
    m = re.match(r"^mcp__(.+?)__(.+)$", name)
    return (m.group(1), m.group(2)) if m else None


def _strings_under(obj, keys=("text", "content", "markdown", "body", "title", "replaceText")) -> list[str]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and k in keys:
                out.append(v)
            else:
                out.extend(_strings_under(v, keys))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_strings_under(v, keys))
    return out


def classify(cfg: dict, tool: str, inp: dict) -> dict | None:
    """What this call sends: {'kind', 'surface', 'config', 'target', 'recipients', 'text'}, or
    None when the call is not gated."""
    inp = inp or {}
    if tool in FILE_TOOLS:
        if os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "sdk-cli":
            return None
        path = inp.get("file_path") or ""
        rule = path_rule(cfg, path) if path else None
        if not rule:
            return None
        if tool == "Write":
            old = ""
            if os.path.exists(path):
                try:
                    old = read_text(path)
                except OSError:
                    old = ""
            text = added_lines(old, inp.get("content") or "")
        elif tool == "Edit":
            text = added_lines(inp.get("old_string") or "", inp.get("new_string") or "")
        else:
            text = "\n".join(added_lines(e.get("old_string") or "", e.get("new_string") or "")
                             for e in inp.get("edits") or [])
        if os.path.splitext(path)[1].lower() in (".html", ".htm"):
            text = html_text(text)
        return {"kind": "file", "surface": rule["surface"], "config": rule["config"], "target": path,
                "recipients": [], "text": text}
    if tool == "Artifact":
        if (inp.get("action") or "publish") != "publish" or inp.get("asset") or not inp.get("file_path"):
            return None
        path = inp["file_path"]
        try:
            raw = read_text(path)
        except OSError:
            return None
        text = html_text(raw) if path.lower().endswith((".html", ".htm")) else raw
        return {"kind": "artifact", "surface": "post", "config": None,
                "target": inp.get("url") or path, "recipients": [], "text": text}
    sm = _split_mcp(tool)
    if not sm:
        return None
    server, name = sm
    mapped = (cfg.get("servers") or {}).get(server)
    if name in SLACK_MSG:
        return {"kind": "slack", "surface": "email", "config": None,
                "target": inp.get("channel_id") or "", "recipients": [inp.get("channel_id") or ""],
                "text": inp.get("message") or ""}
    if name in SLACK_CANVAS:
        parts = [inp.get("title") or "", inp.get("content") or ""]
        parts += [s.get("content") or "" for s in inp.get("sections") or [] if isinstance(s, dict)]
        return {"kind": "slack-canvas", "surface": "post", "config": None,
                "target": inp.get("canvas_id") or "", "recipients": [], "text": "\n\n".join(p for p in parts if p)}
    if name in GMAIL and mapped in (None, "gmail"):
        body = inp.get("body") or (html_text(inp["htmlBody"]) if inp.get("htmlBody") else "")
        subject = inp.get("subject") or ""
        rec = [r for k in ("to", "cc", "bcc") for r in (inp.get(k) or [])]
        return {"kind": "gmail", "surface": "email", "config": None,
                "target": inp.get("messageId") or inp.get("replyToMessageId") or inp.get("draftId") or subject,
                "recipients": rec, "text": (subject + "\n\n" + body).strip()}
    if name in DRIVE and mapped in (None, "drive"):
        text = inp.get("textContent") or ""
        mime = (inp.get("contentMimeType") or "").lower()
        if not text and inp.get("base64Content") and (mime.startswith("text/") or "markdown" in mime or "html" in mime):
            import base64
            try:
                text = base64.b64decode(inp["base64Content"]).decode("utf-8", "replace")
            except ValueError:
                text = ""
        if "html" in mime:
            text = html_text(text)
        if not text:
            return None
        return {"kind": "drive", "surface": "post", "config": None,
                "target": inp.get("fileId") or inp.get("title") or "", "recipients": [], "text": text}
    if name in GDOCS and mapped in (None, "gdocs"):
        texts = []
        for r in inp.get("requests") or []:
            if not isinstance(r, dict):
                continue
            if "insertText" in r:
                texts.append((r["insertText"] or {}).get("text") or "")
            if "replaceAllText" in r:
                texts.append((r["replaceAllText"] or {}).get("replaceText") or "")
        text = "\n".join(t for t in texts if t)
        if not text.strip():
            return None
        return {"kind": "gdocs", "surface": "post", "config": None,
                "target": inp.get("documentId") or "", "recipients": [], "text": text}
    if name in GENERIC and mapped == "claude-docs":
        text = "\n\n".join(_strings_under(inp))
        if not text.strip():
            return None
        return {"kind": "claude-docs", "surface": "post", "config": None,
                "target": json.dumps((inp.get("container") or {}).get("id") or ""), "recipients": [], "text": text}
    return None


# --- the check ------------------------------------------------------------------------------

def check_text(text: str, surface: str | None, override: str | None) -> list[dict]:
    import pherkad
    if override:
        cfg, _ = pherkad.load_layers(None, override, cwd=False)
    else:
        cfg, _ = pherkad.load_layers(surface or "post", None, cwd=False)
    findings, _ = pherkad.run_text(text, cfg, structure=False)
    return [{"line": f.get("line"), "col": f.get("col"), "rule_id": f.get("rule_id"),
             "severity": f.get("severity"), "match": f.get("match"), "message": f.get("message")}
            for f in findings if f.get("engine") == "voice"]


def _escalate(cfg: dict, tool: str, target: str, now: float) -> bool:
    if not target:
        return False
    n = 0
    for e in reversed(recent_log(cfg)):
        if e.get("type") != "gate":
            continue
        if now - e.get("t", 0) > ESCALATE_WINDOW:
            break
        if e.get("target") == target and e.get("tool") == tool:
            if e.get("verdict") == "block":
                n += 1
            elif e.get("verdict") in ("pass", "ask"):
                break
    return n >= ESCALATE_AFTER


def pre(cfg: dict, payload: dict) -> dict | None:
    tool = payload.get("tool_name") or ""
    item = classify(cfg, tool, payload.get("tool_input") or {})
    if not item or not item["text"].strip():
        return None
    t0 = time.time()
    findings = check_text(item["text"], item["surface"], item["config"])
    errors = [f for f in findings if f["severity"] == "error"]
    verdict = "pass"
    if errors:
        verdict = "ask" if _escalate(cfg, tool, item["target"], t0) else "block"
    entry = {"type": "gate", "t": t0, "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0)),
             "session": payload.get("session_id"), "tool_use_id": payload.get("tool_use_id"),
             "cwd": payload.get("cwd"), "tool": tool, "kind": item["kind"], "surface": item["surface"],
             "target": item["target"], "recipients": item["recipients"], "text": item["text"],
             "verdict": verdict, "findings": findings,
             "private": is_private(cfg, item["text"], item["target"], " ".join(item["recipients"])),
             "ms": int((time.time() - t0) * 1000)}
    append_log(cfg, entry)
    if verdict == "pass":
        return None
    lines = "\n".join(f"  {f['line']}:{f['col']} {f['rule_id']}: {f['match']!r}" for f in errors)
    label = item["surface"] or "saga"
    if verdict == "ask":
        reason = (f"voice gate ({label}): this text was refused twice in 15 minutes and still breaks "
                  f"{len(errors)} rule(s). Brian decides:\n{lines}")
    else:
        reason = (f"voice gate ({label}): {len(errors)} error(s). Revise the text and call the tool again; "
                  f"send only the corrected text:\n{lines}")
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": verdict if verdict == "ask" else "deny",
                                   "permissionDecisionReason": reason}}


def _ids(resp) -> dict:
    out = {}
    if isinstance(resp, str):
        try:
            resp = json.loads(resp)
        except json.JSONDecodeError:
            return out
    if isinstance(resp, list):  # MCP content blocks
        for b in resp:
            if isinstance(b, dict) and b.get("type") == "text":
                out.update(_ids(b.get("text")))
        return out
    if isinstance(resp, dict):
        for k in ("id", "threadId", "draftId", "messageId", "ts", "channel", "url", "viewUrl", "permalink", "canvas_id"):
            v = resp.get(k)
            if isinstance(v, (str, int)):
                out[k] = v
        for k in ("message", "draft", "result", "content"):
            if isinstance(resp.get(k), (dict, list, str)) and not out:
                out.update(_ids(resp[k]))
    return out


def post(cfg: dict, payload: dict) -> None:
    tool = payload.get("tool_name") or ""
    if tool in FILE_TOOLS or tool == "Artifact":
        return
    if not classify(cfg, tool, payload.get("tool_input") or {}):
        return
    append_log(cfg, {"type": "result", "t": time.time(), "tool_use_id": payload.get("tool_use_id"),
                     "session": payload.get("session_id"), "tool": tool, "result": _ids(payload.get("tool_response"))})


def _fail_open(cfg: dict | None, payload: dict, reason: str) -> int:
    tool = (payload or {}).get("tool_name") or "a tool call"
    print(json.dumps({"systemMessage": f"voice gate did not run on {tool}: {reason}; the text is unchecked"}))
    if cfg:
        try:
            append_log(cfg, {"type": "gate", "t": time.time(), "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                             "session": (payload or {}).get("session_id"), "tool": tool, "verdict": "error",
                             "error": reason})
        except OSError:
            pass
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cfg_path = None
    if "--config" in argv:
        cfg_path = argv[argv.index("--config") + 1]
    if "--explain" in argv:
        i = argv.index("--explain")
        cfg = load_config(cfg_path)
        print(json.dumps(classify(cfg, argv[i + 1], json.loads(argv[i + 2])), indent=2))
        return 0
    cfg = None
    payload: dict = {}
    try:
        payload = json.load(sys.stdin)
        cfg = load_config(cfg_path)
        if payload.get("hook_event_name") == "PostToolUse":
            post(cfg, payload)
            return 0
        out = pre(cfg, payload)
        if out:
            print(json.dumps(out))
        return 0
    except SystemExit as exc:  # a surface or overlay error inside pherkad
        return _fail_open(cfg, payload, f"surface or config error ({exc})")
    except Exception as exc:  # fail open, loudly (decision 1)
        return _fail_open(cfg, payload, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
