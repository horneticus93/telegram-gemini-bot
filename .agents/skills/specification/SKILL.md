---
name: specification
description: Creates a clear, non-technical specification for a feature request — defines the problem, proposed solution, and success criteria.
---

# Specification Skill

## Purpose

Transform a user's feature request into a structured specification document that clearly describes **what** needs to be done and **why**, without prescribing **how** (no technical details).

## When to Use

This is the **first step** in the development pipeline. Use when:
- A new feature is requested
- A significant change or refactor is needed
- A bug fix requires understanding the desired behavior

## Inputs

- **User request**: free-form text describing what they want

## Process

### Step 1: Understand the Request

Read the user's request carefully. If anything is ambiguous, ask clarifying questions **before** writing the spec. Focus on understanding:
- What problem the user is experiencing or what gap exists
- What the desired end state looks like
- Who benefits from this change

### Step 2: Research Context

Before writing, review:
1. `AGENTS.md` — understand project architecture and constraints
2. Relevant source files — understand current behavior
3. `docs/plans/` — check if similar specs already exist
4. Existing tests — understand current expected behavior

### Step 3: Write the Specification

Create a file at `docs/plans/YYYY-MM-DD-<slug>-spec.md` with this structure:

```markdown
# <Feature Name> — Specification

## Problem Statement

Describe the problem or gap in plain language. What is the user pain point?
Why does the current state not satisfy the need?

## Proposed Solution

Describe the solution in verbal, non-technical terms.
What will the user experience after this is implemented?
What will change from the user's perspective?

## Success Criteria

A numbered list of observable outcomes that prove the feature works:
1. When X happens, Y should occur
2. User can do Z
3. ...

## Scope

### In Scope
- What IS included in this work

### Out of Scope
- What is explicitly NOT included (to prevent scope creep)

## Open Questions

List any unresolved questions that need answers before implementation.
```

### Step 4: Review with User

Present the specification to the user for approval. Address any feedback before proceeding.

## Output

- **Artifact**: `docs/plans/YYYY-MM-DD-<slug>-spec.md`
- **Status**: Specification approved by user

## Transition

After user approves the specification, hand off to the **Plan** skill:

> "Specification approved. Proceeding to the Plan skill to create a detailed implementation plan based on `docs/plans/<spec-file>`."

Read the Plan skill instructions at `.agents/skills/plan/SKILL.md` and follow them.
