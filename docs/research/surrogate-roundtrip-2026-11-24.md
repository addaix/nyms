# Surrogate round trip through LLMs on the test fixtures (nyms#3, 2026-11-24)

**Question.** The default surrogate form, `[PERSON_1]`, rests on one 2026 vendor benchmark in Russian and English ([pipeline-architecture-and-agent-practice.md](pipeline-architecture-and-agent-practice.md) §2). Does it hold on the Danish and English fixtures with current models, against the two keyed forms nyms also offers?

**Method.** `misc/eval/roundtrip.py`. Each fixture (`tests/fixtures/da_lejesag.md`, `en_letter.md`, both synthetic) is pseudonymised with three forms: `counter` (`[PERSON_1]`), `keyed-names` (people and organisations as two capitalised words, `Zodiac Zodiac`; other types `[TYPE:word-word]`) and `keyed-words` (every type `[TYPE:word-word]`). Each is sent through three ordinary tasks with no word about placeholders (summarise in five bullets, translate into the other language, draft a reply), on two models (Claude Haiku and Sonnet through the Claude Code CLI), twice: 72 runs, 1,080 surrogates given. Then per output: how many issued surrogates are still there (tolerant match), occurrences kept exactly, occurrences altered but restorable, parts of name-shaped surrogates left after a match (unrestorable), bracketed tokens that were never issued, and what `reidentify` restored.

**Results.**

| form | task | runs | surrogates given | present after | kept exact | altered (restorable) | name parts left (lost) | invented | restored |
|---|---|---|---|---|---|---|---|---|---|
| counter | all | 24 | 360 | 192 (53%) | 224 | 1 | 0 | 1 | 225 |
| counter | reply | 8 | 120 | 47 (39%) | 62 | 1 | 0 | 1 | 63 |
| counter | summary | 8 | 120 | 25 (21%) | 26 | 0 | 0 | 0 | 26 |
| counter | translate | 8 | 120 | 120 (100%) | 136 | 0 | 0 | 0 | 136 |
| keyed-names | all | 24 | 360 | 187 (52%) | 224 | 0 | 8 | 1 | 224 |
| keyed-names | reply | 8 | 120 | 32 (27%) | 47 | 0 | 4 | 1 | 47 |
| keyed-names | summary | 8 | 120 | 35 (29%) | 39 | 0 | 4 | 0 | 39 |
| keyed-names | translate | 8 | 120 | 120 (100%) | 138 | 0 | 0 | 0 | 138 |
| keyed-words | all | 24 | 360 | 157 (44%) | 180 | 0 | 0 | 0 | 180 |
| keyed-words | reply | 8 | 120 | 29 (24%) | 36 | 0 | 0 | 0 | 36 |
| keyed-words | summary | 8 | 120 | 10 (8%) | 10 | 0 | 0 | 0 | 10 |
| keyed-words | translate | 8 | 120 | 118 (98%) | 134 | 0 | 0 | 0 | 134 |

**Reading it.**

- **Translation, the strict task, keeps nearly everything in every form**: 120 of 120 surrogates for `counter` and `keyed-names`, 118 of 120 for `keyed-words`. Every occurrence present was restored.
- **Altered tokens are rare and the tolerant matcher absorbs them**: 1 in 72 runs (a dropped opening bracket, `ID_1]`), restored.
- **Name-shaped surrogates lose restorability when the model shortens them**: 8 occurrences like "Mr Zodiac" or "Ms Agitate" (surname or first word only, after a title), all in English replies and summaries. The matcher, by design, restores only the full name, so these come back as fake names in the restored text. Bracketed forms never had this failure.
- **Readable-word tokens are left out more often in summaries**: 8% of `keyed-words` surrogates survive a summary, against 21% for `counter` and 29% for `keyed-names`. The models paraphrase them ("a company represented by a lawyer"). This is omission, not corruption: nothing wrong is restored.
- **Invented tokens come from replies, not from corruption**: 2 runs had a bracketed token never issued. Both were the model's own fill-in blanks in a drafted reply (`[AMOUNT demanded]`), which have the shape of a typed token. `reidentify` leaves them alone and reports them as unmatched, which is the right behaviour.
- **No `PERSON_1` / `PERSON_11` confusion** was possible here (at most six of a type per document); the longest-first, word-bounded matcher covers it by construction.

**Verdict.** Keep `[PERSON_1]` (`Counter`) as the default: on these fixtures it is never corrupted beyond what the matcher restores and keeps more items through a summary than `keyed-words`. `keyed-names` reads best but needs part-name restoration before it can be trusted on English letters (#11). The sample is small (two short documents, two models), so these are directions, not rates; the script reruns on any fixture set and model list (`--models`), including another provider's.
