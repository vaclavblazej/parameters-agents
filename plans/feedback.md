Design Options for Interactive Hierarchy Proposals

The core tension is: data currently lives in Rust source code, so any interactive system needs to bridge
user contributions with that source-of-truth.

---
Option A — GitHub PR Workflow (Minimal backend)

Users propose changes by creating pull requests. Merging triggers site regeneration.

Flow:
User logs in (GitHub OAuth)
  → Fills form on website describing change
  → Backend creates a GitHub PR against collection.rs
  → Maintainers review/merge PR
  → CI/CD runs `cargo run fast` → regenerates site

Change representation: Structured form (add relation, correct bound, new parameter) translates to a PR
with a generated patch against collection.rs.

Pros: Free audit trail, existing git tooling, no custom review UI needed
Cons: All users need GitHub accounts, CI/CD setup required, PRs against Rust code may feel awkward for
non-developers

---
Option B — Rust Backend + Proposal Database (Full control)

A separate Axum service stores proposals in a database. Approval triggers regeneration.

Architecture:
                 ┌─────────────────────────────┐
  Hugo static ◄──┤  cargo run fast (triggered)  │
  (approved)     └────────────┬────────────────┘
                              │ on approval
                    ┌─────────▼──────────┐
                    │  Axum API backend  │
                    │  ┌──────────────┐  │
                    │  │   SQLite /   │  │
                    │  │  Postgres    │  │
                    │  │  proposals   │  │
                    │  └──────────────┘  │
                    └────────────────────┘
                              ▲
                    User submits proposal (form)

Proposals stored as structured data:
{
  "type": "add_relation",
  "from": "treewidth",
  "to": "pathwidth",
  "bound": "linear",
  "source": "...",
  "status": "pending | approved | rejected"
}

On approval: backend mutates collection.rs programmatically (since the builder API is well-defined) and
rebuilds.

Pros: No GitHub dependency, rich review UI possible, fine-grained approval workflow
Cons: Most work — building admin UI, designing proposal schema, deployment complexity

---
Option C — Overlay Architecture (Separation of static + live)

Static site stays as-is. A thin layer shows pending/approved proposals dynamically on top.

Architecture:
Hugo static site  +  thin JS client
     (base)            (overlays)
                           │
                    fetches from
                           │
                    ┌──────▼───────┐
                    │  Lightweight │
                    │  API (could  │
                    │  be Rust or  │
                    │  serverless) │
                    └──────────────┘
                    stores proposals
                    as JSON/SQLite

Key idea: Approved proposals are displayed immediately on the site without regenerating — then
periodically batch-regenerated into the static site. Pending proposals show with a "proposed" badge.

Pros: Fastest to ship (no touching static generation), proposals visible instantly
Cons: Two sources of truth (static + dynamic), client-side complexity, divergence risk

---
Option D — Structured Diff Format (Data-model-first)

Decouple the proposal format from the current Rust representation entirely. Proposals are domain-specific
diffs.

Define a JSON schema for "HOPS change proposals":
{
  "version": 1,
  "changes": [
    { "op": "add_parameter", "id": "xyz123", "name": "...", "description": "..." },
    { "op": "add_relation", "from": "xyz123", "to": "tw", "bound": "O(n)", "source": "doe2024" },
    { "op": "correct_relation", "relation_id": "abc", "field": "bound", "new_value": "..." }
  ]
}

These live in a separate store (git repo, DB, filesystem). The Rust pipeline learns to read approved
proposals in addition to collection.rs at build time.

Pros: Clean separation — proposals don't require touching Rust code, easy to version/audit, testable
Cons: Requires extending the Rust pipeline to consume a second data source

---
Recommendation

Given the project's nature (academic, small contributor community, data integrity matters), I'd suggest
Option D as the data model + Option A or B for auth/review UI:

1. Define a proposals/ directory of JSON change files (or single SQLite file)
2. Extend the Rust pipeline to merge approved proposals at build time
3. Build a minimal web form for submitting proposals (auth via GitHub or email token)
4. Use GitHub PRs or a simple admin page for approval

This keeps collection.rs as the curated master while allowing community contributions without requiring
all contributors to write Rust.

---
Key questions that would sharpen the design:
- Who are the expected users — researchers (comfortable with GitHub) or broader public?
- Who approves — just you, or a team of moderators?
- What types of changes are in scope — new relations, corrections, entirely new parameters, or all of the
above?
- Is the site currently hosted somewhere with a server, or purely static (e.g., GitHub Pages)?
