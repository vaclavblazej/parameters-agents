#!/usr/bin/env python3
"""
Generate a ChatGPT prompt for researching a graph parameter and producing
the entries needed to add it to the HOPS (Hierarchy of Parameters) database.

Usage: ./query_param.py <parameter name>
Example: ./query_param.py treewidth
         ./query_param.py "feedback vertex set"
"""

import sys
import random


def rand_alphanum() -> str:
    rnd = random.randrange(0, 2 * 26 + 10)
    if rnd < 10:
        return str(rnd)
    rnd -= 10
    if rnd < 26:
        return chr(ord("a") + rnd)
    rnd -= 26
    return chr(ord("A") + rnd)


def new_id(length: int = 6) -> str:
    return "".join([rand_alphanum() for _ in range(length)])


def to_rust_var(name: str) -> str:
    """Convert a parameter name to a Rust snake_case variable name."""
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def generate_prompt(param_name: str) -> str:
    param_id = new_id()
    source_id = new_id()
    definition_fact_id = new_id()
    rust_var = to_rust_var(param_name)

    return f"""\
You are helping add a new graph parameter to the HOPS (Hierarchy of Parameters)
database — a Rust codebase that catalogues structural graph parameters and their
relationships in parameterized complexity theory.

Please search the internet for: **{param_name}**

Then output ALL FOUR sections below, filled in completely.

══════════════════════════════════════════════════════════════════

## SECTION 1 — Canonical definition

Write a single concise sentence (or two at most) that formally defines
"{param_name}" as a graph parameter.  Use LaTeX math where appropriate
(e.g. $k$, $G$, $V(G)$).  This is the "plain English / math" definition,
not a code snippet.

══════════════════════════════════════════════════════════════════

## SECTION 2 — collection.rs parameter entry

Produce the Rust snippet for src/collection.rs that declares the parameter.
Use the pre-generated ID below — do NOT change it.

Parameter ID (keep exactly): {param_id}

Template to fill in:

```rust
let {rust_var} = parameter("{param_id}", "{param_name}", SCORE, "DEFINITION")
    .done(&mut create);
```

Fill in:
  SCORE      — integer 1–9 reflecting the parameter's importance in the
               parameterized complexity literature
               (9 = as fundamental as treewidth; 1 = very obscure)
  DEFINITION — the canonical definition from Section 1, as a Rust string
               literal.  Escape backslashes (e.g. \\\\mathrm{{td}}).

Optionally add `.abbr("...")` before `.done(...)` if the parameter has a
well-known short abbreviation (e.g. "tw" for treewidth).

══════════════════════════════════════════════════════════════════

## SECTION 3 — BibTeX entry for the original paper

Search the internet for the **earliest paper** that formally introduced or
defined "{param_name}".  Retrieve the paper (via DOI, arXiv, or any open
access link) and confirm it actually contains the definition.

Produce a BibTeX entry suitable for handcrafted/main.bib.

```bibtex
@TYPE{{BIBTEXKEY,
    author  = {{}},
    title   = {{}},
    journal = {{}},   % or booktitle for conference papers
    year    = {{}},
    volume  = {{}},
    pages   = {{}},
    doi     = {{}},
    url     = {{}},
}}
```

Rules:
  TYPE       — Article / InProceedings / Book / Unpublished / etc.
  BIBTEXKEY  — CamelCase string of the form AuthorYear (e.g. Robertson1991),
               must match what you use in Section 4.
  Omit fields you cannot find, but doi and url are strongly preferred.

══════════════════════════════════════════════════════════════════

## SECTION 4 — collection.rs source entry

Open the paper from Section 3 and find the sentence(s) where "{param_name}"
is formally defined.  Note the exact page number.

⚠ The QUOTE must be copied verbatim from the paper.
⚠ The PAGE must be the real page number where the definition appears.
⚠ Do NOT paraphrase. Do NOT use NotApplicable. If you cannot access the paper,
  say so explicitly and leave QUOTE and PAGE as TODO instead of guessing.

Source ID (keep exactly):          {source_id}
Definition-fact ID (keep exactly): {definition_fact_id}

```rust
let VARNAME = source("{source_id}", "BIBTEXKEY", SCORE)
    .wrote(Pp(PAGE), "QUOTE", vec![
        ("{definition_fact_id}", Original, definition(&{rust_var})),
    ])
    .done(&mut create);
```

Fill in:
  VARNAME    — Rust snake_case variable (typically authorYear,
               e.g. robertson_seymour1991)
  BIBTEXKEY  — must match the key from Section 3 exactly
  SCORE      — integer 1–9 for how canonical / reliable the source is
  PAGE       — the page number (integer) in the paper
  QUOTE      — verbatim text from the paper; escape backslashes
               (e.g. \\\\emph{{...}}, \\\\mathcal{{F}})

══════════════════════════════════════════════════════════════════

Important reminders:
  • Keep the pre-generated IDs exactly as given — do not regenerate them.
  • If the paper is behind a paywall and you cannot read it, say so — do
    not invent a quote.  A TODO placeholder is better than a hallucination.
  • If "{param_name}" has multiple equivalent definitions, use the one from
    the original paper in Section 4 and note alternatives in Section 1.
"""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <parameter name>", file=sys.stderr)
        print(f'Example: {sys.argv[0]} "feedback vertex set"', file=sys.stderr)
        sys.exit(1)

    param_name = " ".join(sys.argv[1:])
    print(generate_prompt(param_name))
