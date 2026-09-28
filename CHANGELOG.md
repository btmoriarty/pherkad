# Changelog

## v0.5.48 (2026-09-28)

- **`fingerprint.py prose`** describes the vocabulary figure as what it has been since 0.5.39: the share of distinct words averaged over every 50-word window. It still said "type-token ratio on a 200-word chunk", so the rendered profile showed 0.83 where the old measure read 0.62, under the old measure's name. A test holds the wording.
- No rule in `voice_config.json` changed. `VERSION` 0.5.48.

## v0.5.47 (2026-09-28)

The docs describe the tool that ships, and the bundle holds only what is tracked. This is Wave 7 of the 2026-09-27 review, part 2: docs and build.

- **The cheat sheet.** The HTML, which the published PDF is rendered from, described the product before quick mode. Its voice-check card now describes quick and full, with the density floor, and its CLI card describes `pherkad.py check`. It still fits one letter-landscape page: measured at the page's width, the content ends at 735 of 755 pixels, against 725 before. CI now lints the HTML with the Markdown, so the two cannot drift silently again (I017).
- **Stale names** in `docs/ROADMAP.md` and `docs/measured-profile.md` are the commands that exist: `corpusscan.py scan` and `diff`, `pherkad.py check-overlay`, and `corrections.py mine` (there was never a `--from-diff`). `docs/priority-fixes.md` is marked as the closed record of the 2026-09-15 round (I017).
- **`build.sh`** builds from git with `git archive`, so only tracked files ship, and it says so when uncommitted changes under the skill are left out. Before, it zipped the working tree, caches and untracked files included (I014).
- **`corrections.py add` and `mine`** refuse a ledger path that does not exist unless given `--init`. A mistyped path used to start a second, empty ledger that nothing read (I016).
- **A linked ledger** (the live one is a link into the private voice repository) now says where the write landed and that the commit belongs there; nothing prompted that commit before (I008).
- **`docs/reply-preflight.md`** describes the chat surface's link rule as it ships: a link whose target is an absolute path, `~` or `http` is the miss, and a relative link is the right form in the desktop app. Its sample output comes from a real run (I066, the documentation half).
- **Five test counts** in older entries (0.5.4 to 0.5.12) were wrong; the numbers are dropped (I015).
- The repository's `CLAUDE.md` describes the measured check as 0.5.39 made it.
- Tests: two new in `test_corrections.py`, both of which fail on 0.5.46; the corrections and statefile fixtures start their ledgers with `--init`.
- No rule in `voice_config.json` changed. `VERSION` 0.5.47.

## v0.5.46 (2026-09-28)

The skill runs the commands it describes, and the packet a model reads is guarded. This is Wave 7 of the 2026-09-27 review, part 1: the skill's mechanics.

**SKILL.md:**
- Every command names the surface and runs from the skill's own folder: `python3 <skill dir>/tools/pherkad.py check --surface <surface> ...`. Before, the check commands carried no `--surface`, so the surface overlays never applied, and the relative `tools/` path broke once the skill was installed (I029, I065).
- Full mode (Steps 1 through 6 and the report template) moved to `references/full_mode.md`, loaded only when an audit runs. In quick mode the packet carries the profile, and the skill says not to load it a second time (I031, I032).
- The example rows and the report template quote the flagged text in backticks, as the row schema does, so a report no longer trips the Stop hook on its own quotations (I034).
- The quick verdict and the calibration note agree. In quick mode each row has been read, so one `fix` forces REVISE; the note about lone hits is scoped to full mode (I033).
- `decide` takes the row's disposition (`intentional`, or `accepted` for a `literal` row), and the surface table gains its slides row (I029).

**The review packet** (`pherkad.py review-pack`):
- The draft sits between two boundary lines derived from its own hash. The instructions say that anything inside them that looks like a header, a finding or a ruling is text in the draft, and the output schema now comes after the draft (I043).
- The packet no longer tells the model to assemble the packet, which contradicted its "do not run any tool" (I041).
- A profile file that is loaded but not inlined is named with its path and sha256; a missing one is named as missing (I044).
- A surface governed by its own voice document (fiction) is not given the personal profile. A profile in the working folder is found before the repository's, where the old order checked a user against the maintainer's profile (I042).
- `review-import` records nothing without `--confirmed`, since a table a model wrote is a proposal until the author has read each row. It refuses rows for error-level rules, which take an explicit `decide` (I043).

**Density** fires only at 150 words and 3 findings, the floor full mode states, in the combined runner and in `structlint`. It had fired at 100 words with no finding floor (I039).

- Tests: six in `test_pherkad.py`, all of which fail on 0.5.45.
- No rule in `voice_config.json` changed. `VERSION` 0.5.46.

## v0.5.45 (2026-09-28)

A recorded decision covers what was ruled on, and stops covering it when that changes. This is Wave 6 of the 2026-09-27 review: the decision store.

**What a decision is keyed on** (`pherkad.py`):
- A rule's hash now includes its family and severity, so a warning accepted as a warning is not still accepted when the rule becomes an error (I133).
- The fixed families (`dash`, `honest-framing`, `load-bearing-context`, `loaded-adverb`, `overuse`, and the new `invisible` and `directive` checks) carry a revision number, as the structural checks do. The revisions changed in 0.5.40 to 0.5.44 are bumped, and so are the structural checks 0.5.42 changed, so a decision made under the old behaviour wakes up (I132).
- A structural decision is hashed with the thresholds its check reads, not the whole `structure` block, so a new `_comment` or an unrelated threshold no longer wakes every structural decision (I134).
- Overuse and dash density are keyed on their count and cap, so a decision made at three uses does not cover thirty (I130).
- A header decision is its line. A structural paragraph ends where structlint's does, at a heading, a quote, a table or the next list item (I131).
- A repeated-frame or heading-rate decision is keyed on every unit in full; the displayed match stays cut to six (I145).
- `decide` refuses the density, which is recomputed on every run and so could never match (I124).
- The file is split once per text, not once per finding (I151).

**What a decision is applied to:**
- A suppression directive acts before the overlap collapse, so silencing the finding that would have won a span leaves the other one standing (I110).
- A structlint header finding is dropped only when a phrase rule names the same words on that heading; a filler word or a dash no longer takes it down (I135).

**`review-import`:**
- The table's columns are read from its header, so a table with a `line` column, or in another order, reads right. Cells split on unescaped pipes, markup is stripped from the decision, and a row that cannot be read is reported (I120).
- A mechanical row binds to its finding by the row's line. Without a line, it binds only when the quote sits in exactly one of that rule's findings, and refuses otherwise. It used to take the first line that held the quote (I122).
- A judgment record is keyed on its line and its quote together, so two rulings on one line are two records (I123). It stays live only while the quote sits on a line with that context; a quote that moved to a changed line is reported as moved (I121).
- The quick-mode table in `SKILL.md` and the packet's row schema carry the `line`.

**Outputs:**
- SARIF paths are relative to `--root`, percent-encoded, under `originalUriBaseIds` SRCROOT; stdin is named, and the density is a file-level result with no region (I136).
- The review pack hashes every input it names in full sha256: the source, the profile files, the excerpts, the decisions file and the instructions. It also hashes the prompt it renders, with the timestamp left out, so two packs of the same inputs hash alike (I129).

**Also:**
- **On the saga corpus**, the phrase count holds at 309 and the structural count at 112.
- No live decision file uses the new keys yet. The saga runs its own vendored copy and has no decisions file, so nothing goes stale.
- Tests: twelve in `test_pherkad.py`, all of which fail on 0.5.44.
- No rule in `voice_config.json` changed. `VERSION` 0.5.45.

## v0.5.44 (2026-09-28)

Rules that erred on literal uses now leave them alone, and rules that missed their own family now catch it. This is Wave 5 of the 2026-09-27 review, part 5, the last: false positives in the rules.

