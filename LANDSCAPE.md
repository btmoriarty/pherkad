# Landscape: pherkad's outbound gate and edit-capture loop

Scan date: 2026-11-12. A late scan: pherkad itself (voicelint, structlint, replycheck, the
corrections ledger, the measured profile) was already built when this was written, and the
repository had no LANDSCAPE.md, so for those parts the decision confirms, redirects, or ends
further investment rather than gating a first build. The two new components, the outbound gate
and the edit-capture loop, have no design doc or code yet, and for them this scan is the gate.
Reported numbers below are the authors' own unless a line says they were verified here.

## Core function

The gate takes a piece of prose an AI assistant is about to send or save (an email, a chat
message, a document edit, a published page, a prose file, a slide deck), checks it against one
person's written style rules, and refuses the send with the reasons when a rule is broken.

The capture loop takes the assistant's draft and the text the person actually sent or
committed, finds the phrases the person changed, and records each change as a candidate rule
that the person approves or retires.

Alternate phrasings searched: "lint outbound messages against a style guide before sending",
"guardrail that validates LLM output against banned phrases", "brand voice enforcement hook",
"learn writing preferences from user edits to AI drafts", "AI email assistant that learns from
your sent folder".

## Comparable systems

- Voice-and-tone hooks for Claude Code (Tom Howard). https://dev.to/tompahoward/enforcing-voice-and-tone-with-claude-code-hooks-6db.
  A blog post with the configuration in a public repository, github.com/windyroad/windyroad, 2026.
  What it does: four Claude Code hooks lock edits to a website's copy files until a read-only
  reviewer subagent has checked them against a `VOICE-AND-TONE.md` file. A PreToolUse hook on
  Write and Edit denies the call with `permissionDecision: "deny"` until a marker file exists, a
  PostToolUse hook on the reviewer agent creates the marker, and a Stop hook removes it so every
  turn starts locked.
  Reported results: the author reports the review adds 10 to 30 seconds per turn (reported, not
  verified). No accuracy figures.
  Draw from: the deny-with-reason JSON at the PreToolUse boundary, and the idea that the gate
  scopes itself by path so it never touches code files.
  Falls short: it gates only Write and Edit on one site's copy directories, never email, chat,
  documents or decks; the check is a model reviewer rather than a rule engine, so it is slow and
  not repeatable; it has no ledger and does not learn from the author's edits.

- Vale. https://vale.sh and https://github.com/vale-cli/vale. Open-source prose linter, Go,
  mature, used for documentation style at Datadog, Elastic and others.
  What it does: lints Markdown, HTML and other markup against YAML style packages (Microsoft,
  Google, write-good, proselint, or a house style), with severities, and runs in a GitHub Action
  that comments on changed lines or in a pre-commit hook.
  Reported results: none as accuracy. Datadog and Elastic describe adoption in their docs
  pipelines (reported, not verified). One guide (buildwithfern.com, 2026) recommends promoting a
  rule to error only when it has no false positives on the existing docs.
  Draw from: the rollout rule (a rule becomes an error only after it is clean on the current
  corpus), which pherkad already follows with `corpusscan.py diff`; and lint only the changed
  lines, which the gate adopts for Edit and Write.
  Falls short: it runs at commit or CI time on files in a repository, never at the moment an
  agent sends an email or a Slack message; it has no notion of a per-person profile or surfaces;
  replacing voicelint with it would be a rewrite of a tested engine for no new capability.

- Writer (writer.com) and Acrolinx. https://writer.com/product/chrome-extension and
  https://www.acrolinx.com/product/. Commercial content-governance platforms.
  What it does: an organisation's style guide and terminology (approved, pending, disallowed
  terms) are checked wherever people write. Writer's browser extension covers Gmail and Slack on
  the web and scores compliance in a sidebar; Acrolinx ships an Outlook add-in and describes
  automated checks and quality gates at save, import and publish in a content system.
  Reported results: Acrolinx markets "100% compliance before any content is released"
  (vendor claim, not verified). No independent figures found.
  Draw from: the coverage principle, which is the gate's whole premise: a style rule is only
  enforced if every surface where text leaves is checked. Writer's three term states map onto
  the ledger's pending, promoted and retired.
  Falls short: built for a team's brand style typed by people, not one person's voice produced
  by an agent; the checks sit in human editors, not at an agent's tool boundary; both are cloud
  services, and drafts to Heron fellows and FAccT review text may not leave the Mac.

