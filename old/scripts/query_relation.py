#!/usr/bin/env python3
"""
Generate a ChatGPT prompt to research the relation between two entities
already in the HOPS (Hierarchy of Parameters) database.

IDs are extracted automatically from hops/src/collection.rs.

Usage: ./query_relation.py <name 1> <name 2>
Example: ./query_relation.py treewidth pathwidth
         ./query_relation.py "treewidth" "clique-width"
         ./query_relation.py treewidth planar
"""

import sys
import re
import random
from pathlib import Path

COLLECTION_RS = Path(__file__).parent.parent / "hops" / "src" / "collection.rs"

# Map from constructor keyword → entity type label
CONSTRUCTOR_ETYPE = {
    "parameter":              "parameter",
    "distance_to":            "parameter",
    "higher_order_parameter": "parameter",
    "parametric_parameter":   "parametric parameter",
    "graph_class_property":   "graph class property",
    "graph_property":         "graph class property",
    "graph_class":            "graph class",
    "parametric_graph_class": "parametric graph class",
    "intersection":           "entity",   # resolved further if possible
}

CONSTRUCTORS = list(CONSTRUCTOR_ETYPE.keys())


# ── ID generation ─────────────────────────────────────────────────────────────

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
    return name.strip().lower().replace("-", "_").replace(" ", "_").replace("/", "_")


# ── Entity lookup in collection.rs ────────────────────────────────────────────

def detect_constructor(preceding: str) -> str:
    """Return the rightmost constructor keyword appearing in 'preceding'."""
    best_pos, best = -1, "unknown"
    for c in CONSTRUCTORS:
        pos = preceding.rfind(c)
        if pos > best_pos:
            best_pos, best = pos, c
    return best


def find_entity(name: str, text: str):
    """
    Return (entity_id, rust_var, constructor, etype_label) or sys.exit(1).

    Tries three patterns in order:
      1. "ID", "name"                              (parameter, graph_class, …)
      2. distance_to("ID", &set, "name", …)
      3. intersection("ID", &a, &b, "name", …)
    """
    escaped = re.escape(name)

    # Pattern 1: ID directly before name (covers most constructors)
    m = re.search(r'"([A-Za-z0-9]{6})"\s*,\s*"' + escaped + r'"', text)
    if m:
        entity_id = m.group(1)
        preceding = text[max(0, m.start() - 200): m.start()]
        cons = detect_constructor(preceding)
        return entity_id, to_rust_var(name), cons, CONSTRUCTOR_ETYPE.get(cons, "entity")

    # Pattern 2: distance_to("ID", &set, "name")
    m = re.search(
        r'distance_to\s*\(\s*"([A-Za-z0-9]{6})"\s*,[^,]+,\s*"' + escaped + r'"',
        text,
    )
    if m:
        return m.group(1), to_rust_var(name), "distance_to", "parameter"

    # Pattern 3: intersection("ID", &a, &b, "name")
    m = re.search(
        r'intersection\s*\(\s*"([A-Za-z0-9]{6})"\s*,[^,]+,[^,]+,\s*"' + escaped + r'"',
        text,
    )
    if m:
        return m.group(1), to_rust_var(name), "intersection", "entity"

    print(f"Error: '{name}' not found in collection.rs", file=sys.stderr)
    sys.exit(1)


# ── Per-type-combination notation explanation ──────────────────────────────────