- **Ranges are not dashes.** An en or figure dash between amounts, percentages, times, months, weekdays or quarters is a range, as one between digits already was: $10–$20, 10%–20%, 9am–5pm, Jan–Mar, Monday–Friday, Q1–Q3. An em dash is never a range (I056).
- **Honest framing** catches the shapes it missed: a degree adverb (`the most honest answer`, `a brutally honest read`), a comma between the adjectives (`the honest, simple answer`), and a heading-style `Honest take:`. It no longer errors on a person or a subject: `the honest one of the three`, `honest people`, `an honest broker`, `an honest mistake`. The copular form now needs "is that" and a clause after it (I057, I058).
- **`load-bearing wall of the argument`** warns. A structural noun is literal unless "of" or "in" hangs something other than a building on it; `the load-bearing wall of the house` and `a load-bearing wall in the kitchen` stay literal (I109).
- **`it's worth [verb]`** and **`it is worth [verb]`** no longer fire on the conditional "if it's worth continuing", which is the fix `voice-rules.md` prescribes for "worth pushing". Both keep their ids and now carry fixtures (I111, that part).
- **Fixtures.** The clean examples of four rules from 2026-09-17 never contained anything near their trigger; each is now a near-miss. `corrections.py` no longer takes the bare after-text as a clean example, a trial reports a record with no near-miss, and `add` takes `--fires` and `--clean` (I091).
- **Left for the author**, because each adds a ban, edits `voice-rules.md`, or narrows a rule with no corpus evidence either way: the written bans that no rule enforces (I111), "worth pushing" and "here's the short version" as rules, and the narrowing of `landscape of` and `lands the/first/with` (I050's config half; none of the four has a hit in the saga).
- **On the saga corpus** (202 files, 273,431 words), `corpusscan diff` shows no finding appearing or vanishing, and the linter's own count holds at 309.
- Tests: six new in `test_voicelint.py` and `test_corrections.py`, all of which fail on 0.5.43.
- `voice_config.json`: two rules rewritten with pinned ids and fixtures, four clean fixtures replaced. `VERSION` 0.5.44.

## v0.5.43 (2026-09-28)

An overlay does what it says, and a correction shows its reason, its reach and its speed before it becomes a rule. This is Wave 5 of the 2026-09-27 review, part 4: overlays, rule ids and `corrections.py`.

**Overlays and ids** (`voicelint.py`, `pherkad.py check-overlay`):
- Removes are applied before adds, so removing a rule by id and adding a new entry with that id replaces it. Before, the add was skipped because the id was taken, and the remove then deleted the rule. An add is skipped only for an exact pattern already present or an explicit id already taken. `check-overlay` prints the net effect, the shipped rules the overlay ends up without, as notes (I054).
- A derived id that collides is suffixed with its own pattern's hash, every member of the group alike, so an id no longer depends on list order (I055). The shipped base pins its one such pair, `gut-check` and `gut check`, with the ids they already had, and a test refuses a new collision in the base. An overlay that adds two strings slugging alike now gets a suffix on both.
- A soft `re:` rule gets no word-edge guard it did not ask for, and a phrase that starts or ends with a slot (`[word]`, `[verb]`, `[det]`) ends at a word edge (I093, I100).

**Corrections** (`corrections.py`):
- Ids are a date and a counter; a hash of the phrase and the date collided on a second correction of one phrase in a day. The ledger refuses two records with one id, and `promote` refuses a matcher that changed after its trial (I184).
- `promote` requires a rationale. It refuses a rule that fired more than once per 1,000 words in its trial unless given `--broad`, and a regex that takes over a second on a 2,000-character line. `trial` reports a regex that does not compile (I185).
- A one-for-one swap of a name, a weekday, a month, a number word or a single letter is classed factual, so it never becomes a style rule. A mined phrase waits for the author's kind (`--kind` on `trial` or `promote`), with the tool's guess kept beside it. A one-word literal rule needs `--confirm` (I036).
- `mine` pairs the sentences of a changed block by shared words, not by position, so an inserted sentence no longer shifts every pair after it. A sentence split in two or two merged is recorded as structural. The phrase is sliced from the author's own characters, and a phrase not found in its context is dropped. A record whose context lacks its phrase gets no example, and its trial says so (I186).

**Also:**
- **On the saga corpus**, `corpusscan diff` over 202 files and 273,431 words shows no finding appearing or vanishing. It lists `soft.gut-check-c10a -> soft.gut-check` as renamed only because it reads the 0.5.42 list with the 0.5.43 id rule; under 0.5.42 itself the ids were the two now pinned.
- Tests: eleven new or changed in `test_voicelint.py` and `test_corrections.py`, all of which fail on 0.5.42. The older promote tests pass `--broad`, since their fixture corpus is a few lines long.
- `voice_config.json` changed only in pinning two ids. `VERSION` 0.5.43.

## v0.5.42 (2026-09-28)

The structural checks count the constructions they name, and fewer that only look like them. This is Wave 5 of the 2026-09-27 review, part 3: `structlint`.

- **Abbreviations no longer end sentences.** Each lookbehind now holds its own period. Before, they sat after the period and tested the wrong characters, so none fired and "Dr. Smith" split in two. A number marker (no., vol., pp.) is an abbreviation only before a digit, since "The answer was no." ends a sentence (I080).
- **Two-beats.** A shared function word or pronoun is not a shared shape: "He left. He came back." shares a pronoun. A shared content word counts only in the same slot of both sentences. A new branch catches the same skeleton, as in "The count was wrong. The ledger was right." A pair counts when the paragraph holds only the pair, or when it closes a longer paragraph (I051, I085).
- **Headings** come from `mdmask`, so setext headings count, and a leading number or emphasis is stripped before the stance checks. A subtitle is a short line standing alone under its heading, and a heading with its subtitle is one unit (I079).
- **Stance headings** are narrower. "The real" or "the actual" plus a stance noun must end the heading or open a clause, so "The actual cost of the project" names its subject. "Where X sits" fires only for abstract subjects (I050, the `structlint` part).
- **Frames** are advisory and never count toward density, in `structlint`, in `check`, and in the review pack. A title's medial bare "not" is a contrast foil, as in "Speed not accuracy" (I049).
- **A list item** is its own unit, so a lead-in and its list no longer read as one staccato paragraph. A URL inside link syntax is not a citation marker (I084).
- **Lines are numbered on newline only**, as `voicelint` and `pherkad` number them. `decide` refuses a line with no text to record against (I083).
- **Crashes and bad config.** An `re:` pattern that does not compile, or that matches the empty string, is a config error (exit 2). The count thresholds must be at least 1. `structlint` reads files with replacement and exits 2 on an unexpected error (I086).
- Also fixed by parts 1 and 2: directives read from code-masked text (I052), quotes folded before the long-quote mask (I113), and setext and curly-apostrophe headings (the rest of I079).
- **On the saga corpus** (202 files, the saga's config), structural findings go from 116 to 112. Staccato drops from 103 to 99, two-beats from 12 to 11, and one advisory contrast frame appears. Testing every pair of short sentences had taken two-beats to 131, most of them deliberate pairs in the saga's narrative register, so the check stays on the closing pair.
- Tests: twelve new or changed in `test_structlint.py`, nine of which fail on 0.5.41. The other three guard behaviour that already held: the subtitle rule, the same-skeleton pair, and the content-word branch.
- No rule in `voice_config.json` changed. `VERSION` 0.5.42.

## v0.5.41 (2026-09-28)

What counts as prose is read the way Markdown renders it. This is Wave 5 of the 2026-09-27 review, part 2: the Markdown reader.

- **`mdmask.line_kinds`** keeps the block state it needs (I070, I073):
  - A fence opened inside a list item closes when the item ends, instead of hiding the rest of the file.
  - A line indented four columns after a blank line is code; a tab counts to the next multiple of four.
  - A line right after a quoted line continues the quote unless it starts a block of its own.
  - A line of `=` or `-` under a paragraph makes a setext heading.
  - An HTML comment block and a `pre`, `script`, `style` or `textarea` block run to their terminator, and no fence is read inside them. Comments are a new kind, `comment`.
  - A `>` indented four columns is code, not a quote.
- **Inline code** is paired per paragraph, as CommonMark pairs it: a run of backticks closes at the next run of the same length, across a line break. An escaped backtick opens nothing, and backticks inside an autolink or a tag are not code. The contents of `<code>`, `<kbd>`, `<samp>` and `<tt>` are masked too (I072, I073, I074).
- **The heading pattern** is linear; the old one backtracked cubically on a long run of spaces. A test holds a 100,000-space heading under a second, and `# C#` now reads as "C#" (I071).
- **HTML input** (`--html`, or a `.html` file): quotations, code, preformatted text and scripts are masked whole. Entities are decoded one at a time, so a decoded line break cannot move a line. A decoded `<!--`, `>` or backtick is replaced by a look-alike, so it cannot become a directive, a quote or code (I094).
- **An unclosed voicelint directive** is reported as `directive.unclosed` and hides nothing. It used to blank every line of prose down to the next `-->` in the file. A directive may still wrap within its paragraph, as three allow markers in the saga do (I103).
- **`structlint`** no longer reads an HTML comment as sentences. It reads its directives from code-masked text, so a directive quoted in code silences nothing, and a directive may name the checks it silences. A suppressed line stays in its paragraph, and the findings reported on it are what is dropped (I082).
- **On the saga corpus** (202 files, the saga's config), the count is unchanged at 309.
- Tests: eight in `test_mdmask.py`, `test_voicelint.py` and `test_structlint.py`, all of which fail on 0.5.40.
- No rule in `voice_config.json` changed. `VERSION` 0.5.41.

## v0.5.40 (2026-09-28)

A banned phrase is caught however it is spelled, as long as it reads the same. This is Wave 5 of the 2026-09-27 review, part 1: the normalization pass.

- **One projection** (`voicelint.project`). Every prose rule now reads a copy of the text with the spelling tricks undone, and each finding is placed at the source line and column its first character came from. The projection:
  - decodes entities (`&mdash;`, `&#45;`) (I102);
  - drops backslash escapes, inline tags and comments, link brackets and destinations, and emphasis delimiters. Underscore italics no longer defeat a word-edge rule; snake_case and `2 * 3` are left alone (I106, I107);
  - removes zero-width and other default-ignorable characters (I099);
  - folds typographic quotes, the modifier apostrophe, no-break and thin spaces, and the Unicode hyphens, then applies NFKC (I096, I097);
  - folds Cyrillic and Greek look-alikes inside a word that also holds an ASCII letter, so a Russian or Greek word is left as it is (I097).
- **Bidi controls** (U+202A to U+202E, U+2066 to U+2069) are an error of their own, `invisible.bidi`, because they can make text display in a different order from the one it is read in (I099).
- **Spaces in a phrase** match any run of spaces or tabs with at most one line break, so a hard wrap or a double space no longer hides a phrase, and a paragraph break still ends one (I059).
- **Dashes.** The dash rule covers the figure dash and the two- and three-em dashes; a figure dash between digits is a range, like an en dash (I104).
- **Trailing "quietly"** fires before punctuation, a paragraph break or the end of the text, and no longer at a hard line wrap (I108).
- **A raw `re:` rule** also runs on the source, because a rule may be about the markup itself, such as the chat surface's Markdown-link ban.
- The URL source rule reads the source, since the projection drops link destinations.
- `structlint` reads the same one-for-one fold, now in `mdmask`, and `replycheck` reads files through `voicelint.read_source` (I096, I102).
- **On the saga corpus** (202 files, the saga's config), findings go from 294 to 309. All 15 new ones are phrases the rules already ban, split across a hard line wrap.
- Tests: nine in `test_voicelint.py`, eight of which fail on 0.5.39; the ninth pins the source column after an entity.
- No rule in `voice_config.json` changed. `VERSION` 0.5.40.

## v0.5.39 (2026-09-27)

The measured profile's flags now mean what they say, and each one says how much it rests on. This is Wave 4 of the 2026-09-27 review. A split-half test on the author's own mail shows the size of the change: the profile was built on one half of his mail by id and compared on the 425 messages of 100 words or more in the other. Under 0.5.38's rule, 373 of the 425 had a shape feature past two standard deviations, and all 425 had a function word past it. Under this release, 5 of 425 have a family flagged.

**Counting** (`fingerprint.py`):
- Curly apostrophes and quotation marks count as straight ones. "don’t" was no contraction and “this” no quotation, so mail from any client that curls them read as having neither. The evidence still quotes the author's own characters, and the leakage check sees a curly copy as a copy (I119).
- The function words are about 150 closed-class words: determiners, pronouns, prepositions, conjunctions, auxiliaries and modals, and focusing particles. The old list was Fry's instant words, which included water, people and animal. The distance over them is renamed `fw_distance`, a within-author mean |t|; it was never Burrows's Delta (I191).
- `type_token` is a moving-average ratio over 50-word windows, so it no longer falls as a text grows (I188).
- Every shape feature keeps a quoted passage, including sentence spread, short-after-long, paragraphs, openers, function words and vocabulary. A flag quotes the first feature in its family that has a passage. A word the draft never uses is shown by the author's own use of it (I037).

**Comparing** (`fingerprint.py compare`, `pherkad.py check --fingerprint`):
- A text is measured against the author's single-document pieces of the size nearest its length (100, 200, 400 or 800 words); under 100 words it is not measured. A piece never mixes two documents. Chunks pooled across short emails had hidden the variation between emails (I188).
- Each feature gets a prediction t from the sample SD, floored at one occurrence's worth. A habit the author never shows is no longer an automatic three standard deviations (I189).
- The features fall into seven families, and one habit is one finding. A family's p-value is the rank of its largest |t| among the author's own pieces, each left out in turn. That test is exact whatever the features' skew or correlation. Benjamini-Hochberg at `--fdr` (default 0.05) replaces the fixed 2.0 threshold; `--fingerprint-threshold` is now `--fingerprint-fdr`. When a profile has too few pieces at a size to reach the cut, the result says so (I187, I189).
- A surface with no profile of its own is still measured against the pooled profile, but the finding names the basis and its mix. A user surface map entry may set `"basis"`. A text the profile cannot measure gets a `voice.unmeasured` finding instead of silence (I192).

**The discriminant** (I190):
- It is now nearest shrunken centroids, with the shrinkage chosen by 5-fold cross-validation grouped by document. The score is a Platt-calibrated log-odds, reported with `p_author`, the cross-validated AUC, and a passage for each feature that pulls it.
- It refuses a reference under 50 pieces. The current `reference-flattened.json` has 14 chunks and no per-piece vectors, so the discriminant is off until the reference is rebuilt. `detect.py prompts` refuses the fingerprint condition up front, and names any case under 100 words, instead of writing a floor verdict with a made-up zero.
- The score's scale changed. The detect cutoffs (+0.40, +0.15, 0, -0.15) were set on the old scale and wait on the preregistered thresholds being set again.

**Building and importing** (`fingerprint.py build`, `samples.py`):
- `build` exits 2 on an unknown provenance, on an `--exclude` id missing from the manifest, and on `approved` without `--allow-approved`, which is recorded in the output. Nothing weighted `captured` below `hand`, so both docstrings now say so (I149).
- Mail is read in the charset it is actually in. A latin-1 or ascii label on Windows-1252 or UTF-8 bytes is not believed, and bytes no charset can read are counted and warned about (I119).
- `import-mbox` needs `--from` (repeatable, +tags ignored), `--provenance` and `--surface`, and stores the sender on each record. It skips auto-replies, bulk and list mail, calendar invitations, and forwarded message parts, read from the headers as well as the body. It cuts HTML mail at the first quoted thread, recognises reply attributions in more forms and languages, keeps the author's lines in an interleaved reply, and drops a trailing signature block. A message that cannot be read is counted and skipped, and the manifest is saved even if the loop stops (I142, I143, I195).
- `import-captured` takes only Verbatim blocks and the capture sweep's drop entries, once each, and no longer takes bold quotations inside the assistant's analysis. It lists the candidates and writes only the ids given to `--accept` (I193, I194).

**Tests:**
- Twenty-one tests, new or rewritten, in `test_fingerprint.py`, `test_samples.py`, `test_pherkad.py` and `test_study.py`. All 21 fail on 0.5.38 and pass here.
- The fixtures are larger, because a profile now needs 5 pieces, a flag needs enough pieces to resolve, and the discriminant needs 50 reference pieces.
- The fixture that quoted a real saga item now uses invented text.
- No rule in `voice_config.json` changed. `VERSION` 0.5.39. The fingerprints in voice-profile are not rebuilt; that waits on the author.

## v0.5.38 (2026-09-27)

The eval harness scores what it claims to, and refuses to score a measure against its own inputs. Wave 3 of the 2026-09-27 review, part 2. Rescored under this release as exploratory, detect-01's correct-profile lift falls from +0.26 / +0.83 to +0.03 / +0.46; `docs/ROADMAP.md` says so beside the finding it undercuts.

**Detect scoring** (`eval/detect.py`):
- Verdicts are re-validated at score time, and planned against scored is printed per condition and case type. detect-01 had 139 verdicts the current validator rejects (I022).
- A pair's direction comes from the reader. Pairs marked `same`, or where the reader heard the flattening as the writer, leave the model's scores. Picks other than A, B or same stop the run. Model-reader agreement is shown per condition (I164, I166).
- Lift is reported against each control, paired by case, with a bootstrap interval. A control whose verdicts all sit on one side of the pass bar is marked degenerate and never pooled (I165).
- The atypical piece has its own row, and every rate shows its denominators (I166).
- Manifests record the hash of the profile actually used, and of the whole fingerprint and reference files (I162). The shuffled control no longer tells the judge it is one (I161).

**Preregistration** (I163): `study.py freeze RUN` records `prereg.md`'s hash. `prompts`, `run` and `score` refuse an unfrozen or changed plan, and `score --exploratory` says so on the first line of the results.

**Blinding:**
- Blind ids are random (I027).
- Detect pair sheets are one per flattening round, so an authentic text never repeats on a sheet (I156).
- Revise sheets show the starting draft once and rate it there, show identical drafts once, and score the rating for every arm that wrote that text (I156, I172).
- The author pilot keeps its A/B key across regenerations and shows dashes as commas in both arms (I147, I156).
- No sheet blanks filled answers without `--force`, which keeps a copy (I147).

**Revise and author scoring** (`eval/study.py`):
- Provenance is taken at prompt time from the rule set that produced the findings, and prompts will not orphan finished drafts (I167).
- The both arm shares the judgment arm's clauses (I170).
- A mechanical arm with no findings stops (I171), and each arm reports how many of its drafts came back unchanged.
- A new `profile` arm, the generic review with the profile attached, separates the method's effect from the profile's (I169).
- The anchor is sampled, never atypical, and never a forced-choice candidate (I168).
- Ratings parse strictly (I174). A flagged author draft counts 1 in the lift (I175). Pooled comparisons name their writers and who was left out (I177).
- The author pilot reports an exact sign test (5 of 8 is p = 0.73), with a caution that its discriminant is the measure the loop optimises (I157).

**Leakage** (`tools/fingerprint.py`):
- A reference records each source file's hash and stem.
- `fingerprint.leakage` flags a case that the reference was built from or is a fingerprint sample, and `detect prompts` and the author pilot refuse on it (I158). The pilot's reference was built from flattenings of all eight held-out emails.
- `build --exclude` also drops near-duplicates of an excluded piece, at 5-word-run containment of 0.2 or more either way round, and the pilot's exemplars skip them (I159). One training email, `email-1ebacf1e`, is caught on the real data.
- `detect plan` refuses a profile that shares an 8-word run with a case (I160). The `brian` profile used in detect-01 quotes the held-out op-ed.

**Tests:**
- The detect end-to-end test is asymmetric: `wrong` discriminates, `shuffled` and `none` are degenerate. It asserts the pooled +1.00, which the old code would have reported as +2.00.
- There is now an author-scorer test, plus parser, clause and leakage tests (I178).

No rule in `voice_config.json` changed. `VERSION` 0.5.38.

## v0.5.37 (2026-09-27)

The eval runners are isolated, and every run proves it before a prompt goes out. Wave 3 of the 2026-09-27 review, part 1.

- **Both runners saw the profile.** A canary question showed `eval/runners/claude.sh` loading the operator's memory index, which describes the author's voice rules, and `codex.sh` loading an `AGENTS.md` that names the author's profile. Every pilot run before this release saw part of the profile it was meant to lack, including the generic and bare control arms and every flattening, and those numbers wait on a rerun (I019, I020).
- **The runners are isolated.** `claude.sh` runs with `--safe-mode --strict-mcp-config`, no settings, no tools, and an empty working folder. `codex.sh` runs with a throwaway `CODEX_HOME` holding only a link to the existing login, plus `--ignore-user-config --ignore-rules` and an empty working folder. Both now answer the canary NONE. Codex still sends its own built-in writing guidance on every call, which no flag removes; `eval/README.md` records this.
- **`tools/runner.py`** (new, bundled) is the one runner call that `study.py` and `author.py` share, replacing two copies:
  - The runner starts in its own process group, so a timeout kills the whole group. The old path left a grandchild running (I021).
  - A nonzero exit keeps stderr and the start of stdout in the error.
  - A reply that is a runner error, a rate-limit notice, or a refusal is never scored as a draft (I023).
  - It provides `canary()`.
- **`study.py run` and `flatten`:**
  - Both ask the canary first, refuse to send anything unless the answer is a bare NONE, and keep the answer in `canary.json`. `--skip-canary` records the run as unchecked.
  - Status is written atomically as each reply lands, together with its reply file. Ctrl-C keeps every finished reply, and a resume adopts a reply file whose status entry was never written (I024).
  - `--force` restarts the attempt count and never marks a done item failed without calling the runner (I025).
  - The model recorded is the one the runner reports on its `runner-meta` line, with the CLI version; `--model` is kept as a label, and only items finished in the current pass are stamped (I026).
  - Flattenings are held to the 10 percent length band their prompt states, instead of 15 (I028).
- Tests:
  - Five in `test_runner.py`. The group-kill test fails the old way, which left the grandchild running.
  - Three in `test_study.py`: a leaky runner is refused with nothing sent, the reported model is recorded, and an unrecorded reply is adopted.
  - Fake runners answer the canary as a clean runner would.
- No rule in `voice_config.json` changed. `VERSION` 0.5.37.

## v0.5.36 (2026-09-27)

Exposure and the supply chain: the mechanical half of Wave 0 of the 2026-09-27 review. The history purge waits on the author.

- **One overlay, named.** Under `--config` with no surface, a `./voice_config.json` in the working folder was merged in without a word. `--config` is now the only overlay, and a surface never reads the folder's file (I128). A `--surfaces` or `PHERKAD_SURFACES` path that does not exist exits 2 and no longer falls back to another rule set (I150). A hook test runs from a folder holding a relaxing `voice_config.json`, which is what open PR #3 would have let through (I075).
- **Private material cannot be committed.** `tests/guard-private.sh` runs first in the pre-commit hook. It refuses any staged voice file, correction ledger, fingerprint, reference, held-out id list, review packet, authoring record, root `voice_config.json`, `eval/data/`, `_to_delete/`, or backup, even when `git add -f` forced it past `.gitignore` or the branch has no `.gitignore` at all. `.gitignore` gains the same artifacts (I007, I009).
- **Build with no push token near third-party code** (I013). `build.yml` is two jobs. `build` has a read-only token and installs the PDF renderer from the hash-pinned `.github/ci-requirements.txt` (weasyprint 70.0 and 12 dependencies). `publish` has the write token and runs only git. Every action in both workflows is pinned to a commit SHA, checkout keeps no credentials, and Test runs with a read-only token.
- **The eval README tells the truth about where data goes** (I018). It used to say `eval/data/` never leaves the machine. The runners send samples, profiles, held-out pieces, and drafts to Anthropic (`claude.sh`) or OpenAI (`codex.sh`), and nothing redacts mail yet.
- Four tests, each failing on 0.5.35. No rule in `voice_config.json` changed. `VERSION` 0.5.36.

## v0.5.35 (2026-09-27)

The gate never passes in silence, and the state files cannot be cut or lost. Wave 1 of the 2026-09-27 review.

**The Stop hook** (`replycheck-hook.py`):
- A check that cannot run now blocks once with `voice check did not run: <reason>`, and the assistant tells the person the reply is unchecked. This covers a sibling module that will not import, a broken overlay, an unknown surface, an unreadable transcript, and a crash. Before, the hook exited 0, and a broken hook passed everything (I045, I092, I117). `stop_hook_active` keeps it to one block per turn.
- The enforced revision is checked too. A revision that still fails reaches the person as a `systemMessage` and never blocks a second time (I139).
- Meta rows (a skill body, an image note) are not the turn boundary (I138). `last_assistant_message` is checked when the transcript has not caught up (I048).
- The hook reads no `surfaces.json` from the session's working folder, so a project cannot redirect or disable the chat check (I127). `resolve_surface` and `load_layers` take `cwd=False`, and a surface given as a path reads no user map at all.
- On a surface the assistant speaks, a reply cannot exempt itself (I140). A voicelint or structlint directive outside code is made inert and reported as `directive.in-reply`, an error, and blockquoted lines are linted. Naming a directive or a banned phrase in backticks still works.

**State files** (`statefile.py`, new):
- Every state write goes through a temporary file and `os.replace`, so an interruption leaves the old file whole. That covers the ledger, the samples manifest and sample files, the decision store, the promoted overlay and the prose, fingerprints and references, and label exports (I117, I118). A symlink is followed, so the voice files that link into session-hygiene stay links.
- Each load-change-save of the ledger, the samples manifest, or the decision store holds an exclusive lock on a `.lock` sidecar. Eight concurrent `corrections.py add` runs lost one to three records under 0.5.34 and lose none now (I118).
- `corrections.py promote` checks and builds everything in memory first: it reads the overlay and prose, validates, and loads the effective config from a probe file. Only then does it write, recording `promoting` in the ledger before the overlay and prose. A rerun resumes and adds nothing twice (I116).
- `pherkad.py decisions --prune` counts only files it actually read, exits 2 and prunes nothing when a read fails (I125). A decision now records the `ruleset` it was made under (surface and overlay path). A run under another rule set reports it as not evaluated and never prunes it. The `rule gone` branch is now reachable (I126).
- `corpusscan.py review` will not overwrite an existing label file without `--force`. The export records its row count, and `score-review` rejects a file that no longer holds them, rejects a hit label other than TP or FP, and exits 1 when nothing is labelled (I115).

Tests: ten hook tests (eight fail on 0.5.34), five `test_statefile.py` tests (the concurrency one fails on 0.5.34), and two prune tests. The threshold test now decides and re-checks under the same overlay. No rule in `voice_config.json` changed. `VERSION` 0.5.35.

## v0.5.34 (2026-09-27)

Main green again, and kept green. Main's Test run had been red since 0.5.33: Python 3.8 and 3.9 crashed on two modules, four tests had lagged the 0b8b7b4 link rule, and the manifest was stale. Wave 2 of the 2026-09-27 review.

- **Python 3.8 floor restored.** `fingerprint.py` and `samples.py` carry `from __future__ import annotations`, and `pherkad.py author` no longer merges dicts with `|`. All eleven suites pass under 3.8.2 and 3.9.
- **The Stop hook skips headless runs** (640f3cb, shipped here): a turn opened with `turnOrigin: "sdk"` is a script's `claude -p` call, and blocking it made the model rewrite output a program parses.
- **Tests that never ran now run.** `test_pherkad.py` and `test_corrections.py` called `unittest.main()` before their last classes, so six tests had never run as scripts, which is how CI runs them. One of them failed once it ran: a measured `voice.sent_mean` finding quoted the feature name, not the text. Each sentence-length statistic is now quoted by the sentence whose length is nearest it.
- **Tests match the link rule.** Since 0b8b7b4, a relative Markdown link passes on `assistant-chat`, and an absolute, `~` or http target is the miss. Three tests now say so.
- **A structlint crash is a failure.** `test_structlint`'s helper used to read a crash as "no findings". It now fails on any exit other than 0 or 1, or on a traceback.
- **Gates.** The pre-commit hook runs `tests/run-all.sh`, which runs the smoke test and every suite against the checkout it sits in (`smoke.sh` no longer hard-codes a path), and `PYTHON=` picks the interpreter. In CI, every suite step runs even after an earlier one fails. `build.yml` now runs only after Test finishes green on main, so a red suite never publishes a bundle.
- **One version.** `manifest --write` stamps `.claude-plugin/plugin.json`, which had drifted to 0.5.0, and `--verify` fails when they differ.
- No rule in `voice_config.json` changed, so there is no corpus count.
- `VERSION` 0.5.34.

## v0.5.33 (2026-09-18)

Roadmap item 25: authoring on demand from the numbers.

- **`pherkad.py author NOTES --surface S --fingerprint F [--reference R] [--samples DIR] [--profile-dir D] [--runner CMD] [--rounds N] [--out FILE]`** (`author.py`). The packet: the surface and its guidance; the fingerprint's numbers for that surface written as instructions (sentence length band and median, short and long shares, paragraph size, opener rates and common first words, punctuation per sentence with dashes and semicolons named absent where they are, contraction and question rates, the constructions the author rarely or never uses, the function words used more and less than the reference); the archetype from `Voice_Profile.md`; the three hand-written samples nearest the notes in subject (content-word cosine, 80 to 450 words); the notes. Without a runner it prints the packet. With one, the runner drafts, the draft is scored (mechanical check, discriminant, deviating features), the findings go back as revision instructions up to `--rounds` times, and the best draft is kept (no errors first, then the discriminant, then fewer warnings) with its record in `<out>.author.json`.
- **`eval/author_pilot.py`**: the test the feature has to pass. For each held-out piece, the runner extracts the facts as terse notes, writes one draft from a bare prompt and one from the packet, and both are scored against the real piece; a blind pairs sheet asks the author which reads as his. First run on the eight held-out work emails (claude-sonnet-5, one revision round): the packet's drafts sat nearer the author than the bare prompt's on 5 of 8 (mean discriminant +0.06 against +0.03; the real emails +0.08), and carried 0 mechanical errors against the bare prompt's 8. The blind reading is pending; the feature stays while it wins there.
- Four tests (`test_author.py`).
- `VERSION` 0.5.33.

## v0.5.32 (2026-09-18)

Roadmap item 24: the author's edits as evidence.

- **`corrections.py mine DRAFT EDITED --ledger F [--source ...] [--surface S] [--dry-run]`** reads the diff between what a model drafted and what the author sent. Sentences are aligned; inside a changed sentence, each changed run of words up to eight long becomes a ledger candidate, `X -> Y` with the draft sentence as context, and a run the author cut becomes `X -> ""`. A sentence more than six tenths rewritten becomes a judgment record (no regex). Case-only and punctuation-only changes and bare number swaps are not candidates. Every record enters pending with an empty rationale; a phrase already in the ledger is reported and not added twice; `trial` and `promote` still need the count and the author's say, and a factual change still never becomes a rule.
- Two tests.
- `VERSION` 0.5.32.

## v0.5.31 (2026-09-18)

Roadmap item 23: prose from numbers.

- **`fingerprint.py prose F [--surface a,b] [--reference R] [--out FILE]`** renders the prose profile from the fingerprint, one section per surface: sentences (mean, spread, median, quartiles, short and long shares, short-after-long), paragraphs, openers and the most frequent first words, punctuation per sentence, contractions and questions per 1,000 words, the construction rates with the ones that never occur named as absent, the function-word signature (against the reference when one is given: used more, used less, both rates), vocabulary. Every claim carries its count, and where the feature keeps evidence, one quoted sentence with the sample id that holds it. Evidence is now credited to the sample whose paragraph holds the sentence, and the short-sentence example is a real sentence of three words or more, not a list number.
- **`pherkad.py review-pack --measured FILE`** carries the measured view into the judgment packet as `Voice_Profile.measured.md` (also picked up from the profile directory when present), so the model reads the numbers beside the archetype. The four archetype moves in the hand-written `Voice_Profile.md` (concrete object before concept, flat consequence, the telling wrong detail, the role reversal owned) are not counted by this fingerprint and stay as judgment guidance with quotes but no counts; the measured view sits beside them, and the roadmap's "no claim without a number" holds for the view, not yet for the archetype.
- Two tests.
- `VERSION` 0.5.31.

## v0.5.30 (2026-09-18)

From importing two Gmail accounts (1,339 and 6,252 sent messages) into the author's private samples folder.

- **`samples.py import-mbox` reads HTML-only bodies down to text** (block tags to line breaks, other tags dropped, entities decoded) instead of taking the raw markup; 99 of the older account's messages had come through with `<div>` tags in them and were re-imported clean. One test.
- Two findings recorded in the private provenance rule, both measured on the held-out 2025 to 2026 work mail: personal mail pooled with work mail lowered the check from 16 of 16 to 14 of 16, and mail from before 2015 lowered it to 13 of 16, so each is its own surface (`email-personal`, `email-early`) and `email` is work mail from 2015 on. A register is a surface; the numbers say where the lines are.
- `VERSION` 0.5.30.

## v0.5.29 (2026-09-17)

Roadmap item 22 and the first measured result. Brian's sent mail (an Apple Mail export of the Stevens account) went into the private samples folder: 231 messages, 34,969 hand-written words, after `import-mbox` learned to drop calendar invitations and auto-replies, Outlook's angle-bracket link targets, and bodies over 800 words (pasted documents, not typed mail).

- **Distance is not recognition.** A fingerprint built from everything but eight held-out emails put each email's flattening nearer the author's mean than the email itself on 15 of 16 pairs: generic prose sits near everyone's mean. So `fingerprint.py build-reference DIR --out R` profiles what the author is not (flattenings, or other writers), and `compare --reference R` adds a **discriminant**: over the features where the author's mean and the reference's differ by half a pooled standard deviation or more, the mean per-feature evidence that the text is nearer the author (a linear discriminant, equal variance, floored). With the reference built from the other emails' flattenings each time, the held-out email scored above its own flattening on 16 of 16 pairs. Against six cohort notes the score does not separate: it has learned hand-typed mail from machine-flattened mail, not this writer from another, and a reference of other writers is what would teach it that.
- `fingerprint.py build --exclude ID,ID` holds samples out; the fingerprint records them.
- `pherkad.py check --fingerprint F --reference R` adds `voice.discriminant` beside `voice.distance`.
- **The detect harness has a `fingerprint` condition**: `study.py prompts <run> --fingerprint F --reference R` writes its verdicts directly, no model, with the mapping fixed in `detect._fingerprint_verdict`, and `score` reports its margins beside the linter floor.
- Four tests (reference and discriminant, exclude, the harness condition, the mail filters).
- `VERSION` 0.5.29.

## v0.5.28 (2026-09-17)

From Brian's slide-by-slide reviews of the FA550 Week 3 rebuild and Week 4 revision, fifteen corrections through the ledger (`corrections.py add`, `trial`, `promote`), the first project ledger in use.

- **Four soft phrases**, shipped in the base set because none is slide-specific: `soft.is-the-check` (the copular equative closer, `X is the check`, narrowed so `the check-in` does not fire), `soft.earns-nothing`, `soft.on-its-face`, `soft.leaves-out-is-most-of`. Trial counts on 624 files: 3, 2, 2, 0.
- **Two `structlint` frames**: `paired-beat` (a title of two comma-joined halves with the same opener or a count on each side and no verb: "What you keep, what you change", "Twelve outputs, seven decisions") and `appositive-tail` (a noun phrase, a comma, and a tail that gestures: "Three layers, and tonight is the second visit", "The same paragraph, sent back three ways"). Both are rate checks across a document's headings and subtitles, like the other frames, and both accept a numbered heading. Two tests.
- The judgment-only families are in `voice-rules.md` under the 2026-09-17 heading: the callback that asks the room to recall an earlier week, the compressed line that reads as noise, the points count standing in for a reason, the abstraction spoken about but not seen, and the section tagline that previews its section.
- `VERSION` 0.5.28.

## v0.5.27 (2026-09-16)

Roadmap phase 6, items 20 and 21: the measured profile (`docs/measured-profile.md`).

- **`samples.py`**: the author's own writing with provenance. `add FILE --dir DIR --provenance hand|captured|approved --surface S` copies the text under the private samples folder and records id, surface, date, words, and sha256; nothing enters without a provenance and a surface, and the tool never guesses either. `import-captured CAPTURED.md` takes only the verbatim author items out of the saga's capture file (bold-quoted items and `Verbatim:` blocks; the assistant's prose around them is not his) as `captured/narrative`; `import-mbox FILE --from ADDR` takes the author's sent mail from an export he makes himself, quoted replies and signatures stripped, as `hand/email`. `list` and `verify`. Six tests.
- **`fingerprint.py build --samples DIR --out F`**: the measured profile, stdlib. From `hand` and `captured` samples (never `approved`, which the tool already shaped), per surface and pooled, over 200-word chunks so every feature carries a mean and a standard deviation in the author's own units: sentence length and its spread, short and long shares, short-after-long runs, paragraph shape and closers, opener classes and first words, punctuation per sentence, contractions and questions, the construction rates (contrast frames, candour, pointers, hedges, intensifiers, initial And/But/So, passive shapes), 150 function-word rates (Burrows's Delta), word length, type-token ratio. Every feature keeps up to five quoted sentences with their sample ids. `compare FILE --fingerprint F` reports each feature past two standard deviations with the text's sentence and the author's beside it, plus Delta and a shape distance; `show` prints the profile. Seven tests.
- **`pherkad.py check --fingerprint F`** adds advisory `voice.<feature>` findings and a `voice.distance` summary; never counted in density, never an error. One test. `samples.py` and `fingerprint.py` join the bundle.
- First build, from 84 verbatim saga items (1,898 words, narrative register): the fingerprint separates nothing in the professional pilot corpus, and should not, since no hand-written professional sample exists yet. The tool is ready for the sent-mail export.
- `VERSION` 0.5.27.

## v0.5.26 (2026-09-16)

From the first detect pilot (`eval/data/runs/detect-01`, 348 judgments).

- **A judge reply must agree with itself.** The first run returned `PASS` with a rating of 1 twice and `PASS` with no evidence and no markers; the validator scored them. Now a `PASS` needs a rating of 3 or more, a `REWRITE` a rating of 2 or less, and every verdict needs at least one quoted phrase in `evidence`; a reply that fails is retried like any other invalid reply, and the judge prompt says so. One test.
- **Two runners** in `eval/runners/`: `claude.sh` (the Claude CLI with no settings, so no hooks and no CLAUDE.md voice rules reach the control arm, no tools, no saved session) and `codex.sh` (the Codex binary, final message only). Documented in `eval/README.md`.
- `VERSION` 0.5.26.

## v0.5.25 (2026-09-16)

- **`study.py flatten <writer> --runner CMD [--k 2]`** writes the detect task's flattened cases: one prompt per held-out piece and variant, through a runner that never sees the profile, held to within 10 percent of the source length (a shorter text is a confound, not a flatter voice), retried otherwise, with a `.meta.json` beside each flattening carrying the runner, model, and hashes. Before this the protocol said how to make a flattening and nothing made one.
- One test.
- `VERSION` 0.5.25.

## v0.5.24 (2026-09-16)

Item 18 of `docs/ROADMAP.md`, the last of phase 5: a judgment ruling is kept.

- **`pherkad.py review-import TABLE --file DRAFT --decisions FILE [--surface S]`** records the ruled rows of a quick-mode table (the Markdown table the skill returns, or a JSON list of the same rows; `-` reads stdin) in the decision store. A row whose `decision` is `intentional`, `literal`, `not applicable`, or `quoted` is a decision; `fix` rows and rows without a quote or a rationale are skipped and said so. A row whose `rule_ref` is a mechanical rule id resolves to the finding at the quote and is recorded exactly as `decide` would record it. Any other reference becomes a `judgment.<family>` record (`judgment (5c)` becomes `judgment.5c`, `positive-register` becomes `judgment.positive-register`) keyed on the quote and the line it sits on, with the rationale as the reason. Importing the same table twice updates the records in place.
- **The next packet lists what has been ruled.** `review-pack` carries `already_ruled` (rule id, quote, disposition, reason) for every judgment record whose quote is still in the draft, and the prompt prints them under a heading that tells the model not to raise them again.
- **A judgment record is live while its quote is in the file.** `decisions` reports one `stale (quote gone)` when the sentence has been edited or cut, and `--prune` drops it, so a ruling cannot outlive the text it was made on. Judgment records never suppress mechanical findings and never enter the density.
- A row with no quote (a whole-document ruling such as "positive register not applicable") is not recorded; there is nothing in the text to key it on, and a ruling keyed on the file would go stale on any edit.
- Four tests.
- `VERSION` 0.5.24.

## v0.5.23 (2026-09-16)

Item 17 of `docs/ROADMAP.md`, labelled calibration.

- **`corpusscan.py review DIR --surface S --out labels.jsonl`** exports a labelling sample as JSONL: up to `--per-rule` hits for every rule (path, line, a hash of the line, the span, the context, an empty `label`) and up to `--unflagged` paragraphs of 40 to 200 words on which nothing fired, with a meta line carrying the surface, corpus size, base hash, and the labelling convention. The reader marks each hit `TP` or `FP`, and each unflagged unit `clean` or the rule id that should have fired. The tool never writes a label.
- **`corpusscan.py score-review labels.jsonl ...`** reports, per surface and rule, TP, FP, precision, and false flags per 1,000 words; the misses the reader named on unflagged units; the units confirmed clean; and how many records are still unlabelled. So a rule can carry a number instead of an impression, and a bad number is grounds to narrow or drop it.
- Three tests.
- `VERSION` 0.5.23.

## v0.5.22 (2026-09-16)

Item 19 of `docs/ROADMAP.md`: the three weaknesses the Astra review of 0.5.17 named, each a way a decision could outlive its reason.

- **The heading-rate finding is document-scoped.** `structure.interrogative-headers` now quotes every heading in the rate (question ones marked), and a decision on it is keyed on that list, so a change to any heading that moves the rate makes the finding new again. Before, it was anchored to the first question heading and the 0.5.17 paragraph fix did not reach it.
- **A structural rule's hash carries its implementation revision.** `structlint.STRUCT_REVISION` numbers each check; `rule_hashes` folds the number in beside the thresholds. Changing how a check works (a regex, the parallelism test) is now a rule change that wakes every decision made under the old version; the numbers already record the 0.5.6 changes.
- **Overlay fixtures are also run under the effective stack.** `check-overlay` still tests each rule alone (that proves matching), and now says when a `fires` example that passes alone loses its span to another rule under the full configuration, naming the rule that wins: `worth [word] than` against the shipped `worth more than`, for one.
- Three tests.
- `VERSION` 0.5.22.

## v0.5.21 (2026-09-16)

Item 16 of `docs/ROADMAP.md`, resumable eval runs.

- **`study.py run <run> --runner "<command>" --jobs N`** executes a planned run's prompts through any command that reads a prompt on stdin and prints the reply (`claude -p --model ...`, `codex exec -`, a script), so the harness stays stdlib-only and model-agnostic. Every item's state lives in `runs/<run>/status.json`: attempts, prompt and reply sha256, runner, model, error, finish time. A stopped run resumes with the same command; a reply that fails validation (a detect reply without a JSON verdict, a rating outside 1 to 5, an unknown verdict word, a draft under forty characters) is retried up to `--retries` times and then marked failed with the reason; `--limit N` runs a smoke test; `--dry-run` lists; `--force` redoes. Only the JSON object of a detect reply is saved, not the chatter around it. `--model` is recorded on every completed item.
- The detect judging prompt now names the surface, the one omission the Astra review found in it.
- Four tests with fake runners: validation, retry then failure, resume, a runner that exits non-zero.
- `VERSION` 0.5.21.

## v0.5.20 (2026-09-16)

Item 15 of `docs/ROADMAP.md`, the judgment packet.

- **`pherkad.py review-pack --surface X FILE`**, new. One command assembles everything a quick-mode judgment run needs: the surface (speaker, positive-register expectation, guidance, approved excerpts from the user map), the three profile files found by `--profile-dir`, `PHERKAD_PROFILE`, the repository root, or the working directory (inlined with a sha256 each, or by path and hash only with `--no-profile-text`), the mechanical findings with the decision file applied and density over what counts, the judgment-only rules that apply to this speaker and register, the Quick mode instructions lifted from `SKILL.md` (with step 1 rewritten, since the findings are already there and the model is told not to run a tool), and the output schema. `--format json` prints the bundle; the default prints the prompt; `--out DIR` writes `pack.json` and `prompt.md`. The surface is required and never inferred. A missing profile is said in the prompt, not hidden: an explicit `--profile-dir` without one is a profile-less scan and the report has to say so.
- `SKILL.md` Quick mode gains a step 0: assemble the packet when a runtime is available; steps 1 and 2 are then done.
- Eight tests.
- `VERSION` 0.5.20.

## v0.5.19 (2026-09-16)

The repeated-frame check, the first feature from the Astra review of 0.5.17 and the first check that reads a whole document rather than a sentence.

- **`structure.frame.<name>.<kind>`**, new in structlint. A frame is a syntactic template no single instance of which is a fault: `X, not Y`, `X rather than Y`, `X is not Y` (the `contrast` frame), and `The one thing that`, `What X gets wrong`, `Why X matters`. The check counts each frame across three unit kinds and reports one advisory finding per frame per kind when the recurrence clears the thresholds: headings, where the units are the headings plus the short line under each (a slide's subtitle or a section's tagline) and the share is taken over the headings themselves; sentences; and the closing sentence of every paragraph of forty words or more. Titles use a loose pattern (a bare `not` in a title is the foil) and sentences a strict one. The finding's match quotes the units, a decision on it is keyed on that list (`scope: document`), and it stays out of the combined density. Thresholds are seven new `structure` keys, shipped with defaults and open to a surface or overlay.
- **Calibrated on the three documents that motivated it and two that should stay quiet.** The Week 3 deck before its edits fires (6 of 40 slides); after them it does not. The NeurIPS paper fires at heading level (3 of 12) and sentence level (39 of 183). The Week 4 deck does not fire, since its frame lived in body lines the judgment pass counted and this check does not; that is the intended side of the line. None of the 202 saga files and none of this repository's docs fire.
- `pherkad.py rules` lists the twelve frame ids; the manifest carries them.
- Six tests in structlint, one in pherkad (document-scoped decision, outside density).
- `VERSION` 0.5.19.

## v0.5.18 (2026-09-16)

- **`load-bearing` needs a word boundary on the left.** The context check matched `load bearing` inside `workload bearing on exercise` in a real paper. One character, one test.
- `VERSION` 0.5.18.

## v0.5.17 (2026-09-16)

Two more defects from the Astra re-run, which again ran out of usage before it could report (`docs/codex-features-astra-2026-09-15-second-pass.md`, third attempt).

- **`corpusscan` runs both engines and takes `--surface`.** It ran voicelint alone, so the structural rules could not be counted or calibrated on a corpus, and it had no way to apply a surface's thresholds. `run_corpus` now goes through `pherkad.run_text` (no density), findings are the shared dicts, `scan` and `diff` accept `--surface` (applied before `--config`) and `--no-structure`. On the saga the structural rules count 103 staccato, 12 two-beat, 1 header, the same 116 the gate reports as advisory.
- **A structural decision is keyed on its paragraph, and on the thresholds.** structlint reports a paragraph against its first line, so a decision keyed on that line survived an edit further down; and a threshold change did not change the rule's hash, so a decision made under one threshold survived another. `context_hash` takes the whole paragraph for a structural finding (the record says `scope: paragraph`), and `rule_hashes` folds the `structure` thresholds into every structural rule's hash and the density's.
- Tests for both.
- `VERSION` 0.5.17.

## v0.5.16 (2026-09-15)

Three defects, two of them named by a second Astra review that ran out of usage before it could finish (`docs/codex-features-astra-2026-09-15-second-pass.md`).

- **Density is computed over the findings that count.** `pherkad.py check` built its combined density over every finding, so eight advisory structural findings produced a counted density warning that blocked under `--strict`, and deciding every finding on a page left the density warning standing. `density_finding()` now runs after advisory and decisions are applied, over what remains; `run_text(density=False)` lets a caller do the same.
- **A decision covers every line with that text.** `decide` set a record's `count` from the occurrences on the line named, so a refrain repeated eight times was decided once and reported seven times. It now counts every finding in the file whose rule and line text match.
- **The revision scorer penalises a flagged draft instead of dropping it.** The primary contrast (arm minus generic) scored only unflagged drafts, so an arm that invented facts on half its runs could show a lift on the other half. A flagged draft is now scored 1 in the penalised mean that drives the contrast; the unflagged mean is shown beside it.
- Tests for all three.
- `VERSION` 0.5.16.

## v0.5.15 (2026-09-15)

Item 13 of `docs/ROADMAP.md`, the detection experiment, which completes the roadmap and gives `docs/review-followups.md` item 2 its harness.

- **`eval/detect.py`**, new, dispatched from `study.py plan --task detect`. Cases per writer from the writer's directory: authentic held-out (one may be atypical), flattenings paired to their source, matched impostors, override pieces. Five conditions: `correct`, `wrong`, `shuffled` (the profile's own lines scrambled, a control the protocol asked for), `none`, and `linter` (the mechanical verdict alone, the floor, written by the harness). `--repeats` runs every item N times under blind ids. `plan` writes `prereg.md` and `score` warns while it holds a TODO.
- **Judging prompts** ask the model for a JSON verdict (rating, PASS / light REVISE / REVISE / REWRITE, positive register, markers cited, evidence) and record model and hashes per item. **Two reader sheets**: the pairwise authentic-versus-flattened sheet in blind order, and every mechanical finding on authentic text for TP/FP labelling.
- **Score** reports, per writer and pooled: paired discrimination margins under each condition; correct-profile lift over the controls beside the linter floor; acceptance and rejection rates against the pass bar; verdict stability across repeats as exact, adjacent, and severe movement; explanation overlap as the Jaccard of markers cited; reader accuracy on the decided pairs, with pairs the reader marked `same` excluded from the model's scoring; and per-rule linter precision with false flags per 1,000 authentic words.
- `eval/test_study.py` runs the whole task with a synthetic judge: two writers, six cases, five conditions, two repeats, a severe wobble, a `same` pair, and a false-positive label, and checks every number in the report.
- What the harness does not do is stated in `eval/README.md`: it does not separate the roles and it prints no interval. Both wait on the confirmatory run.
- `VERSION` 0.5.15.

## v0.5.14 (2026-09-15)

Item 12 of `docs/ROADMAP.md`, the revision experiment.

- **`eval/study.py plan --task revise`** plans the question the tools exist to answer: does their feedback improve a draft more than another editing pass would? One starting draft per writer, five arms: `untouched`, `generic` (a self-review with no Pherkad input, the control, and required), `mechanical` (the findings of `pherkad.py check` and nothing else), `judgment` (the skill's quick-mode rules against the profile, every mechanical call disabled), `both`. `--repeats N` runs each arm N times on the same source so stability is measured. `prompts` writes one prompt per item with the right blocks (the mechanical arms carry the findings, the judgment arms the profile, the untouched arm is copied) and `--model` records what runs them. `sheet` shuffles the arms per writer under blind ids and asks for voice, a fidelity flag, useful and unnecessary edit counts, and minutes. `score` reports per writer and arm, with a flagged draft counting as a failure of its arm whatever its rating, and each arm's rating minus the generic arm's as the primary outcome, pooled across writers.
- **Provenance on every item**, in both tasks: the tool version, the effective rule set's hash, the profile's hash, the prompt's hash, and the model. A result can be traced to what made it.
- The authoring task is unchanged apart from the provenance fields; the two tasks share the writers, briefs, sheet, and ratings machinery. `eval/README.md` documents the revision task.
- `eval/test_study.py` gains an end-to-end run of the revision task in a temporary data directory: plan, missing-source report, prompts with the right blocks per arm, sheet, ratings, score with a flagged repeat.
- `VERSION` 0.5.14.

## v0.5.13 (2026-09-15)

Item 11 of `docs/ROADMAP.md`, surfaces, which closes phase 3.

- **A surface names what the text is**: who is speaking (`assistant` to the author, or the `author` as himself) and whether the positive register is expected (`no`, `profile`, `frame`, `yes`, or `own-voice-document`). Seven ship in `tools/surfaces/`, each an overlay with a `_surface` block carrying speaker, register, and guidance: `assistant-chat` (the chat rules; no marker expected), `technical` (`significant` and `robust` are terms of art, not filler), `email`, `post`, `paper` (register in the frame only; the statistical terms are not filler), `slides` (the interrogative-heading threshold drops to 18 percent, where decks were measured to separate), and `fiction` (the project's own voice document governs; the personal profile does not apply).
- **Layering.** `--surface X --config OVERLAY` applies the shipped base, then the surface's overlay, then the project's, in that order; the two flags are no longer exclusive. The saga gate now runs `--surface fiction --config <its overlay>`, so every gate names its surface.
- **A user map**, `surfaces.json` (or `--surfaces`, or `PHERKAD_SURFACES`), is consulted before the shipped set. It can add a surface with its own overlay, or point a shipped name at approved excerpts from the same series and extra guidance; `tools/examples/surfaces.json` shows the shape. `pherkad.py surfaces` lists every surface with speaker, register, guidance, overlay, and which excerpts exist. An unknown surface is an error listing the known ones; a bad speaker or register, or a missing overlay or excerpt path, is reported by name.
- **`SKILL.md` gains Step 0a, name the surface**: say it in the first line of any report, ask rather than infer when it is not obvious, and for authoring write beside the surface's approved excerpts for rhythm and register, never as a template. The positive-register table in quick mode now mirrors the surfaces' field, with `pherkad.py surfaces --json` as the authority.
- `replycheck` resolves its surface through the same path. `--format json` carries the surface, speaker, and register.
- `test_pherkad.py` grows by 8 surface cases.
- `VERSION` 0.5.13.

## v0.5.12 (2026-09-15)

Item 10 of `docs/ROADMAP.md`, the correction ledger.

- **`tools/corrections.py`**, new. A JSONL ledger, project-owned and never committed here, one record per correction: before, after, context, source, surface, kind, rationale, the proposed field and matcher, the examples, the trial, the status, and a history. `add` records a correction and classifies it (literal, templated, structural, judgment, preference, factual, exception; `--kind` overrides the guess), proposing the matcher and a `fires`/`clean` pair from the context. `trial` counts the candidate on a corpus with the pattern alone (under the full set a shipped rule wins a shared span on a tie and the candidate looks silent), stores hits, files, rate, and contexts on the record, checks the examples, and names any shipped rule that overlaps. `promote` refuses an untrialled rule, refuses a factual correction however often it recurs, and otherwise writes the overlay entry (an `add_<field>` object with id, rationale, since, fires, clean), which is where the fixtures live, and appends the mined-corrections line under a dated, sourced heading in the prose file; a judgment or preference kind gets the prose line only. `list`, `show`, `retire`.
- **The prose is generated from the record.** The ledger is the transaction log; the mined-corrections section is a view of it.
- **`pherkad.py check-overlay` runs an overlay's fixtures**, each rule alone, so a promoted correction's tests run wherever the overlay is checked.
- A promotion into the shipped base joins the list itself rather than an `add_`; the tool says to write the manifest, count it, and record it.
- `tools/test_corrections.py`, in CI. `corrections.jsonl` is gitignored beside the personal voice documents.
- `VERSION` 0.5.12.

## v0.5.11 (2026-09-15)

Item 9 of `docs/ROADMAP.md`, the compact judgment mode. A change to the skill's instructions, not to code.

- **Quick mode is the default depth of validation.** `SKILL.md` gains Step 0b (choose quick or full) and a Quick mode section: one run of `pherkad.py check --format json`, one read of the draft for the judgment-only rules that apply to its surface, and one table with a row per finding: `rule_ref`, `quote`, `decision`, `rationale`, `proposed_edit`. Decisions are `fix`, `intentional`, `literal`, `not applicable`, or `quoted`; only a `fix` row carries an edit. The verdict is one line. Nothing is scored, no fingerprint is produced, and nothing is rewritten that was not flagged. A confirmed `intentional` or `literal` row in a project with a decision file is recorded with `pherkad.py decide`.
- **Full mode is the audit**, Steps 1 through 6 unchanged, for a paper, an essay, a chapter, an explicit request for scores, or a quick pass that found the voice missing across the piece.
- **Positive markers apply by surface.** A table in Quick mode says where the positive register is expected: not in an assistant's reply, a technical answer, a bug report, a commit message, or a status email; in the frame and close of a post or letter; in the frame and transitions of a paper; never from the personal profile in fiction, which has its own voice document. `references/authoring.md` rule 5 says the same from the drafting side: a scene added to a technical answer to fit the profile is worse than none.
- **The blanket chat exemption is gone.** `references/ai_tells.md` now exempts informal messages between people, and names an assistant's reply as the `assistant-chat` surface, checked by `replycheck.py` and judged in quick mode.
- Step 3 of full mode runs `pherkad.py check --format json` once instead of two commands. The cheat sheet gains rows for the quick check, the combined CLI, and the reply preflight.
- `VERSION` 0.5.11.

## v0.5.10 (2026-09-15)

Item 8 of `docs/ROADMAP.md`, the release manifest and the overlay check, which closes row 12 of `docs/priority-fixes.md` and phase 2 of the roadmap.

- **`tools/bundle-manifest.json`**, new, written by `pherkad.py manifest --write` at release: the version, a schema number, the sha256 of every vendored file (the five a gate needs, plus replycheck, its hook, corpusscan, and the surfaces), and every rule id the shipped base runs. `pherkad.py manifest --verify` fails when a file beside the script no longer matches, when a file is missing or unlisted, when the version differs from `VERSION`, or when the rule ids differ from the shipped config. CI runs it, so a release that edits a tool and forgets the manifest fails its own tests; the first run of the test did exactly that.
- **`pherkad.py check-overlay OVERLAY`** loads a downstream overlay on the shipped base and reports what would silently do nothing: a `remove_<field>` naming a rule that is not here (error), an `add_<field>` duplicating a shipped rule (warning), a whole-list replacement where `add_`/`remove_` would inherit (warning), a structure key the base does not know (config error). The saga overlay checks clean; the shipped `assistant-chat` surface checks clean.
- **The saga's `sync-voicelint.sh --check`** now verifies three things: the six vendored files against its own sha record, pherkad's manifest against the copies, and the saga overlay against the vendored base. Any one failing exits non-zero, and `lint-voice.sh` reports it at the top of every run.
- `test_pherkad.py` gains cases for the new commands.
- `VERSION` 0.5.10.

## v0.5.9 (2026-09-15)

Item 7 of `docs/ROADMAP.md`, the decision file, which closes row 7 of `docs/priority-fixes.md` by giving a downstream corpus a way to triage its advisory warnings once.

- **`pherkad.py check --decisions FILE`** hides, and stops counting, every finding the author has ruled on. A decision is a record `{rule_id, path, context_hash, rule_hash, count, disposition, reason, decided}`: the context is the whole line the finding sits on with whitespace collapsed, the rule hash is the rule's pattern, and the record covers up to `count` occurrences on that line. A changed line, a changed rule, or an extra occurrence makes the finding new again. `--show-decided` prints the hidden ones; the summary reports `N decided (a accepted, b intentional, c deferred)` so the debt stays visible; `--format json` carries each finding's decision and `--format sarif` omits decided findings. Paths are relative to `--root`, default the decision file's directory.
- **`pherkad.py decide --decisions FILE --reason "..." path:line[:rule_id]`** is the only thing that writes a decision, and it refuses an empty reason and a location with no finding. Dispositions: `accepted` (the author's usage), `intentional` (a deliberate choice), `deferred` (known, fix later). Deciding a line covers every occurrence of that rule on it; naming a rule id covers that rule only.
- **`pherkad.py decisions --decisions FILE FILES...`** reports which records still match and why the others do not (line changed or finding gone, rule changed, rule gone); `--prune` drops the stale ones and nothing is pruned without it.
- **The saga gate passes `--decisions voice-decisions.json --root <repo>`** when that file exists at the repo root. It does not exist yet; the 293 advisory warnings and 6 errors there are the author's to rule on, one `decide` at a time, and nothing in the tool rules on them for him.
- `test_pherkad.py` grows by 11 decision cases.
- `VERSION` 0.5.9.

## v0.5.8 (2026-09-15)

Item 6 of `docs/ROADMAP.md`, the combined runner.

- **`tools/pherkad.py check`**, new. Runs voicelint and structlint over each file, folds the findings into one list in one schema (line, col, severity, rule, match, message, rule_id, engine), removes the overlap between the engines, computes one density over both, and prints one format: text, `--format json` (voicelint's envelope plus tool version, config sha256, and the advisory prefixes), or `--format sarif` (SARIF 2.1.0, advisory findings as `note`). `--advisory PREFIX` reports rule ids under a prefix without counting them, which is how a gate keeps the structural checks visible but non-blocking; `--strict`, `--no-structure`, `--quiet`, `--surface`, `--config`, and `-` for stdin as elsewhere. Exit codes are voicelint's. `pherkad.py rules` lists every rule both engines run.
- **Density is computed once**, over both engines' findings, against `structure.density_per_100`; structlint's own per-document density is dropped from the combined list. **Overlap**: a structlint `header` finding whose heading contains the text of a voicelint finding on the same line is the same tell twice, and the voicelint one, which names the rule, is kept.
- **`replycheck` runs on the shared core** (`pherkad.run_text`) and splits by engine; its verdict and output are unchanged.
- **The saga gate calls one command.** `lint-voice.sh` runs `pherkad.py check --config <overlay> --advisory structure.` in place of the separate voicelint and structlint steps, and no longer resolves a world-specific structlint path. `sync-voicelint.sh` vendors five files: `pherkad.py`, `voicelint.py`, `structlint.py`, `mdmask.py`, `voice_config.json`. The whole-tree run reports 6 errors, 293 warnings, 116 advisory, the same numbers the two steps gave.
- `tools/test_pherkad.py`, in CI.
- `VERSION` 0.5.8.

## v0.5.7 (2026-09-15)

Item 5 of `docs/ROADMAP.md`, the shared Markdown extraction layer, which closes row 4 of `docs/priority-fixes.md`.

- **`tools/mdmask.py`**, new. One reading of Markdown structure for both linters: `line_kinds(text)` classifies every line (code, blockquote, table, heading, field, list, blank, prose) and `mask(text, kinds)` blanks the named kinds, and inline code spans, to same-length whitespace so offsets never move. Fences are backtick or tilde, three or more, closed by a fence of the same character at least as long, or by the end of the file; a `>` inside a fence is code.
- **voicelint imports it** and now masks blockquotes as well as code. A quoted passage is someone else's words, which voice-rules.md exempts, and structlint already skipped it; the two tools no longer disagree on what is prose. Inline quotation marks are still linted: in fiction the dialogue is the author's voice, and adjudicating a direct quote stays with the judgment layer. On the saga corpus no finding sat on a blockquoted line, so voicelint's count is unchanged at 6 errors and 293 warnings.
- **structlint imports it** for code, blockquote, table, heading, field, and list detection, and drops its own copies of those regexes and its unused `QUOTED` constant. One consequence: an inline code span now keeps its width when a sentence is measured, where the old stripper collapsed it to one space, so a sentence that was only "short" because its code collapsed no longer counts. Two staccato findings on the saga corpus went away for that reason (118 to 116); both were sentences carrying a code span.
- The saga's `sync-voicelint.sh` vendors `mdmask.py` beside `voicelint.py`; a vendored voicelint without it fails at import, loudly, rather than running with less.
- `tools/test_mdmask.py`, in CI; voicelint gains cases for blockquote masking and for inline quotation staying prose.
- `VERSION` 0.5.7.

## v0.5.6 (2026-09-15)

Item 4 of `docs/ROADMAP.md`, the structlint fixes, which close rows 1, 2, 3, and 9 of `docs/priority-fixes.md`.

- **The two-beat check tests shape, not length.** Two short sentences count as a parallel only when they share an opener, both carry a negation, share a closing word, or have the same token count with a repeated content word. "The meeting starts at nine. Lunch follows at noon." no longer fires; "None of them wrong. None of them ours." still does. On the saga corpus two-beats went from 31 to 12, and every one of the 19 that vanished was an ordinary pair.
- **Spans are masked, lines are kept.** A URL, a DOI, an arXiv id, a year in parentheses, a page run, or a long quoted span is blanked in place and the rest of the line is still checked, so a staccato run beside a link is visible. A whole bibliographic entry (author-and-initial opener, or two or more markers) is still dropped as before.
- **Two header patterns tightened.** `The real X` and `The actual X` fire only on a stance noun (problem, question, issue, reason, point, story, answer, and so on), so `The actual results` is left alone; `Where X sits` needs an abstract or pointer subject (`Where this sits`, `Where Stage 3 Sits`, `Where the argument stands`), so `Where the chair sits` is a chair.
- **Thresholds are configurable**, in the same file voicelint reads, under a `structure` object with the same overlay semantics: `short_chars`, `two_beat_diff`, `staccato_run`, `density_per_100`, `interrogative_pct`, `interrogative_min`. The shipped `voice_config.json` carries the defaults; `structlint --config OVERLAY` and `replycheck` pick up an overlay's values; voicelint validates the object and rejects an unknown threshold.
- **Findings carry voicelint's shape**: line, col, severity, rule, match, message, rule_id, with ids `structure.<check>`. The text line reads `path:line:col [warning] two-beat (structure.two-beat): ...` and `--json` uses voicelint's `{"suppressed", "files"}` envelope, so one consumer reads both tools. `excerpt` remains as a read-only alias.
- `test_structlint.py` grows from 23 to 42 tests: a case for each false positive above, for each threshold, and for the finding shape.
- `VERSION` 0.5.6.

## v0.5.5 (2026-09-15)

Item 3 of `docs/ROADMAP.md`: the corpus scan and release diff, so the count that every rule change is supposed to carry is one command rather than an afternoon.

- **`tools/corpusscan.py`**, new. `scan DIR...` counts every rule over a corpus (hits, files, hits per 1,000 words, sorted); `--rule ID` narrows to one rule with sampled contexts; `--candidate "field:pattern"` (or a JSON rule object) tries a rule that is not in the config yet, and refuses one that already is. `diff DIR --old A.json --new B.json` runs two base rule sets under the same overlay and reports rules added, removed, and renamed (same pattern, new id), per-rule deltas, and the findings that appear and vanish, with contexts for the new ones. `--json` adds the tool version, the sha256 of every config involved, and the corpus size, which is what a dated snapshot should keep. Every number is labelled a raw hit; nothing promotes a rule.
- **`voicelint.load_config(path, base=...)`** takes another base file, for the corpus tools only. The linter's own CLI still always runs the shipped base, so a vendored copy cannot be pointed at a stale one.
- Today's calibration reproduced by the tool, the 0.5.1 rule set against 0.5.5 on the saga's shareable tree (202 Markdown files, 273,455 words, saga overlay, both run under the current linter so only the rule changes show): errors 6 to 6, warnings 300 to 293, 62 findings appear and 69 vanish; 15 rules added, 21 removed, 5 renamed. The hand count earlier today read 313 to 294 because it also carried the 0.5.2 and 0.5.3 code changes (overlap collapse, directive blanking). The three `named` soft phrases from `docs/priority-fixes.md` row 7 score 0 hits on the corpus and stay.
- The count command is in the repository `CLAUDE.md`, so a rule change without a count is a visible omission.
- `tools/test_corpusscan.py`, 11 tests, in CI.
- `VERSION` 0.5.5.

## v0.5.4 (2026-09-15)

Item 2 of `docs/ROADMAP.md`: the reply preflight, for the gap where nothing checked an assistant's chat replies.

- **`tools/replycheck.py`**, new. Both scanners over a drafted reply under a surface overlay, one line per finding, a verdict (`PASS` exits 0, `FIX` exits 1, could-not-run exits 2), `--strict`, `--json`, `--no-structure`. Structural findings are advisory and never change the verdict; a checker that fails every terse answer gets switched off.
- **`tools/surfaces/assistant-chat.json`**, new. An overlay for an assistant speaking to the author: the demonstrative pointer, `worth noting` and `worth saying`, question praise, markdown links, tilde paths, the section sign, the `plainly` tag, the coy withhold. Each rule carries an id, a rationale, and examples the tests run. Chat-only rules live here so the shipped defaults stay general.
- **`tools/replycheck-hook.py`**, new. A Claude Code `Stop` hook: reads the assistant text since the last human message from the transcript, runs the same check, and on an error exits 2 with the findings so the assistant sends a corrected follow-up. One enforced revision per reply (`stop_hook_active` is honoured), warnings block only under `REPLYCHECK_STRICT=1`, and a hook that cannot read its input exits 0 rather than wedging the session.
- **`banned_phrases` and `engagement_bait` accept `re:` patterns**, as `soft_phrases` already did, with no word-edge guard on a regex. A banned finding's message shows the rule's rationale when it has one.
- **`docs/reply-preflight.md`** and a repository `CLAUDE.md` carry the recipe: draft to a file, check, revise at most three times, send the exact buffer that passed, and a check that did not run is not a pass. The habit it will keep catching is quoting a banned phrase in plain quotation marks; backticks are masked.
- Evidence from the session that built it: two of eight long assistant replies would have been sent back, all on quoted examples.
- `tools/test_replycheck.py`, in CI.
- `VERSION` 0.5.4.

## v0.5.3 (2026-09-15)

Item 1 of `docs/ROADMAP.md`: stable rule ids, as additive metadata. The string lists and the `add_`/`remove_` contract are unchanged, so a vendored copy and its overlay keep working as they were.

- **Every rule has an id.** A string entry derives one from its pattern (`banned.game-changer`, `soft.worth-more-to-word-than`; a regex gets `soft.re-<8 hex>`); two strings that slug alike (`gut-check`, `gut check`) stay distinct. The fixed rules are `dash`, `dash-density`, `load-bearing-context`, `honest-framing`, `loaded-adverb`, `overuse.<word>`, and `source.<domain>`.
- **An entry may be an object** `{"id", "pattern", "rationale", "since", "fires", "clean"}`. The five shipped regex rules are now objects with ids (`soft.mystery-tail-no-way`, `soft.mystery-tail-never-said`, `soft.mystery-tail-could-not-say`, `soft.abstract-landscape`, `soft.authenticity-tag`), a rationale, and examples. The test suite runs every `fires` and `clean` example, so a rule with examples is a tested rule. A duplicate explicit id, an unknown key, or a missing pattern is a config error.
- **Findings carry `rule_id`**, in the JSON and in the text line (`soft-cliche (soft.abstract-landscape)`). A soft finding's message shows the rule's rationale when it has one, instead of the raw regex.
- **`remove_<field>` accepts an id**, so an overlay drops a shipped regex without pasting it. `add_<field>` skips an entry whose id or pattern is already present. An inline `ignore-line` can name an id as well as a family.
- **`--list-rules`** prints every rule the effective config runs (id, family, severity, pattern, rationale), or the same as JSON with `--json`.
- A read directive comment is blanked before matching, so `ignore-line banned.game-changer` no longer lints its own words.
- The saga corpus reports 6 errors and 293 warnings against 0.5.2's 294, with 4 suppressed against 9: the five findings that used to fire on directive comments and then be suppressed are gone, and so is one that fired inside an allow-comment's own text and was never suppressed.
- `VERSION` 0.5.3.

## v0.5.2 (2026-09-15)

The second half of the Codex review: the rule-level bugs, then a calibration of the shipped set against a 200-file downstream corpus. Everything in the calibration was counted before it was kept.

- **The honest-framing error covers the family voice-rules.md states**, `[det] honest [adj] NOUN` with the nouns that name an utterance (answer, take, look, note, framing, part, case, move, position, summary, and so on), plus the copular form `[det] honest NOUN is that` whatever the noun. It had been twelve literals beginning "the", so `One Honest First Look` and `the honest obstacle is that` walked past it. Subject-matter nouns (broker, assessment, accounting) do not fire, and the broad `honest \w+` warning is gone: 39 corpus hits, most of them literal adjectives.
- **Overlapping phrase hits collapse to one finding.** `This is what it buys you` produced four warnings for one tic. Errors beat warnings, the longer match wins at equal severity, and the counting rules (overuse, dash density, source, load-bearing context) are left alone so a soft phrase cannot swallow a real count.
- **`voicelint-allow` matches whole words.** Allowing `land` used to silence a `landscape` finding.
- **A numeric en-dash range is not a dash hit.** `Pages 10–12` was an error; the prose rule allows it.
- **`[verb]` means a gerund.** `worth nothing` no longer matches `worth [verb]`. `it is worth noting` is banned with or without `that`.
- **Calibration, dropped:** `the one that` (25 corpus hits, all ordinary relative clauses), the bare `lands at/in/on` and `land here/there` placement forms (the plane lands at noon), the good/great/fair-question block. `landscape` is narrowed to the abstract forms (`the current landscape`, `landscape of`). `rhymes with` and `the mirror image of` are warnings, since their literal senses were errors. Kept on the evidence: `is the whole`, `is the point`, `the part that`, `the thing that`, 136 corpus hits that read as the announcing-significance tell.
- **Calibration, added**, the bans voice-rules.md states that nothing enforced: `important` and the boosters (`very`, `really`, `extremely`) as filler; `in all honesty` banned; `frankly`, `candidly`, `truthfully`, `to be honest` warned in their comma-tagged form only (bare `answers it truthfully` is literal); `the truth is,` as bait in its comma form only (`the truth is stupider than the myth` is a sentence); `moreover`, `furthermore`, `in recent years` as warnings; clause-final `quietly` on by default rather than opt-in.
- Net on the corpus: warnings 313 to 294, errors 1 to 6, every new error a real instance of the honest-framing tell.
- `VERSION` 0.5.2.

## v0.5.1 (2026-09-15)

A Codex review of the tools, recorded in `docs/codex-review-2026-09-15.md`, found four correctness bugs. This release fixes those four and nothing in the rule set; the calibration findings in that review wait on a separate decision.

- **The Python copy of the defaults is gone.** `voicelint.py` carried a `FALLBACK_CONFIG` that had drifted from `voice_config.json` (13 soft phrases against 115, 26 banned phrases against 34), and every `--config` was merged onto that stale copy rather than the shipped file. Any user config, however small, silently ran with a fraction of the rules. The shipped JSON beside the script is now the only base; a missing base exits 2 instead of running with less. The overlay is `--config`, or `./voice_config.json` in the working directory when it is a different file. `--print-config` prints the effective set.
- **The `rules-file` marker is read after code masking**, and only as an HTML comment on its own line. Before, the marker inside backticks, or mentioned in a sentence, silenced the whole file.
- **Fence masking covers tilde fences and unclosed fences.** A tilde block was linted as prose, and an unclosed backtick fence, which Markdown renders as code to the end of the file, was too.
- **Suppression directives survive HTML stripping.** `strip_html` removed every comment, so `ignore-line` and `voicelint-allow` did nothing in an `.html` input.
- **`frame` leaves the load-bearing exempt set.** The comment above the set already named "load-bearing frame of the argument" as the figurative case; the set contradicted it. It now draws the context warning like any other non-structural object.
- **`eval/study.py` scores the letter you typed.** Forced-choice picks resolved to the row the letter sat on, so entering `b` on row `a` counted as picking `a`. A pick now resolves to the named candidate; an unknown letter, two conflicting picks for one writer, or a rating outside 1 to 5 stops the run rather than scoring a guess. `eval/test_study.py` covers it.
- **Both test files are real `unittest` suites**, collected by `python3 -m unittest` and by pytest, with the old direct invocation unchanged for CI. The prior scripts ran at import time and were invisible to both runners. Every bug above has a regression case.
- `VERSION` 0.5.1.

## v0.5.0 (2026-08-20)

A structural checker joins the linter. `voicelint` matches phrases; the families that actually sink a draft have no string to match, and `voice-authoring.md` has said so since 2026-08-15 under "The linter is the last check, not the check" without anything enforcing it. Guidance lost to the default register in practice, so it becomes a tool.

- **`tools/structlint.py`, new.** Four checks with nothing to grep for: the clipped balanced parallel, a run of three or more short sentences, a header that strikes a pose rather than naming its subject, and density. Everything is a warning, because these are judgment calls that over-fire by design, and the output is a list for a glance rather than a verdict.
- **It reads paragraphs, not lines.** Hard-wrapped markdown puts one sentence across several lines, and a line-by-line read saw a sentence ending mid-line as a two-beat that was not there. Blockquotes, list items, bold run-in labels and clauses ending in a colon are all skipped for the same reason: a checker that cries wolf gets ignored.
- **`tools/test_structlint.py`, new**, wired into the test workflow beside the voicelint suite. The negative cases outnumber the positive ones, which is the right ratio for a tool whose failure mode is noise.
- **The land heuristic is merged into `voice_config.json`**, closing a queued item, and rescoped. The queued version covered the "it did not land with the team" sense and caught 5 of 71 metaphorical uses in a real corpus; the dominant construction is "X lands somewhere."
- **`actually` and `silently` become watch words capped at two per document** rather than bans. Both already had rules with no tooling. A ban on `silently` would have broken "silent failure," which is literally true of software.
- **Soft phrases added** for the empty-emphasis frame, the forward pointer, the named-nominalization, and the "what it buys you" sales register.
- **`carries` deliberately did not get a phrase ban.** Four of five uses in a real corpus's titles were precise; the header check catches the abstract one and leaves the rest.
- `VERSION` 0.5.0.

## v0.4.9 (2026-07-24)

A third Codex round refined the evaluation design. The verdict has held across rounds (a sound advisory tool, the judgment layer unproved), so this closes the doc-review loop; the remaining work is running the study, not editing it.

- **The primary outcome is a paired within-writer contrast.** The 0.4.8 "frozen" outcome still averaged authentic and flattened items together, which cancels the two cases the study exists to separate. It is now the discrimination margin (authentic rating minus flattened rating, and authentic minus impostor) under the correct profile minus the same margins under the pooled controls. The estimand matches.
- **Reader reliability is a measured outcome.** Added to the metrics: writer-versus-reader and reader-versus-reader agreement on the blind pairwise judgments, with uncertainty and a fixed rule for disputed pairs. The human reference is only as good as its agreement.
- **The harness and the protocol are told apart.** `eval/README.md` now states plainly what `study.py` implements (correct/wrong/none, one rater, one run) and what stays manual (shuffled control, validation case types, repeated runs, multiple readers), so "the harness scales to it" is not read as "it is implemented."
- **A failed holdout is diagnosed, not auto-widened.** `profile_builder.md` no longer says "widen them" on a missed holdout; it revises a marker only if a fresh control shows better authentic recognition without accepting an impostor, since widening trades specificity for recall.
- `VERSION` 0.4.9.

## v0.4.8 (2026-07-24)

A second Codex round on 0.4.7 confirmed the earlier fixes and found four smaller things. All docs.

- **The verdict map covers every state.** REVISE listed a voice dimension at 3 and a missing-markers score at 2 or below, but not one off-profile dimension at 2 or below for any other reason, while REWRITE needs two or more. REVISE now includes "exactly one voice dimension at 2 or below," so no score pattern falls through.
- **The blind-eval primary outcome is one frozen formula.** It said "mean rating (or discrimination margin)," which is two outcomes. The primary is now the mean 1-to-5 rating, correct profile minus the equally weighted controls, with the discrimination margin and any verdict score named as secondary and a fixed verdict encoding if one is used.
- **The local holdout runs blind.** Step 4b listed each case beside its expected verdict, so a validating pass could return the expected answer from the cue. The check now shuffles the items, strips the labels and expectations from the validating pass, and reveals them only for the comparison.
- **The cheat sheet stops promising fidelity it cannot enforce.** "Facts ... stay exactly as you had them" is now stated as a requirement to check, not a guarantee, since nothing enforces exact preservation and rewrite fidelity is still an unmeasured outcome.
- `VERSION` 0.4.8.

## v0.4.7 (2026-07-24)

A cross-vendor review (Codex, GPT-5.6) caught issues the Claude reviews missed. All docs.

- **Sample count matches the holdout.** The profile builder reserves one sample before extraction (0.4.6), but the docs still said "3 to 5 samples," which leaves only two to build from at the low end. README, `profile_builder.md`, and both cheat sheets now say at least four (five or more for multiple registers), with one reserved.
- **The eval harness stops overclaiming.** `eval/README.md` opened by calling itself "the harness that turns ... into a result you can trust," but `study.py` is a blinded single-rater pilot, not the confirmatory study. The opening now says so and points to `docs/blind-eval.md` for the multi-writer design.
- **Flattening no longer strips content.** The holdout and blind-eval flattening steps said "remove personal examples," but examples are often the evidence, so removing them confounds a thinner text with a flatter voice. Both now preserve facts and concrete examples, neutralize only framing, syntax, hedging, transitions, and rhythm, and require a facts-and-detail equivalence check before a flattening is used.
- **The blind-eval protocol has a preregistration.** `docs/blind-eval.md` gains an estimand, the writer as the analysis unit, the primary-outcome formula, an interval method, a multiplicity rule, a power statement, and fixed failure criteria, all set before the run.
- `VERSION` 0.4.7.

## v0.4.6 (2026-07-24)

A review confirmed the mechanical layer is sound and put the weight on the judgment layer, the holdout, and the evaluation design. This pass is docs and one test, no linter code.

- **Provenance residue removed.** README no longer says Pherkad "makes it visible" or that a failure means "the machine's habits crept in"; a REVISE or REWRITE is described as a weak profile match or too many configured patterns, never as evidence of how a draft was produced. `SKILL.md`'s central line is now "run a structured review of whether written output matches one specific person's voice profile," Dimension 5 is "Generic or flattened patterns," and the output heading is "GENERIC OR FLATTENED PATTERN FLAGS."
- **Score anchors and an explicit verdict map.** The seven dimensions now share a stated 1-to-5 anchor scale, so a score is reproducible rather than a feeling, and the PASS/REVISE/REWRITE rules are tied to specific dimension scores and signals instead of "a handful" or "heavy hits."
- **The profile holdout is repaired.** The holdout is chosen and isolated before markers are extracted (a read sample cannot be made unseen); a failed holdout is spent, so a profile changed to fix it is confirmed on a new untouched sample; the flattened rewrite is produced by an editor or model blind to the profile, preserving facts and order within 10 percent length, not by deleting the profile's markers; and the impostor check uses several closely matched writers.
- **The blind-eval protocol became a study design.** `docs/blind-eval.md` now leads with correct-profile lift (run every item under the correct, a wrong, a shuffled, and no profile, plus linter-only) as the primary result, since a pass proves nothing if the wrong profile does as well. Added within-writer register coverage, independent blind flattening with at least two variants, several hard impostors, external blinded pairwise reader judgment, role separation across model families, frozen definitions (light REVISE, run count, model and sampling, stability, thresholds), a twelve-item measurement list, an authoring arm, and pilot-versus-confirmatory sizing.
- **Test.** Added a regression case that an empty watch-word key exits 2.
- **Evaluation harness.** New `eval/study.py` and `eval/README.md`: a blinded voice-authoring study that measures correct-profile lift (a draft written with the writer's own profile against wrong-profile and no-profile controls, plus a real held-out anchor), the concrete way to run the `docs/blind-eval.md` design. Data lives under `eval/data/` and is gitignored; the code and protocol are shareable.
- `VERSION` 0.4.6 (the eval harness is repo tooling, not part of the skill bundle).

## v0.4.5 (2026-07-24)

A fourth review found the mechanical layer sound and pointed the real work at the judgment layer. This pass closes the remaining linter holes, stops the linter and docs from implying provenance, and starts the highest-value work: evidence that the "sounds like you" verdict generalizes.

- **Config validation is semantic, not just structural.** A negative watch-word cap (which used to crash at runtime) and an empty configured phrase (which used to match at every character) are now rejected with exit 2, along with empty watch-word keys. A validated config no longer reaches a runtime failure or a match-everywhere rule.
- **Suppression is comment-scoped and code-aware.** A `voicelint: ignore` directive is recognized only inside an HTML comment, and directives are read from the code-masked text, so a backticked or in-prose token can no longer silence a real finding.
- **`load-bearing` is warning-only.** A regex reading one word cannot tell `load-bearing frame of the argument` (figurative) from `load-bearing case` (a literal enclosure), so the hard-error tier is gone. A clear physical member is exempt; everything else is a soft `load-bearing-context` warning, and whether an ambiguous use is really figurative is left to the judgment layer.
- **Provenance language removed.** The linter and docs no longer imply they detect AI authorship. README leads with "helps you review whether a draft still sounds like you"; `SKILL.md` surfaces "generic phrasing" rather than "AI-generated flatness"; `profile_builder.md` and `ai_tells.md` describe positive markers as evidence of profile match, not of how a passage was produced. A hit or a verdict is about voice fit, never about provenance.
- **Profile holdout check.** `profile_builder.md` gains Step 4b: reserve one sample the profile never saw, then confirm the profile recognizes it, revises a flattened rewrite of it, and does not accept another writer's piece, before the profile is trusted. It catches an overfit profile that only matches its own extraction set.
- **Blind-evaluation protocol.** New `docs/blind-eval.md`: the plan for the multi-writer blind set that would move the judgment layer from advisory to dependable, with the case types, the run method, the pass bar, and a requirement to report failures. The protocol is written; the dataset needs real samples. `docs/review-followups.md` is updated to match.
- `VERSION` 0.4.5.

## v0.4.4 (2026-07-24)

A third external review found an over-correction from 0.4.3 and several older bugs. This pass grades `load-bearing` instead of guessing, hardens the config loader, makes the linter safe for real technical and multilingual prose, and adds a way to silence a checked false positive.

- **`load-bearing` is graded in three tiers.** 0.4.3 over-corrected: `member`, `frame`, and `assembly` are ordinary engineering nouns but were hard-errored as figurative. Now a physical member (wall, beam, column, joist, truss, slab, stud, lintel, girder, rafter, member, frame, assembly, footing, pier) is exempt; a clear argument word (argument, assumption, claim, thesis, premise, idea, reasoning, logic, case, and the like) is an error; everything else, including ambiguous nouns and predicate use, is a soft `load-bearing-context` warning that asks for a look rather than declaring the metaphor.
- **The mathematical minus sign is no longer called a dash.** U+2212 left the prose-dash set, so `5 − 3` does not raise a dash error.
- **Decomposed Unicode is handled.** The phrase-edge guard now counts combining marks (category M) as part of the preceding letter, so a phrase after an NFD accent no longer slips the boundary.
- **Config validation is strict.** Boolean fields (`no_dashes`, `flag_loaded_quietly`, `load_bearing_literal_only`) are type-checked, and an unknown top-level key (a typo like `no_dash`) is rejected with exit 2 instead of silently ignored. Comment keys still start with `_`.
- **No shared mutable default state.** `load_config` and the deep-merge now `deepcopy` the built-in fallback, so mutating one returned config cannot bleed into the next load (matters for imports and tests, not the one-shot CLI).
- **Hostname matching tolerates a trailing dot.** A fully qualified `www.msn.com.` now matches; path, query, and userinfo still do not. Only scheme-bearing URLs are scanned, and that limit is documented.
- **Inline suppression.** A `voicelint: ignore-line` or `voicelint: ignore-next-line` directive (optionally naming rules) silences a checked false positive; the summary and JSON report the suppressed count. This gives the standalone linter a real answer for a legitimate quotation or term instead of "the model will sort it out."
- **JSON output shape.** `--json` now returns `{"suppressed": N, "files": {path: [findings]}}` rather than a bare path map, so a consumer can see suppressions. A breaking change for anyone parsing the old top-level map.
- **Honest defaults and docs.** The news-brief closers (`that's the news`, `watch the move`, `note the framing`, `read this under`, `is the move`) moved from the generic defaults to `examples/news-brief.json`. `SKILL.md` describes the linter as heuristic where it is heuristic and drops "final quality gate" for "final advisory review." The stale example comments and the `review-followups.md` opening are corrected.
- `VERSION` 0.4.4.

## v0.4.3 (2026-07-24)

A second external review caught two regressions from 0.4.2 and three older bugs. This pass fixes the mechanical layer to match its own release notes and pulls source-quality policy out of the generic defaults.

- **`load-bearing` regression fixed.** 0.4.2 widened the literal exemption too far: `structure`, `capacity`, `member`, `frame`, and `assembly` read as metaphor as often as engineering (`the load-bearing structure of the argument`), so they wrongly silenced the tell. The exemption is now only unambiguously physical members (wall, beam, column, joist, truss, slab, stud, lintel, girder, rafter); figurative use fires again.
- **Density floor regression fixed.** The linter's dash-density warning still used a 100-word floor while `SKILL.md` and the changelog said 150. The linter now requires 150+ words and 3+ dash hits, matching the judgment layer.
- **Domain matching reads the host, not the whole URL.** The old regex flagged an aggregator name anywhere after `https://`, so `https://example.com/path/msn.com/story` fired on `msn.com`. Matching now parses the hostname with `urllib.parse.urlsplit` and compares host suffixes and labels, so a domain in the path or query is ignored.
- **Phrase edges are Unicode-aware.** The 0.4.2 boundary guard used an ASCII character class, so a phrase wedged between accented letters slipped through. The guard now tests the neighboring character with `str.isalnum`, which is Unicode-aware.
- **Source policy left the generic defaults.** `aggregator_domains` is now empty and the `live` watch word is gone from `voice_config.json` and the built-in fallback; both live in `examples/news-brief.json`. Source provenance is not voice, so it should not ship as a generic voice rule.
- **Tests and honesty.** Added regression cases for the ambiguous-noun `load-bearing`, the 149/150-word and 2/3-hit density thresholds, host-versus-path domain matching, and Unicode edges. The "covers every rule and promised exception" claim is corrected to "core rules, CLI behavior, and documented examples," and the test docstring says plainly that the judgment layer is not tested here.
- **Doc accuracy.** README and the cheat sheet now describe the real exit-code contract (a warning exits 0 unless `--strict`; usage, IO, and config errors exit 2). README's provenance section is retitled Origins and no longer implies public validation. `SKILL.md` Step 3 asks for each sentence with a *supported* tell, not "every" tell.
- `VERSION` 0.4.3.

## v0.4.2 (2026-07-24)

Correctness pass on the mechanical linter after an external repo review, plus honest-scope wording in the docs. The linter now overreaches less and the judgment layer keeps the calls it should keep.

- **Phrase matching respects word boundaries.** A banned or engagement-bait phrase whose edge is alphanumeric is now guarded, so `is the move` no longer fires inside `movement`. Punctuation-edged phrases (`picture this:`, `in conclusion,`) still match as written.
- **Code spans are masked before matching.** Fenced blocks and inline `code` become same-height whitespace, so a doc can name a banned phrase in backticks without tripping the linter. Line and column offsets are unchanged. Ordinary quotations are deliberately not exempted; adjudicating a direct quote stays with the judgment layer.
- **`load-bearing` recognizes real structural context.** The literal exemption widened past `walls` to beams, columns, members, structures, assemblies, capacity, joists, trusses, slabs, frames, studs, lintels, and girders. Figurative use still fires.
- **`flag_loaded_quietly` is off by default.** Clause-final position alone cannot separate an insinuating `quietly` from a plain manner adverb (`shut the door quietly`), which produced false positives. It is now an opt-in house rule; overuse is still caught by the `quietly` watch word, and the pre-modifier case stays in `references/ai_tells.md`.
- **Config deep-merges.** A user config now merges onto the defaults key by key: setting one entry in `watch_words` no longer wipes the others. New `add_<field>` / `remove_<field>` keys amend a shipped list without restating it. `examples/relaxed.json` demonstrates both.
- **Density needs a floor of text.** The judgment-layer density verdict (`SKILL.md` Step 4) applies only to a draft of 150+ words with 3+ findings, so a lone hit in a short passage no longer forces a REVISE against the stated lone-hit calibration. The linter's dash-density warning gained the same floor.
- **Tests and CI.** `tools/test_voicelint.py` rewritten as a table-driven suite over the core rules, CLI behavior, and documented examples (boundaries, load-bearing context, code masking, dash and density modes, deep-merge and list ops, domain matching, HTML stripping, JSON, `--strict`, exit codes, invalid config, line/column). A new `.github/workflows/test.yml` runs it on Python 3.8 through 3.12 on every push and pull request.
- **Honest-scope wording.** README no longer says "flags every tell" (now "checks the full catalog"); "the validator gets more accurate with use" became "a later run applies the recorded correction"; the module and `--help` descriptions and `ai_tells.md` no longer claim to detect provenance; the self-lint claim now names its scope (README and the cheat sheet).
- `VERSION` 0.4.2.

## v0.4.1 (2026-07-17)

- **Split profiles.** Pherkad loads `voice-rules.md` and `voice-authoring.md` from the working folder when present, alongside `Voice_Profile.md`. A profile can split across the three (personal markers in the profile, bans in `voice-rules.md`, drafting guidance in `voice-authoring.md`), so a writer keeps one canonical copy of each rule instead of duplicating them into the profile.
- `SKILL.md` Step 0 and `references/authoring.md` load the companion files.
- `VERSION` 0.4.1.

## v0.4.0 (2026-07-17)

- **Authoring mode.** Pherkad now drafts and rewrites in the writer's voice, not only validates. New `references/authoring.md`: write from the profile's positive markers, avoid the product-marketing register by default, choose words by a meaning-versus-decoration condition rather than a fixed list, restore the writer's hedging, anchor in a concrete witnessed detail, and self-validate the draft before returning it.
- `SKILL.md` gains a Modes section: validation (Steps 0 to 6) and authoring (`references/authoring.md`), both reading the same `Voice_Profile.md`.
- Weighted preferences are documented as authoring guidance and corpus-level monitoring, never a per-document lint rule, since a ratio is not checkable in a single document.
- `VERSION` bumped to 0.4.0.

## v0.3.1 (2026-07-17)

- **voicelint: the "quietly" rule now flags the trailing position, not the pre-modifier.** A pre-modifier "quietly + verb" ("quietly building") cannot be told mechanically from a legitimate stance ("quietly skeptical," "quietly noticing"), so the old rule fired on good prose. The linter now flags "quietly" only when it ends a clause or sentence ("shut it down quietly," "the numbers moved quietly"), the insinuating position that implies concealed intent. The pre-modifier case moves to the judgment layer in `references/ai_tells.md`.
- `references/ai_tells.md`: the single loaded-adverb line splits into a mechanical trailing-quietly entry and a judgment-layer pre-modifier entry.
- Added `tools/test_voicelint.py`, a dependency-free regression test that locks in the trailing-versus-pre-modifier behavior plus core smoke tests.
- `VERSION` bumped to 0.3.1.

## v0.3 (2026-07-16)

- **Positive register: calibrate toward, not only against.** `references/ai_tells.md` gains a Positive register section. Validation now reads whether a draft carries the writer's own distinctive markers, not only whether it is clean of tells. A draft clean of every tell but showing none of the writer's markers has flattened toward a generic default, and that is a REVISE-level signal in its own right. Generalized from a private single-writer rubric; the examples (concrete before concept, flat consequence, the telling detail, owned not deflected) describe the shape, and the profile carries each writer's own version.
- **Genre calibration.** Added to `references/ai_tells.md` and the skill's Calibration notes: distinctiveness lives in the frame, the transitions, and the close, while the analytical, legal, or technical core stays plain and precise and must not be flagged for failing to be vivid. A finished piece is often deliberately uneven by design, a distinctive frame around an exact middle.
- `references/profile_builder.md`: new Step 2b captures the writer's positive markers (the archetype), so a profile records what the voice does, not only what it bans.
- `skills/pherkad/SKILL.md`: Step 3 and the Calibration notes wire the positive-register read and genre calibration into the diagnostic and the verdict.
- Added a `VERSION` file (0.3.0) so an install self-identifies.

## v0.2 (2026-07-15)

- **voicelint: soft-cliche warnings.** A new warning layer for phrasings that are hard to ban outright but recur far too often in AI-assisted text. New `soft_phrases` config field, matched as warnings rather than errors, with readable placeholders: `[word]` matches one token, `[verb]` matches a gerund. Seeded set: `it's worth [verb]`, the `I want to be plain / clear / honest / upfront / direct / transparent` opener family, `gut-check` and `gut check`, `where your [word] lives`, `names a way`, and `the [word] that never bends`.
- A soft hit that lands on a stronger banned phrase (for example `it's worth noting that`) is dropped as redundant, so the phrase reports once, as an error.
- Config validation now covers `soft_phrases`. Warnings still exit 0 unless `--strict`, so the layer is safe in CI.
- Reworded the two cheat-sheet footer labels the new rule flagged in Pherkad's own docs (`Where your data lives` -> `Your data`, `The rule that never bends` -> `The one rule`), so `README.md` and the cheat sheet still exit 0 under the default linter (the scope CI checks; the changelog and catalog quote the patterns by name and are exempt).

## v0.1 (2026-07-15)

First public version, generalized from a private single-writer validator.

- Split the validator into a generic engine and a personal voice profile. The engine (SKILL.md protocol plus `references/ai_tells.md`) ships here; the profile is built per user and never enters the repo.
- `references/profile_builder.md`: a short interview that builds `Voice_Profile.md` from 3 to 5 real writing samples, every marker backed by a quoted sentence. Corrections append over time.
- `references/example_profile.md`: a fictional persona (Rosa Vantani, field ecologist) showing the profile shape, including catalog overrides (deliberate em dash use, domain vocabulary exemptions).
- Tell catalog carried over intact: categories 5a-5i, the density meta-rule (2.0 flagged constructions per 100 words), cluster warnings, and the caveats (technical-literal uses, quotes, single instances, the validator-internals exception). At the judgment layer, em dash flagging is profile-conditional: full flagging unless the profile shows deliberate dash use with evidence.
- All references to the original writer's private source documents removed; personal markers replaced by the profile mechanism.
- Merged in **voicelint** (`skills/pherkad/tools/voicelint.py`), a dependency-free mechanical linter for the regex-able subset of the catalog, from a working draft built for a different project. The full observed rule set ships as the defaults (hard dash ban, banned phrases, watch-word caps, source-domain list); every rule was built from tells seen across many AI-assisted documents, not one writer's preference, so none of it was demoted in the generalization. Defaults also gained the catalog's generic tells (scene-setting openers, engagement bait). What generalization added instead is a documented relaxation path: `tools/examples/relaxed.json` shows loosening a default the writer's profile contradicts (with the dash-density cap replacing the hard ban for deliberate dash users), `tools/examples/news-brief.json` shows team-specific additions, and any relaxation should match an evidence-backed override in `Voice_Profile.md` so the linter and the judgment layer agree. The skill's Step 3 runs the linter first when Python is available; the profile builder can emit a personal config.
- Catalog additions from the voicelint rule set: self-narrating closers, reader stage-directions, analogy connectives, loaded adverb + verb, and crutch-word overuse.
- Meaning guardrail on rewrites, from the voicelint rules doc: a voice edit never adds or drops facts, names, numbers, dates, or sources, and preserves emphasis.
- README gained two author sections: **Why these defaults** (the rules come from tells observed across many AI-assisted documents, they ship strict, and customizing to purpose is a JSON edit away) and **Why this exists** (informed use of AI lets people on the fence write and build things they would not otherwise have tried; the fix for flattened prose is knowing what the tools do to your sentences, not abstaining).
- One-page cheat sheet in `docs/` (`CHEATSHEET.md`, `.html`, `.pdf`): every mode, what to say, what you get, matching the Kochab cheat-sheet format.
- Repo scaffolding: README, MIT LICENSE, `build.sh` (one-command packaging of `pherkad.skill`).
