# Reading Map Repository Instructions

## Domain authority

If a task can change Reading Map product semantics, data relationships, or business behavior — including Catalog, Entity/Work/Edition identity, Review/Research, Structure, ReadingList, Classification, Guide, Bookshelf, Plan, reading logs, or recommendation behavior — read and follow:

`.codex/skills/reading-map-domain-model/SKILL.md`

Pure visual styling, mechanical refactors, and test fixes do not need to reload the full domain skill when they cannot change those semantics.

## Priority

When sources conflict:

1. the user's current explicit requirement;
2. `.codex/skills/reading-map-domain-model/SKILL.md`;
3. the current task's explicit implementation requirements;
4. current code and regression tests;
5. source/reference material under `docs/`.

Old plans, deleted docs, stale handoffs, QA diaries, and Git history are **not** fallback requirements. Do not use them to restore old UI, fields, workflows, or data models unless the user explicitly asks for historical investigation.

If current code conflicts with the Domain Skill, treat the code as implementation that may need to change. If a current requirement is unclear, ask the user rather than filling the gap from history.

## Model before workaround

If a requirement fits the current model awkwardly, first question whether the model assumption should change. Prefer a simpler domain correction over UI/technical workarounds created only to preserve an old abstraction.

## Operational skills

Use project-local workflow skills when their task applies:

- `.codex/skills/catalog-research-worker/SKILL.md`
- `.codex/skills/wild-reading-list-to-json/SKILL.md`

These operational skills defer to the Domain Skill for business semantics.

## Verification

Do not change unrelated behavior while fixing a scoped task. Run the relevant regression/build checks after changes and report what was actually verified.