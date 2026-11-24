"""Measure how surrogate forms survive a round trip through an LLM (nyms#3).

Pseudonymise each test fixture with three surrogate forms, send it through ordinary tasks
(summarise, translate, draft a reply) on a few models, then count, per surrogate the model
was given:

- **kept**: occurrences written exactly as issued;
- **altered**: occurrences the tolerant matcher still restores but that were not exact
  (case, spacing, a dropped bracket, a genitive);
- **mangled**: leftover fragments of name-shaped surrogates ("Mr Brook"; a run of name
  words counts once), which the matcher cannot restore;
- **invented**: bracketed tokens in the output that were never issued (cannot be restored);
- **restored**: what :meth:`nyms.Pseudonymiser.reidentify` put back.

A surrogate missing from a summary may be a legitimate omission, so "dropped" is reported
per task, and the translate task (where every item should survive) is the strict one.

Models run through ``aix.chat`` (default: the Claude Code CLI backend, no API key). Raw
outputs go to ``<nyms data dir>/eval/roundtrip-<date>/``, never into the repo; the fixtures
are synthetic, so the summary may be published.

Usage::

    python misc/eval/roundtrip.py --models claude-cli/haiku claude-cli/sonnet --reps 2 --jobs 4
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from nyms.core import Pseudonymiser, _leftover_tokens, _tolerant_pattern
from nyms.surrogates import Counter, KeyedWords

HERE = Path(__file__).resolve().parents[2]
FIXTURES = {
    "da": HERE / "tests/fixtures/da_lejesag.md",
    "en": HERE / "tests/fixtures/en_letter.md",
}
OTHER = {"da": "English", "en": "Danish"}
SAME = {"da": "Danish", "en": "English"}
KEY = b"nyms-roundtrip-eval-fixed-key-32b"
FORMS = {
    "counter": lambda: Counter(),  # [PERSON_1]
    "keyed-names": lambda: KeyedWords(
        KEY
    ),  # PERSON/ORG as "Alder Brook", others [TYPE:word-word]
    "keyed-words": lambda: KeyedWords(
        KEY, templates={}
    ),  # every type as [TYPE:word-word]
}
TASKS = {
    "summary": "Summarise this document in five bullet points, in {same}.",
    "translate": "Translate this document into {other}. Output only the translation.",
    "reply": "Draft a short reply to this document from its recipient, in {same}.",
}


def _pseudonymised(lang, form):
    p = Pseudonymiser(f"eval-{lang}-{form}", store={}, strategy=FORMS[form](), key=KEY)
    r = p.pseudonymise(FIXTURES[lang].read_text())
    return p, r.text, sorted({s for _, s in r.replacements})


def _name_fragments(issued):
    """Pattern matching one leftover fragment of a name-shaped surrogate.

    A fragment is a run of whitespace-separated words taken from the issued names, so
    "Mr Zodiac" (from ``Zodiac Zodiac``) or "Foggy Folksong" (a reordered
    ``Folksong Foggy``) each count once, and a word shared by two names is not counted
    twice. Matches nothing when no name-shaped surrogate was issued.

    >>> pat = _name_fragments(["Zodiac Zodiac", "Kayak Outhouse", "[EMAIL:a-b]"])
    >>> pat.findall("Dear Mr Zodiac, and Outhouse Kayak.")
    ['Zodiac', 'Outhouse Kayak']
    >>> _name_fragments(["[PERSON_1]"]).findall("Zodiac")
    []
    """
    words = sorted(
        {w for s in issued if not s.startswith("[") for w in s.split()},
        key=len,
        reverse=True,
    )
    if not words:
        return re.compile(r"(?!)")
    word = "(?:" + "|".join(map(re.escape, words)) + ")"
    return re.compile(rf"(?<!\w){word}(?:\s+{word})*(?!\w)")


def _measure(p, issued, output):
    pattern = _tolerant_pattern(issued)
    kept = sum(output.count(s) for s in issued)
    tolerant = len(pattern.findall(output))
    present = {s for s in issued if _tolerant_pattern([s]).search(output)}
    stripped = pattern.sub(" ", output)
    mangled = len(_name_fragments(issued).findall(stripped))
    back = p.reidentify(output)
    invented = [
        t
        for t in _leftover_tokens(output)
        if t not in issued and not pattern.fullmatch(t)
    ]
    return dict(
        issued=len(issued),
        present=len(present),
        kept=kept,
        altered=max(0, tolerant - kept),
        mangled=mangled,
        invented=len(invented),
        restored=back.restored,
        unrestored_tokens=len(back.unmatched),
    )


def run(models, reps, jobs, outdir):
    cases = []
    for lang in FIXTURES:
        for form in FORMS:
            p, text, issued = _pseudonymised(lang, form)
            for task, tmpl in TASKS.items():
                prompt = (
                    tmpl.format(same=SAME[lang], other=OTHER[lang])
                    + "\n\n---\n\n"
                    + text
                )
                for model in models:
                    for rep in range(reps):
                        cases.append((lang, form, task, model, rep, p, issued, prompt))

    def one(case):
        from aix import chat

        lang, form, task, model, rep, p, issued, prompt = case
        name = f"{lang}-{form}-{task}-{model.replace('/', '_')}-{rep}.txt"
        path = outdir / name
        if path.exists():
            output = path.read_text()
        else:
            output = chat(prompt, model=model)
            path.write_text(output)
        return dict(
            lang=lang,
            form=form,
            task=task,
            model=model,
            rep=rep,
            **_measure(p, issued, output),
        )

    with ThreadPoolExecutor(jobs) as pool:
        return list(pool.map(one, cases))


def summarise(rows):
    agg = defaultdict(lambda: defaultdict(int))
    for r in rows:
        for key in [(r["form"], "all"), (r["form"], r["task"])]:
            a = agg[key]
            a["runs"] += 1
            for k in (
                "issued",
                "present",
                "kept",
                "altered",
                "mangled",
                "invented",
                "restored",
                "unrestored_tokens",
            ):
                a[k] += r[k]
    lines = [
        "| form | task | runs | surrogates given | present after | kept exact | altered (restorable) | name fragments left (lost) | invented | restored |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (form, task), a in sorted(
        agg.items(), key=lambda kv: (kv[0][0], kv[0][1] != "all", kv[0][1])
    ):
        lines.append(
            f"| {form} | {task} | {a['runs']} | {a['issued']} | {a['present']} ({100 * a['present'] / a['issued']:.0f}%) | "
            f"{a['kept']} | {a['altered']} | {a['mangled']} | {a['invented']} | {a['restored']} |"
        )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--models", nargs="+", default=["claude-cli/haiku", "claude-cli/sonnet"]
    )
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--outdir", default=None)
    a = ap.parse_args()
    from nyms.keys import data_dir

    outdir = Path(
        a.outdir or data_dir() / "eval" / f"roundtrip-{dt.date.today():%Y-%m-%d}"
    )
    outdir.mkdir(parents=True, exist_ok=True)
    rows = run(a.models, a.reps, a.jobs, outdir)
    (outdir / "rows.json").write_text(json.dumps(rows, indent=1))
    print(f"{len(rows)} runs; raw outputs in {outdir}")
    print(summarise(rows))


if __name__ == "__main__":
    main()
