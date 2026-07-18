# Authoring mode

Pherkad has two modes. Validation, the rest of this skill, checks a draft against the writer's profile. Authoring, described here, drafts or rewrites prose in the writer's voice in the first place. Same profile, same tell catalog, run forward instead of backward. Loading this skill should let the model write as the user, not only grade what it wrote.

## When to use

- The user asks for a draft, a rewrite, or "write this in my voice."
- Any extended prose the user will send or publish as themselves.
- As the default posture for user-authored text once a `Voice_Profile.md` exists.

## Precondition: the profile

Authoring reads `Voice_Profile.md` from the working folder, the same file validation uses. Without it there is no voice to write in; run `references/profile_builder.md` first. Do not author against a generic default and call it the user's voice.

## How to draft

1. **Write from the positive markers, not only away from the tells.** Lead with the profile's owned vocabulary and its archetype moves, the Positive register. A draft that merely avoids every tell still flattens toward a competent generic default. Absence of tells is necessary, not sufficient.

2. **Match the register the profile names, and avoid the pitch register by default.** The most transferable register rule across writers: prose that sounds like product marketing is almost never a personal voice. If a sentence would be at home in a product launch, a sales deck, or a landing page, it is the wrong register even when every individual word is allowed. Write as a person reporting from inside the work, not selling its outcome.

3. **Choose words by condition, not by list.** Use a complex or distinctive word when it carries precise meaning; use the plain form when it would be decoration. This meaning-versus-decoration test is how a profile's weighted preferences resolve in practice: the distinctive word appears where it does real work, the plain word everywhere else, and the ratio falls out on its own.

4. **Restore what a generic draft strips.** Carry the profile's hedging and tentativeness. Add the downtoners and structural hedges the profile records; a clean confident default is usually more certain than the writer actually is.

5. **Anchor in the concrete.** Where the genre allows, include at least one specific, witnessed detail: a role, a time, an artifact, a number. Concept with no scene is the most common form of flatness.

6. **Respect the bans while drafting.** Do not emit what validation would flag. The tell catalog and the profile's bans apply to your own output as you write it.

## Then grade yourself

Before returning a draft, run it through validation: the Step 2 diagnostic and, where a runtime is available, `voicelint.py`. Fix your own flags. Author, then check your own work. Do not hand back a draft you have not validated.

## Guardrails

- **Meaning over voice.** Never add, drop, or bend a fact, name, number, date, or source to fit the voice. The rewrite meaning-guardrail applies to authoring too.
- **Weighted preferences are not lint rules.** A profile may state a preference as a ratio (word A most of the time, word B occasionally). A ratio is not checkable in a single document, and the linter must not enforce it. Resolve it per instance through the meaning-versus-decoration condition; track the ratio, if at all, at corpus level, never in the per-draft check.
- **The profile wins.** Where the profile explicitly claims a habit with evidence, it overrides a generic default here, exactly as in validation.