def relation_body(
    type1: str, type2: str,
    name1: str, name2: str,
    var1:  str, var2:  str,
    fact_id: str, fact_id2: str,
) -> str:
    """Return the notation description + Rust snippet template for this type pair."""

    # ── parameter ↔ parameter ────────────────────────────────────────────────
    if type1 == "parameter" and type2 == "parameter":
        return f"""\
Both entities are **parameters**.  `relation(&{var1}, &{var2}, BOUND)` encodes:
given a graph G, how does {name2}(G) relate to {name1}(G)?
`UpperBound(X)` means {name2} ≤ f({name1}) for a function f of growth class X.

BOUND variants:
  UpperBound(X)       — {name2} ≤ f({name1}),  f ∈ X
  LowerBound(X)       — {name2} ≥ f({name1}),  f ∈ X   ({name2} can be large)
  Bounds(lo, hi)      — lo({name1}) ≤ {name2} ≤ hi({name1})
  Exactly(X)          — tight: Bounds(X, X)
  Equivalent(f, g)    — {name2} ≤ f({name1})  AND  {name1} ≤ g({name2})
  Equal               — {name2} = {name1} on every graph
  Exclusion           — {name2} is NOT bounded by any function of {name1}
  Incomparable        — mutual Exclusion
  StrictUpperBound(X) — {name2} ≤ f({name1})  AND  {name1} NOT bounded by {name2}

CpxTime growth classes X (weakest to strongest bound):
  Constant    O(1)       Polynomial  k^O(1)    Tower  2^2^…^k
  Linear      O(k)       Exponential 2^O(k)    Exists any computable f(k)

Rust snippet:
```rust
let VARNAME = source("SOURCE_ID", "BIBTEXKEY", SCORE)
    .wrote(Pp(PAGE), "QUOTE", vec![
        ("{fact_id}", Original, relation(&{var1}, &{var2}, BOUND)),
    ])
    .done(&mut create);
```

If two separate facts are needed (e.g. upper bound + lower bound from different
theorems), use both fact IDs with a second `.wrote(...)` call:
```rust
    .wrote(Pp(PAGE2), "QUOTE2", vec![
        ("{fact_id2}", Original, relation(&{var1}, &{var2}, BOUND2)),
    ])
```"""

    # ── graph class / property → parameter ──────────────────────────────────
    elif type1 in ("graph class", "graph class property") and type2 == "parameter":
        return f"""\
`{name1}` is a **{type1}** and `{name2}` is a **parameter**.
The relation is an `ImplicationRelation` stating whether membership in / having
`{name1}` implies that `{name2}` is bounded (or that it is unbounded).

  ImplicationRelation::Implies  — every graph in `{name1}` has bounded `{name2}`
  ImplicationRelation::Excludes — there exist graphs in `{name1}` with unbounded `{name2}`

Rust snippet:
```rust
let VARNAME = source("SOURCE_ID", "BIBTEXKEY", SCORE)
    .wrote(Pp(PAGE), "QUOTE", vec![
        ("{fact_id}", Original, relation(&{var1}, &{var2}, ImplicationRelation::Implies)),
    ])
    .done(&mut create);
```"""

    # ── parameter → graph class ──────────────────────────────────────────────
    elif type1 == "parameter" and type2 == "graph class":
        return f"""\
`{name1}` is a **parameter** and `{name2}` is a **graph class**.
The relation is an `ImplicationRelation`:

  ImplicationRelation::Implies  — bounded `{name1}` ⇒ graph belongs to `{name2}`
  ImplicationRelation::Excludes — bounded `{name1}` does NOT imply membership in `{name2}`

Rust snippet:
```rust
let VARNAME = source("SOURCE_ID", "BIBTEXKEY", SCORE)
    .wrote(Pp(PAGE), "QUOTE", vec![
        ("{fact_id}", Original, relation(&{var1}, &{var2}, ImplicationRelation::Implies)),
    ])
    .done(&mut create);
```"""

    # ── parameter ↔ graph class property (equivalence possible) ─────────────
    elif type1 == "parameter" and type2 == "graph class property":
        return f"""\
`{name1}` is a **parameter** and `{name2}` is a **graph class property**.
Use `EquivalenceRelation::Equivalent` if `{name1}` is bounded ⟺ `{name2}` holds,
or `ImplicationRelation::Implies` for a one-directional implication.

  EquivalenceRelation::Equivalent — bounded `{name1}` ⟺ graph has `{name2}`
  ImplicationRelation::Implies    — bounded `{name1}` ⇒ graph has `{name2}` (one way)

Rust snippet:
```rust
let VARNAME = source("SOURCE_ID", "BIBTEXKEY", SCORE)
    .wrote(Pp(PAGE), "QUOTE", vec![
        ("{fact_id}", Original, relation(&{var1}, &{var2}, EquivalenceRelation::Equivalent)),
    ])
    .done(&mut create);
```"""

    # ── graph class ↔ graph class ────────────────────────────────────────────
    elif type1 == "graph class" and type2 == "graph class":
        return f"""\
Both entities are **graph classes**.
`relation(&{var1}, &{var2}, REL)` states that every graph in `{name1}` also
belongs to `{name2}` (under the given graph containment relation REL).

collection.rs defines these graph-relation-type variables at the top of the file:
  subset           — plain set containment (every {name1}-graph is a {name2}-graph)
  subgraph         — under vertex/edge deletion
  minor            — under vertex/edge deletion + edge contraction
  topological_minor — under vertex/edge deletion + degree-2 vertex contraction
  induced_subgraph — under vertex deletion only
  induced_minor    — under vertex deletion + edge contraction

For a plain "every {name1}-graph is a {name2}-graph" use `normal_rel.clone()`
(defined at the top of collection.rs as Implies under subgraph).
For Exclusion (i.e. there exist {name1}-graphs NOT in {name2}), set
`relation: ImplicationRelation::Excludes` inside the struct.

Rust snippet:
```rust
let VARNAME = source("SOURCE_ID", "BIBTEXKEY", SCORE)
    .wrote(Pp(PAGE), "QUOTE", vec![
        ("{fact_id}", Original, relation(&{var1}, &{var2}, normal_rel.clone())),
        // replace normal_rel with: subset / minor / induced_subgraph / etc.
    ])
    .done(&mut create);
```"""

    # ── graph class property ↔ graph class property ──────────────────────────
    elif type1 == "graph class property" and type2 == "graph class property":
        return f"""\
Both entities are **graph class properties**.
The relation is an `ImplicationRelation`:

  ImplicationRelation::Implies    — every graph class with `{name1}` also has `{name2}`
  ImplicationRelation::Excludes   — `{name1}` does NOT imply `{name2}`
  ImplicationRelation::Equivalent — `{name1}` ⟺ `{name2}`

Rust snippet:
```rust
let VARNAME = source("SOURCE_ID", "BIBTEXKEY", SCORE)
    .wrote(Pp(PAGE), "QUOTE", vec![
        ("{fact_id}", Original, relation(&{var1}, &{var2}, ImplicationRelation::Implies)),
    ])
    .done(&mut create);
```"""

    # ── fallback ─────────────────────────────────────────────────────────────
    else:
        return f"""\
The entity types are **{type1}** and **{type2}**.
Inspect the `Relatable` trait implementations in `hops/src/input/source.rs`
to find the correct data type for this combination, then fill in:

```rust
let VARNAME = source("SOURCE_ID", "BIBTEXKEY", SCORE)
    .wrote(Pp(PAGE), "QUOTE", vec![
        ("{fact_id}", Original, relation(&{var1}, &{var2}, RELATION_DATA)),
    ])
    .done(&mut create);
```"""


