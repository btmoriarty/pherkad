# Codex feature pass on 0.5.17, Astra, 2026-09-16

The fourth attempt, and the first to finish: `codex exec --sandbox read-only -m gpt-6-astra` at `ultra` (codex-cli 0.154.0) against `d9e850a` (0.5.17), 62,840 tokens. The prompt was narrowed to five files and four questions after two attempts had run out of usage while reading (`docs/codex-features-astra-2026-09-15-second-pass.md`). The prompt is at the end.

Ranked by expected value to this author per day of work:

1. **Generate a complete judgment packet.** `SKILL.md:65` leaves context assembly manual; add `pherkad.py review-pack --surface …` producing JSON and a prompt containing resolved guidance, approved excerpts, applicable profile files, findings, and source hashes, reusing `load_layers`. **1 day; low noise risk**, chiefly from including irrelevant profile material.

2. **Detect repeated title frames.** `structlint.py` checks individual heading patterns and interrogative rate but cannot collect recurring syntactic templates; add `check_document(units, surface, config)`, backed by a small `docunits.py` representation of titles, bodies, and notes. **2 days; medium noise risk**, controlled through aggregate advisory findings and surface-specific thresholds.

3. **Turn corpus counts into labeled calibration.** `corpusscan.py` now counts both engines by surface, but raw frequency cannot establish usefulness; add `review` and `score-review` commands exporting sampled hits and unflagged units as JSONL `{surface, rule_id, path, source_hash, span, label}`, then reporting precision and missed constructions by surface. **1 to 2 days; low added noise risk**, with sampling bias the main limitation; reuse existing contexts, stable IDs, and detect’s precision calculations.

4. **Persist judgment findings and their dispositions.** `SKILL.md:66` assigns generic `judgment` references, while `pherkad.py decide` requires a mechanical finding; add `review-import` for `{rule_ref, evidence_spans, context_hash, disposition, rationale}`, with stable judgment-family IDs and invalidation against the complete evidence scope. **2 days; medium noise risk** from carrying an old judgment into changed context; reuse the decision store and correction ledger’s rationales.

5. **Execute detection runs resumably.** `eval/detect.py:220` delegates every prompt and returned JSON to the operator; add `study.py run --jobs N` with per-blind-ID status, response validation, retries, and prompt/model hashes, reusing the manifest and verdict loader. **1 day; no additional linguistic noise**, provided separate repeats remain separate executions.

For the deck findings, I would implement the following:

- **Repeated frames:** In `structlint`, recognize explicit templates such as `^.+,\s*not\s+.+$`, `^The one thing that .+$`, and `^What .+ gets wrong\b.*$`, case-insensitively, with nonempty slots. Start with **three matching titles comprising at least 20% of eligible titles, or five matching titles regardless of share**; these are proposed thresholds requiring deck calibration, not measured cutoffs. Count title units, not matches within a title. Under `slides`, consume explicit slide boundaries and title/body/notes roles; under prose surfaces, compare headings at the same level. Reuse Markdown masking, but require a documented extraction convention rather than assuming every heading starts a slide. Report one advisory `{scope:"document", frame_id, hits, total, related_locations:[{unit_id,line,text}]}`, quoting the titles together and excluding it from density. Decisions must hash **all eligible titles**, since changing the denominator can change the finding.

- **Presenter narration:** Keep the fault decision in judgment. “Show what comes back” can be a legitimate student instruction; neither the imperative nor “we” establishes presenter narration. A slides-only collector can surface sentence-initial `we + read/show/look at` and imperatives such as `show + what comes back`, with **one occurrence sufficient for review**. Run it over student-facing bodies, exclude notes/code/quotations, and report the slide title, body quotation, and audience metadata as an uncounted cue. The judgment asks whose action the sentence describes and whether that instruction belongs on the student’s slide.

Three remaining weaknesses:

- **Document findings still receive paragraph decisions.** [structlint.py:404](skills/pherkad/tools/structlint.py:404) anchors the heading-rate finding to its first interrogative heading, while [pherkad.py:265](skills/pherkad/tools/pherkad.py:265) treats every structural finding as paragraph-scoped. Accepting that warning can therefore survive edits to other headings that substantially change the rate; the 0.5.17 paragraph fix does not cover this case. Findings need explicit scope and complete evidence locations.