- Guardrails AI validators. https://guardrailsai.com/hub/validator/guardrails/ban_list. An
  open-source framework for validating LLM output, with a hub of validators.
  What it does: validators run over a model's output inside an application; the Ban List
  validator matches listed words with fuzzy matching (Levenshtein distance 1 by default), and
  each validator has an on-fail policy such as raise, reask, fix or no-op.
  Reported results: none reported.
  Draw from: the explicit on-fail vocabulary, which frames the design question this gate has to
  answer for its own failures (fail open with a logged warning, or fail closed).
  Falls short: it wraps a model call inside an application the developer owns; it cannot see an
  assistant's tool calls in a harness, and it has no personal profile or learning.

- PRELUDE and CIPHER (Gao, Taymanov, Salinas, Mineiro, Misra). https://arxiv.org/abs/2404.15269
  and https://github.com/gao-g/prelude. NeurIPS 2024 paper with MIT-licensed code.
  What it does: learns a user's latent writing preference from their edits to an agent's drafts.
  CIPHER asks a model to describe the preference behind each edit, retrieves the descriptions
  from the most similar past contexts, and conditions the next draft on them, with no
  fine-tuning.
  Reported results: on summarisation and email-writing tasks with a GPT-4 simulated user, CIPHER
  had the lowest cumulative edit distance of the methods compared and shorter prompts than
  methods that replay raw edits (reported, not verified).
  Draw from: edit distance between the draft and what was sent as the measure of whether the
  loop is working, which the daily counts can report per surface; and the per-context retrieval
  idea for the later judgment-layer check.
  Falls short: the learned preference is a model-written description applied silently; there is
  no rule, no trial on a corpus, and no approval step, and the evaluation uses a simulated user.

- Email assistants that learn from the sent folder: Fyxer, alfred_, Spark "My Writing Style",
  Superhuman. https://docs.fyxer.com/using-fyxer/work-with-drafts and
  https://get-alfred.ai/blog/ai-that-drafts-emails-in-my-voice. Commercial products.
  What it does: the assistant drafts replies, watches what the person sends, and adapts future
  drafts. Fyxer's documentation says light edits teach it and full rewrites do not; alfred_
  describes tracking whether a draft was sent as-is, edited or rewritten.
  Reported results: Fyxer claims to have doubled the number of drafts sent without edits (vendor
  claim, not verified).
  Draw from: the pairing rule (a heavily rewritten draft yields nothing to learn, so only pairs
  above an overlap floor are mined, which `corrections.py mine` already does with its 0.6
  whole-sentence threshold), and the three outcomes (sent as-is, edited, rewritten) as the
  capture loop's per-draft label.
  Falls short: the learning is opaque and cloud-side, the person never approves a rule, and none
  of them checks text the assistant writes outside their own email client.

