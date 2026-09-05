---
description: "Review code for correctness, clarity, and conventions. Use on a file, function, or diff after implementing, before integrating."
agent: agent
tools: [read, search]
---

Review phase of the flow. Give structured feedback against the story's acceptance
criteria, Definition of Done, and any ADRs it references, plus the fixed flow in
`.github/copilot-instructions.md`.

**Correctness**: bugs, edge cases, error handling gaps
**Clarity**: naming, complexity, readability; clear over clever
**Conventions**: follows the project instructions and layout
**Tests**: behaviour covered once, tests independent, the gate would pass
**Docs**: docs, runnable example, and changelog updated for the change
**Security**: secrets not committed, plus any obvious OWASP Top 10 concerns

**Design principles**: the newest document in `.agents/design/` is the source, and its
closing review checklist is the short form. `tests/test_design_principles.py` and
`tests/test_import_structure.py` already fail on the mechanical half, so spend the
review on the half a test cannot see.

- *Simplicity.* Could a reader hold this shape in their head? When an obvious
  mechanism and a clever one both work, the obvious one wins. Nothing can test this,
  so it is the reviewer's job and nobody else's.
- *Lookup efficiency.* Does a schema-side lookup scan a list where a set or dict
  would do? Anything that scales with the schema is built once and looked up, not
  re-derived per call.
- *Data structure choice.* Scaling with the schema means Python dicts and sets.
  Scaling with the data means it stays in Polars. Never pull rows or cells into
  Python lists; the round trip out of Arrow costs a measured 10x and is unbounded
  when no limit is set.
- *Stateless classes.* The test catches `self.x = ...` outside `__init__`. It cannot
  see a method that communicates by mutating an argument, or one whose result depends
  on the order it was called in. Look for those.
- *Frozen, built once.* Apply the design document's own test: could the cache be
  thrown away and rebuilt from the constructor's arguments with an identical result?
  If yes it is memoization. If no it is state, and it does not belong there.
- *Import flow.* A new `TYPE_CHECKING` block or function-body import fails the
  ratchet by design, so that the question gets asked rather than accreting. Answer
  it: does the dependency point the wrong way? At the top-level API boundary it may
  be fine. Anywhere else it usually is not.
- *One definition per predicate.* If a rule is now written in two places, one of them
  is wrong. Point at the named view or helper it should have used.

Where a finding restates something a test already enforces, say so and move on. The
value of this pass is the judgement, not re-running the gate.

Format as a prioritised list: `[blocker]`, `[suggestion]`, `[nit]`.
End with a one-line verdict: is the Definition of Done met, or what is missing.

Finally, file your review as `.agents/review/YYYYMMDDHHMM_<short-descriptive-title>.md`,
add a row to
`.agents/review/index.md`, and note the hand-off in `.agents/memory/`.
