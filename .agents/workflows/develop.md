---
description: Full development pipeline — from feature idea to tested, reviewed code
---

# /develop Workflow

Run the complete development pipeline for a feature: Specification → Plan → Implementation → Review → Testing.

## Steps

1. **Read the orchestrator** at `.agents/orchestrator.md` to understand the full pipeline, state tracking, and loop limits.

2. **Specification** — Read and follow `.agents/skills/specification/SKILL.md`:
   - Understand the user's request
   - Create a spec document at `docs/plans/YYYY-MM-DD-<slug>-spec.md`
   - Get user approval before proceeding

3. **Plan** — Read and follow `.agents/skills/plan/SKILL.md`:
   - Analyze the approved spec
   - Research the codebase
   - Create a plan document at `docs/plans/YYYY-MM-DD-<slug>-plan.md`
   - Get user approval before proceeding

4. **Implementation** — Read and follow `.agents/skills/implementation/SKILL.md`:
   - Execute plan tasks in dependency order
   - Write code and tests for each task
   // turbo
   - Run `pytest -v` after each task
   - Ensure all tests pass before proceeding

5. **Review** — Read and follow `.agents/skills/review/SKILL.md`:
   - Switch to reviewer mindset
   - Evaluate code against review checklist
   - If `CHANGES_REQUESTED` → return to step 4 (max 3 cycles)
   - If `APPROVED` → proceed to step 6

6. **Testing** — Read and follow `.agents/skills/testing/SKILL.md`:
   - Analyze test coverage gaps
   - Write additional tests
   // turbo
   - Run `pytest -v`
   - If failures → return to step 4 for fixes (max 3 cycles)
   - If all pass → pipeline complete ✅

7. **Done** — Report completion summary to the user:
   - What was implemented
   - Test results
   - Files changed
