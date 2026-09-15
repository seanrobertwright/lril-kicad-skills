# Skill evals

One `evals.json` per skill in the skill-creator format (`skill_name`,
`evals[]` with `id`, `prompt`, `expected_output`, `files`). Run them with
the skill-creator harness (`/skill-creator`) or by hand: give the prompt to a
fresh agent with the skill installed, then check the expected outcome.
Objective evals (schematic, symbol, footprint, export) check files that
KiCad's own tools can verify; the interview evals are judged on behaviour
(one question at a time, recommendation given, nothing assumed, DESIGN.md and
design.json updated).

Fixture: `examples/stm32node/design.json`, and any datasheet PDF you drop in
`evals/fixtures/` (not committed).