Also seen: brand-voice-check, a PostToolUse hook on .md and .mdx writes described in a
promotional post (https://dev.to/raxxostudios/why-i-run-claude-code-plugins-for-brand-voice-enforcement-m8k),
with no code published, so not distinct from the Howard entry. Generic AI-phrase linters,
llmstrip (https://github.com/HugoLopes45/llmstrip), cfregly/claude-deslop, slopless (npm) and
defluff (PyPI), which ship fixed lists of generic AI vocabulary and are not distinct from
voicelint's shipped defaults. Grammarly's personalised voice profile
(https://support.grammarly.com/hc/en-us/articles/23153676821773-Introducing-voice-features),
which adapts suggestions to a detected profile, not distinct from the email assistants above.

## Evidence on the function

PRELUDE (above) is the only controlled evaluation found of learning from edits, and it uses a
simulated user. No study was found that measures whether a style gate at the send boundary
reduces the edits a person makes afterwards. The Vale rollout guidance (promote a rule only when
it is clean on the corpus) is practitioner advice, not a measurement. Verdict: the function is
plainly doable as rule matching; whether it reduces Brian's corrections is unmeasured anywhere,
so the gate has to measure it itself, which is what the daily counts are for.

## Venue or official-tool check

The gate touches four systems.

Claude Code (the harness) ships the mechanism and nothing more. Its hooks reference
(https://code.claude.com/docs/en/hooks) documents PreToolUse matchers as unanchored regular
expressions over tool names, including MCP tools named `mcp__<server>__<tool>`, and a deny
decision printed as `hookSpecificOutput.permissionDecision: "deny"` with a reason; the default
command timeout is 600 seconds. No official voice or style gate exists.

Claude's own styles feature (https://claude.com/blog/styles and
https://support.claude.com/en/articles/10181068) builds a custom style from uploaded writing
samples. It shapes generation and is advisory; it checks nothing at send time and keeps no
ledger. The desktop app's output style (the Brief style in use here) is the same kind of control.

Gmail and Slack ship drafting help but no style gate for their API or connector senders; the
only style enforcement found in those clients is third party (Writer's extension, above). Google
Docs and Drive have no outbound check on API writes.

## Crowded-space verdict

Style enforcement for human writers is a crowded commercial space (Writer, Acrolinx, Grammarly)
with a mature open-source linter (Vale). Learning a writer's style from their edits is an active
research topic (PRELUDE) and a feature of several email assistants. Enforcement at an AI
assistant's tool boundary is thin: one blog-post configuration (Howard) gates file edits with a
model reviewer. A new entrant will be compared against Vale, Writer, and the Howard hooks.

## Differentiation decision

Decision: EXTEND EXISTING, per component.

| Component | Decision | What is extended, and with what |
|---|---|---|
| Outbound gate | Extend pherkad (replycheck's engine and surfaces) with a PreToolUse hook | Claude Code's PreToolUse deny, as Howard uses it, over every sending tool rather than file edits only, with voicelint rules instead of a model reviewer |
| Draft log | Extend pherkad | A JSONL log of every gated text, kept on the Mac |
| Edit capture | Extend `corrections.py mine` | A nightly pairing job; the pairing floor and the sent-as-is, edited, rewritten label come from the email assistants, the edit-distance measure from PRELUDE |
| Sent-mail reader | Build, small | No comparable reads one person's sent mail into a local diff without a cloud service; stdlib IMAP or the Gmail API, decided in the design |
| Approvals and counts | Extend the overnight daily report | Two sections of an existing page |
| Deck check | Extend pherkad with a slide-text extractor | Stdlib reading of the .pptx zip (slide and notes XML) and of HTML decks, so pherkad stays dependency-free |
| Judgment-kind check (later) | Undecided | Candidates are a model check on outbound sends and CIPHER-style retrieval of past corrections; scanned again before it is designed |

Adopting Vale was considered and rejected: it would replace a tested engine that already carries
surfaces, a corpus count, a measured profile and a corrections ledger, and it would still need
the same hook, log and capture loop built around it. Adopting Writer or Acrolinx fails the
privacy constraint and checks people, not an agent.

Rationale: every piece of the function already exists somewhere except the combination this
needs, which is one person's rules enforced at every point where an agent's prose leaves a
session, with that person's own edits feeding approved rules back into the same gate. The
engine, ledger and report are in hand, so the work is integration. This decision would change if
Claude Code or the connectors shipped an official outbound content check that could run local
rules, or if the daily counts show after a month that blocked texts are not reducing Brian's
corrections.

## Datasets and sources to reuse

- The corrections ledger, `/Users/moriarty/code/session-hygiene/voice/corrections.jsonl`: 20
  records since 2026-09-27, the gold set for whether the gate would have caught each one.
- The saga reference corpus used for every rule change (`corpusscan.py diff`), unchanged.
- PRELUDE's code and task setup, https://github.com/gao-g/prelude, for the edit-distance
  measure on email drafts.

## Search record

Run 2026-11-12 with web search:

- Claude Code PreToolUse hook lint outbound email Slack message style guide block
- Claude Code hook voice style check before sending Gmail draft MCP tool anti-slop
- Vale prose linter style guide enforcement pre-commit CI
- Acrolinx content governance checks style guide in email Outlook browser before publish
- Writer.com style guide terminology rules enforcement Chrome extension Slack Gmail
- Grammarly style guide team enforcement learns from user edits personalized voice 2026
- open source tool detect AI slop phrases in writing linter "delve" banned words
- Guardrails AI output validator hub reject LLM output custom validator tone banned phrases
- learning latent preference from user edits LLM agent PRELUDE CIPHER arxiv
- compare AI draft to sent email edits learn writing preferences tool
- Claude custom styles upload writing samples match your writing style announcement

Pages opened: the Howard post, the RAXXO post, the PRELUDE repository, and the Claude Code hooks
reference. TrueVoice MCP (claudemarket.ai) returned HTTP 429 and debabble's PyPI page returned a
browser challenge, so neither is catalogued.
