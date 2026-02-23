---
name: testing
description: Writes comprehensive tests, runs the full suite, and ensures everything passes. Loops back to Implementation for fixes if tests fail.
---

# Testing Skill

## Purpose

Ensure the implemented feature has thorough test coverage and that the entire test suite passes. This is the final quality gate before the feature is considered done.

## When to Use

This is the **fifth and final step** in the development pipeline. Use after the Review skill approves the code.

## Inputs

- **Specification path**: for understanding expected behavior
- **Plan path**: for knowing which tasks were implemented
- **Changed files**: list of all modified/created files

## Process

### Step 1: Analyze Existing Coverage

1. List all changed/new production code files
2. For each, check which tests already exist in `tests/`
3. Identify coverage gaps:
   - New functions without tests
   - Changed behavior without updated tests
   - Missing edge case coverage
   - Missing error path coverage

### Step 2: Write Additional Tests

For each coverage gap, write tests following project conventions:

#### Test Conventions (from `AGENTS.md`)
- Framework: `pytest` + `pytest-asyncio`
- Config: `pytest.ini` with `asyncio_mode = auto`
- Mocking: `MagicMock` / `AsyncMock` from `unittest.mock`
- Patching: `patch("bot.module.target")` for module-level singletons
- DB tests: temporary SQLite DB + Alembic migration

#### Test Categories to Cover

1. **Happy path tests** — normal expected behavior
2. **Edge case tests** — boundary values, empty inputs, large inputs
3. **Error path tests** — what happens when things go wrong
4. **Integration tests** — components working together
5. **Regression tests** — ensure old behavior is not broken

#### Test Writing Guidelines

- One test function per behavior (not per function)
- Descriptive test names: `test_<what>_<when>_<expected_result>`
- Use fixtures for shared setup
- Assert specific values, not just "no exception"
- Test both the return value AND side effects

### Step 3: Run Full Test Suite

```bash
pytest -v
```

Evaluate the results:
- All tests pass → proceed to Step 4
- Tests fail → go to Step 3a

#### Step 3a: Handle Failures

1. Analyze each failure:
   - Is it a **test bug**? → Fix the test directly
   - Is it a **code bug**? → Invoke the Implementation skill (Fix Flow)

2. If invoking Implementation skill:

   > "Test failures found. Returning to Implementation skill for fixes."
   > Failures to fix:
   > 1. `test_file.py::test_name` — description of failure
   > 2. ...

   Read the Implementation skill at `.agents/skills/implementation/SKILL.md` (Fix Flow).

3. After fixes, **re-run the full test suite**

   > **Loop limit**: Maximum **3 fix cycles**. If tests still fail after 3 cycles, escalate to the user with a summary of persistent failures.

### Step 4: Final Verification

1. Run the full test suite one final time:
   ```bash
   pytest -v
   ```

2. Confirm:
   - [ ] All tests pass
   - [ ] No tests are skipped or xfailed without reason
   - [ ] New code has test coverage
   - [ ] Edge cases are covered
   - [ ] Error paths are covered

3. Produce a brief test summary:
   ```
   Tests: X passed, 0 failed, 0 skipped
   New tests added: Y
   Files covered: [list]
   ```

## Output

- **New/updated test files**: comprehensive test coverage
- **Green test suite**: `pytest -v` all pass
- **Test summary**: pass count, new tests, covered files

## Transition

### Pipeline Complete ✅

> "All tests pass. Feature implementation is complete."
> 
> Summary:
> - Specification: `docs/plans/<spec-file>`
> - Plan: `docs/plans/<plan-file>`
> - Tests: X total, Y new
> - All acceptance criteria met

Report the completion to the user with a summary of everything that was done.
