---
name: review
description: Performs a thorough code review of implemented changes — checks quality, contract compliance, edge cases, and test coverage. Returns issues or approves.
---

# Review Skill

## Purpose

Act as an independent code reviewer. Evaluate all changes made by the Implementation skill for quality, correctness, maintainability, and compliance with project standards.

## When to Use

This is the **fourth step** in the development pipeline. Use after the Implementation skill completes its work.

## Inputs

- **Specification path**: the original spec for context
- **Plan path**: the implementation plan for expected behavior
- **Changed files**: list of all files modified or created

## Process

### Step 1: Adopt Reviewer Mindset

> **CRITICAL**: You are now a **reviewer**, not the implementer. Be objective, skeptical, and thorough. Question assumptions. Look for what could go wrong.

Forget any attachment to the code you may have written. Your job is to find problems.

### Step 2: Review Checklist

Go through each changed file and evaluate against this checklist:

#### Code Quality
- [ ] Code is readable and follows existing project style
- [ ] No unnecessary complexity or over-engineering
- [ ] Functions are focused (single responsibility)
- [ ] Variable/function names are clear and descriptive
- [ ] No dead code, commented-out code, or debug artifacts
- [ ] Error handling is adequate (no silent failures)

#### AGENTS.md Contract Compliance
- [ ] `GeminiClient.ask()` return type preserved: `tuple[str, bool]`
- [ ] Session entry shape preserved: `{role, text, author}`
- [ ] Memory layer contracts honored (embeddings, similarity, conflict resolution)
- [ ] Async boundaries are correct
- [ ] Module-level state patterns preserved

#### Architecture
- [ ] Changes respect module boundaries
- [ ] No circular dependencies introduced
- [ ] Dependency injection / patchability maintained for tests
- [ ] Database changes have Alembic migration (if applicable)

#### Edge Cases & Robustness
- [ ] Empty/null inputs handled
- [ ] Telegram 4096-char message limit respected
- [ ] Race conditions considered for background tasks
- [ ] `ALLOWED_CHAT_IDS` parsing not affected

#### Test Coverage
- [ ] Every new function/method has a test
- [ ] Every changed behavior has updated tests
- [ ] Edge cases are tested
- [ ] Tests follow project patterns (`pytest`, `MagicMock`, `AsyncMock`)
- [ ] No tests are skipped or ignored

#### Documentation
- [ ] `AGENTS.md` updated if contracts changed
- [ ] `.env.example` updated if new env vars added
- [ ] `README.md` updated if user-facing behavior changed

### Step 3: Write Review Report

Create a structured review report:

```markdown
# Code Review Report

## Summary

Brief overall assessment.

## Verdict: APPROVED / CHANGES_REQUESTED

## Findings

### Critical Issues (must fix)
1. [File:Line] Description of the issue — why it's a problem — suggested fix

### Warnings (should fix)
1. [File:Line] Description — suggestion

### Suggestions (nice to have)
1. [File:Line] Description — suggestion

## Checklist Results

| Category | Status |
|----------|--------|
| Code Quality | ✅ / ⚠️ / ❌ |
| Contract Compliance | ✅ / ⚠️ / ❌ |
| Architecture | ✅ / ⚠️ / ❌ |
| Edge Cases | ✅ / ⚠️ / ❌ |
| Test Coverage | ✅ / ⚠️ / ❌ |
| Documentation | ✅ / ⚠️ / ❌ |
```

## Output

- **Review report**: structured findings with verdict
- **Verdict**: `APPROVED` or `CHANGES_REQUESTED`

## Transition

### If `CHANGES_REQUESTED`

Hand off back to the **Implementation** skill with the issue list:

> "Review found issues. Returning to Implementation skill for fixes."
> Issues to fix:
> 1. Issue description
> 2. ...

Read the Implementation skill instructions at `.agents/skills/implementation/SKILL.md` (Fix Flow) and follow them.

After fixes are applied, **re-run this Review skill** to verify the fixes.

> **Loop limit**: Maximum **3 review cycles**. If issues persist after 3 cycles, escalate to the user with a summary of unresolved problems.

### If `APPROVED`

Hand off to the **Testing** skill:

> "Code review passed. Proceeding to Testing skill for comprehensive test coverage."

Read the Testing skill instructions at `.agents/skills/testing/SKILL.md` and follow them.
