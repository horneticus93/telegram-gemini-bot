---
name: implementation
description: Executes the implementation plan task by task — writes production code and basic tests, runs pytest after each task to ensure nothing breaks.
---

# Implementation Skill

## Purpose

Execute an approved implementation plan by writing production code and accompanying tests, task by task, ensuring the codebase stays green throughout.

## When to Use

- **Normal flow**: After the Plan skill produces an approved plan
- **Fix flow**: When called back by the Review or Testing skill to fix specific issues

## Inputs

### Normal Flow
- **Plan path**: path to the approved plan (e.g. `docs/plans/YYYY-MM-DD-<slug>-plan.md`)

### Fix Flow
- **Issue list**: specific problems to fix (from Review or Testing skill)
- **Context**: which files and tests are affected

## Process

### Step 1: Prepare

1. Read `AGENTS.md` — refresh on project contracts, testing standards, code guidelines
2. Read the implementation plan — understand all tasks and their dependencies
3. If in Fix Flow — read the issue list and understand what needs to change

### Step 2: Execute Tasks

For each task in the plan (in dependency order):

#### 2a. Implement Code Changes

- Write clean, minimal, behavior-preserving code (unless refactoring is the task)
- Follow existing patterns in the codebase
- Maintain async boundaries (use `asyncio.to_thread` where already used)
- Preserve dependency injection / patchability for tests
- Add comments only where logic is subtle

#### 2b. Write Tests Alongside Code

- For every new function/method, write at least one test
- For every changed behavior, update existing tests
- Follow existing test patterns: `pytest` + `pytest-asyncio`, `MagicMock` / `AsyncMock`
- Tests go in the appropriate `tests/test_*.py` file

#### 2c. Run Tests After Each Task

```bash
pytest -v
```

- If tests pass → mark task as complete, proceed to next task
- If tests fail → fix the issue before moving on
- **Never leave failing tests behind**

### Step 3: Verify Acceptance Criteria

After all tasks are complete, go through each task's acceptance criteria and confirm they are met.

### Step 4: Update Documentation

If changes affect:
- Environment variables → update `.env.example` and `README.md`
- Module contracts → update `AGENTS.md`
- Database schema → create Alembic migration
- API behavior → update relevant docs

## Output

- **Code changes**: all files modified/created per the plan
- **Tests**: unit tests for all new/changed behavior
- **Green test suite**: `pytest -v` passes
- **Updated docs**: if applicable

## Transition

After implementation is complete, hand off to the **Review** skill:

> "Implementation complete. All tasks executed, tests pass. Proceeding to Review skill."

Read the Review skill instructions at `.agents/skills/review/SKILL.md` and follow them.

### Fix Flow Return

When called from Review or Testing, after fixing issues:

> "Fixes applied. Tests pass. Returning to [Review/Testing] skill for re-evaluation."

Return control to whichever skill invoked you.