# ── Top-level prompt assembly ──────────────────────────────────────────────────

def generate_prompt(name1: str, name2: str) -> str:
    text = COLLECTION_RS.read_text()

    id1, var1, cons1, type1 = find_entity(name1, text)
    id2, var2, cons2, type2 = find_entity(name2, text)

    source_id = new_id()
    fact_id   = new_id()
    fact_id2  = new_id()

    body = relation_body(type1, type2, name1, name2, var1, var2, fact_id, fact_id2)

    return f"""\
You are helping add a relation to the HOPS (Hierarchy of Parameters) database —
a Rust codebase cataloguing structural graph parameters and their relationships
in parameterized complexity theory.

The two entities already exist in the database:
  Entity 1: "{name1}"  (type: {type1},  ID: {id1},  Rust var: {var1})
  Entity 2: "{name2}"  (type: {type2},  ID: {id2},  Rust var: {var2})

Please search the internet for the known relation between **{name1}** and
**{name2}** and fill in all THREE sections below.

══════════════════════════════════════════════════════════════════

## SECTION 1 — The relation

Describe what is known between "{name1}" and "{name2}":
  • Direction (which bounds which, are they equivalent, incomparable, …)
  • Tightness (is the bound known to be tight?)
  • Any witness graphs for lower bounds / exclusions

══════════════════════════════════════════════════════════════════

## SECTION 2 — Rust notation

{body}

Pre-generated IDs — keep exactly as given:
  Source ID : {source_id}
  Fact ID 1 : {fact_id}
  Fact ID 2 : {fact_id2}  (use only if a second separate fact is needed)

══════════════════════════════════════════════════════════════════

## SECTION 3 — BibTeX + source entry

Search for and retrieve the **original paper** that proves the relation from
Section 1.  Open the paper and find the exact theorem or lemma.

### BibTeX entry (for handcrafted/main.bib):
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

### collection.rs source entry (fill in the template from Section 2):

⚠ QUOTE must be copied verbatim from the paper.
⚠ PAGE must be the real page number — use Pp(N).
⚠ Do NOT paraphrase. If you cannot access the paper, say so and write TODO
  instead of guessing.

  VARNAME    — Rust snake_case variable for this source (e.g. robertson1991)
  BIBTEXKEY  — must match the BibTeX key above
  SCORE      — 1–9, importance/reliability of the source
  PAGE       — integer page number
  QUOTE      — verbatim theorem statement

══════════════════════════════════════════════════════════════════

Important reminders:
  • Keep the pre-generated IDs exactly as given.
  • A TODO placeholder is better than a hallucinated quote or page number.
  • For two-directional results from separate theorems use both fact IDs and
    two .wrote(...) calls (or two separate source entries if in different papers).
"""


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <name 1> <name 2>", file=sys.stderr)
        print(f'Example: {sys.argv[0]} treewidth pathwidth', file=sys.stderr)
        print(f'Example: {sys.argv[0]} "treewidth" "clique-width"', file=sys.stderr)
        sys.exit(1)

    print(generate_prompt(sys.argv[1], sys.argv[2]))