- **Structural rule hashes do not identify their implementation.** [pherkad.py:276](skills/pherkad/tools/pherkad.py:276) hashes the rule’s `pattern`, but structural patterns are descriptive labels supplied at [pherkad.py:405](skills/pherkad/tools/pherkad.py:405). Changing a header regex or the parallelism algorithm without changing those labels or thresholds leaves accepted decisions valid. Give each structural rule an explicit semantic revision and hash its relevant parameters.

- **Overlay fixtures establish isolated matching, not effective behavior.** [pherkad.py:665](skills/pherkad/tools/pherkad.py:665) removes competing list rules before testing examples. A candidate can pass its fixtures yet disappear behind another rule when the actual configuration resolves overlapping findings. Retain those unit fixtures, but add effective-stack cases asserting the surviving rule ID and severity under base, surface, and project overlays.

For detection, my practical minimum would be **eight independent held-out pieces on one surface**, including one atypical piece, one content-preserving flattening of each, four matched impostors, and two legitimate override pieces: **22 cases**. Supply one decoy profile, freeze the target profile and judging settings, and run:

```bash
python3 eval/study.py plan author-pilot --task detect \
  --writers author --surface post \
  --conditions correct,wrong,shuffled,none,linter --repeats 3
```

That requires **264 model judgments**; the linter condition is automatic. Obtain blind human pair judgments and freeze exclusion rules before scoring. Include the surface explicitly in the frozen judging prompt: the current prompt construction at [detect.py:211](eval/detect.py:211) supplies profile and passage only.

Report the paired discrimination lift over controls with a source-level bootstrap interval, authentic acceptance, flattened/impostor acceptance, and severe verdict movement across repeats. Label it an exploratory result for this author and surface; the independent sample size is eight source documents, not the number of judgments.

The principal operational obstacle is the manual prompt/JSON round trip at [detect.py:220](eval/detect.py:220): hundreds of individual handoffs make even this pilot unnecessarily laborious.


## The prompt

You are reviewing the repository at /Users/moriarty/Documents/kochab/pherkad, read-only. Do not modify files. Do not run the test suites (they need a writable temp dir your sandbox lacks); they pass. Two earlier attempts at this review ran out of budget while reading, so READ ONLY THESE, in this order, and then write: CHANGELOG.md (0.5.1 through 0.5.17 shipped on 2026-09-15 and 16), skills/pherkad/tools/pherkad.py, skills/pherkad/tools/structlint.py, skills/pherkad/SKILL.md, and docs/codex-features-astra-2026-09-15-second-pass.md (what the two failed attempts found, all fixed). Skim other files only if a specific question needs one line from them.

Context: a writing-voice toolkit for one author. voicelint (phrase rules with stable ids), structlint (shape checks: two-beat parallel, staccato run, posed heading, aphorism, interrogative-heading rate), mdmask (shared Markdown reading), pherkad.py (combined runner, one schema, density over counted findings, surfaces, per-occurrence decision file, release manifest, overlay check), replycheck (assistant-reply preflight plus a Claude Code Stop hook, in use), corpusscan (per-rule corpus counts, candidate trials, release diffs, both engines, surfaces), corrections (a ledger: add / trial / promote to a tested rule with fixtures and generated prose), eval/study.py (author, revise, detect tasks with provenance and preregistration). A downstream fiction corpus (202 files, 275k words) is the calibration corpus. Yesterday the tools ran on two real lecture decks under the slides surface: the mechanical layer found nothing on either; the model's judgment pass found on both a recurring "X, not Y" antithesis frame across five or six slide TITLES, and presenter narration ("We read what comes back", "Show what comes back") on student-facing slides. Both decks were fixed at the source.

Report, tersely, in this order:

1. The next five features, ranked by value to this author per day of work. Each: two sentences, the gap in a named file, a design sketch (interface, data shape, where it lives, what it reuses), effort in days, noise risk.
2. The two judgment findings from the decks. Design a document-level checker for cross-unit repetition of a frame (the same syntactic template across headings or slide titles: "X, not Y", "The one thing that ...", "What X gets wrong") and for presenter narration in slide bodies, or say why each should stay judgment. Be concrete: the pattern, the threshold, where it lives (structlint or a new module), how it takes a surface, what it reports.
3. Three things weak or wrong in what shipped. Cite file and line. Prefer a design that will not scale, a schema that will need to change, or a test that proves less than it seems to.
4. The smallest run of eval/study.py --task detect that would produce a number worth reporting for this one author, and the one thing in the harness that would make it harder than it should be.

Under 1,200 words. No praise. Do not restate what the project does.
