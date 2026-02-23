---
name: plan
description: Creates a detailed, task-by-task implementation plan from an approved specification — technical analysis, dependency ordering, and acceptance criteria.
---

# Plan Skill

## Purpose

Transform an approved specification into a concrete, actionable implementation plan. Break the work into ordered tasks with clear acceptance criteria so the Implementation skill can execute without ambiguity.

## When to Use

This is the **second step** in the development pipeline. Use after the Specification skill has produced an approved spec.

## Inputs

- **Specification path**: path to the approved spec file (e.g. `docs/plans/YYYY-MM-DD-<slug>-spec.md`)

## Process

### Step 1: Analyze the Specification

Read the specification thoroughly. Extract:
- All success criteria (these become acceptance tests)
- Scope boundaries (guard against scope creep during planning)
- Open questions (resolve them now or flag as blockers)

### Step 2: Technical Research

Investigate the codebase to understand what needs to change:

1. **Read `AGENTS.md`** — review contracts, module boundaries, testing standards
2. **Identify affected files** — list every file that needs modification or creation
3. **Map dependencies** — understand which changes depend on others
4. **Check existing tests** — know what test coverage exists today
5. **Review database schema** — if DB changes are needed, note Alembic requirements

### Step 3: Write the Implementation Plan

Create a file at `docs/plans/YYYY-MM-DD-<slug>-plan.md` with this structure:

```markdown
# <Feature Name> — Implementation Plan

> Based on specification: `docs/plans/<spec-file>`

## Technical Analysis

Brief summary of what needs to change technically.
List key architectural decisions or trade-offs.

## Files to Modify

| File | Action | Description |
|------|--------|-------------|
| `bot/example.py` | MODIFY | Add new function X |
| `bot/new_file.py` | CREATE | New module for Y |
| `tests/test_example.py` | MODIFY | Add tests for X |

## Task Breakdown

Tasks are ordered by dependency (do earlier tasks first).

### Task 1: <title>

**Files**: `bot/example.py`
**Description**: What to do, specifically.
**Acceptance Criteria**:
- [ ] Criterion A
- [ ] Criterion B

### Task 2: <title>

**Files**: `bot/example.py`, `tests/test_example.py`
**Description**: What to do, specifically.
**Acceptance Criteria**:
- [ ] Criterion A
- [ ] Criterion B
**Depends on**: Task 1

... (continue for all tasks)

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Risk description | High/Medium/Low | How to handle |

## Edge Cases

List edge cases that implementation and testing must address:
1. Edge case A
2. Edge case B

## Testing Strategy

- Unit tests to write
- Integration tests to write
- Existing tests that must still pass
- Command to run: `pytest -v` or targeted subset
```

### Step 4: Review with User

Present the plan to the user. The plan must be approved before proceeding to implementation.

## Output

- **Artifact**: `docs/plans/YYYY-MM-DD-<slug>-plan.md`
- **Status**: Plan approved by user

## Transition

After user approves the plan, hand off to the **Implementation** skill:

> "Plan approved. Proceeding to the Implementation skill to execute tasks from `docs/plans/<plan-file>`."

Read the Implementation skill instructions at `.agents/skills/implementation/SKILL.md` and follow them.
