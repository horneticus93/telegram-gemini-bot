# Development Pipeline Orchestrator

This document defines how the 5 development skills work together as a pipeline.

## Pipeline Sequence

```
Specification → Plan → Implementation → Review ⇄ Implementation → Testing ⇄ Implementation → Done
```

## Skills Reference

| Step | Skill | Location | Output |
|------|-------|----------|--------|
| 1 | Specification | `.agents/skills/specification/SKILL.md` | `docs/plans/*-spec.md` |
| 2 | Plan | `.agents/skills/plan/SKILL.md` | `docs/plans/*-plan.md` |
| 3 | Implementation | `.agents/skills/implementation/SKILL.md` | Code + tests |
| 4 | Review | `.agents/skills/review/SKILL.md` | Review verdict |
| 5 | Testing | `.agents/skills/testing/SKILL.md` | Green test suite |

## State Tracking

At each pipeline step, announce the current state:

```
📍 Pipeline: [Specification | Plan | Implementation | Review | Testing]
📄 Spec: docs/plans/<spec-file> (if exists)
📋 Plan: docs/plans/<plan-file> (if exists)
🔄 Cycle: Review #N / Test-Fix #N (if in loop)
```

## Transition Rules

1. **Specification → Plan**: Only after user approves the spec
2. **Plan → Implementation**: Only after user approves the plan
3. **Implementation → Review**: Only after all tasks complete and tests pass
4. **Review → Implementation** (loop): When review finds issues
5. **Review → Testing**: When review verdict is `APPROVED`
6. **Testing → Implementation** (loop): When tests fail due to code bugs
7. **Testing → Done**: When all tests pass

## Loop Limits

| Loop | Max Cycles | On Limit Reached |
|------|-----------|-----------------|
| Review ⇄ Implementation | 3 | Escalate unresolved issues to user |
| Testing ⇄ Implementation | 3 | Escalate persistent failures to user |

## Naming Conventions

- Spec files: `docs/plans/YYYY-MM-DD-<slug>-spec.md`
- Plan files: `docs/plans/YYYY-MM-DD-<slug>-plan.md`
- Date format: ISO 8601 date (`YYYY-MM-DD`)
- Slug: lowercase, hyphens, descriptive (e.g. `user-profile-caching`)

## How to Start

To run the full pipeline, use the `/develop` workflow:

```
/develop <feature description>
```

Or manually read each skill's `SKILL.md` in sequence.
