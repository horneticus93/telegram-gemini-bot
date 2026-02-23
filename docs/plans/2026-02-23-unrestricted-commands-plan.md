# Unrestricted Commands — Implementation Plan

> Based on specification: `docs/plans/2026-02-23-unrestricted-commands-spec.md`

## Technical Analysis

The current firewall for interacting with the bot is implemented using `ALLOWED_CHAT_IDS`.
In `bot/handlers.py`, `handle_message` checks this at the very beginning and returns early if the `chat_id` is not in the list.
In `bot/memory_handlers.py`, `handle_memory_command` also checks this and returns early. The callback routing `handle_memory_callback` and edit reply handler `handle_memory_edit_reply` do not explicitly check `ALLOWED_CHAT_IDS`, but they are either triggered by buttons from the command or by the main dispatcher `_message_dispatcher` in `bot/main.py`.

The dispatcher `_message_dispatcher` routes all non-command text messages to `handle_memory_edit_reply` first, and if not consumed, to `handle_message`.

To allow slash commands for everyone (specifically `/memory` for now, but enabling the pattern):
1.  Remove the `ALLOWED_CHAT_IDS` check from `handle_memory_command` in `bot/memory_handlers.py`.
2.  The interactive UI components (callbacks via `handle_memory_callback` and edit intercept via `handle_memory_edit_reply`) already do not strictly enforce `ALLOWED_CHAT_IDS`, so they will organically work once the root `/memory` command is accessible.
3.  `handle_message` in `bot/handlers.py` will keep its `ALLOWED_CHAT_IDS` check to prevent unauthorized users from conversing with the AI or taking up session memory.
4.  Tests in `tests/test_memory_handlers.py` need to be updated. Specifically, `test_memory_command_shows_facts` and `test_memory_command_no_facts` should be modified to prove they work even if the chat ID is not in `ALLOWED_CHAT_IDS`.

## Files to Modify

| File | Action | Description |
|------|--------|-------------|
| `bot/memory_handlers.py` | MODIFY | Remove `ALLOWED_CHAT_IDS` check from `handle_memory_command`. |
| `tests/test_memory_handlers.py` | MODIFY | Update tests to verify commands work for disallowed chats. |

## Sequence / Task Breakdown

### Task 1: Remove restriction from `/memory` command

**Files**: `bot/memory_handlers.py`
**Description**: Remove the lines in `handle_memory_command` that check if `chat_id` is in `ALLOWED_CHAT_IDS` and return early if not.
**Acceptance Criteria**:
- [ ] `handle_memory_command` processes requests regardless of `chat_id`.

### Task 2: Update Tests

**Files**: `tests/test_memory_handlers.py`
**Description**: Modify existing tests for `/memory` command to explicitly use a `chat_id` that is *not* in the mocked `ALLOWED_CHAT_IDS` to prove the restriction is lifted.
**Acceptance Criteria**:
- [ ] `test_memory_command_shows_facts` runs successfully when `chat_id` is not in `ALLOWED_CHAT_IDS`.
- [ ] `test_memory_command_no_facts` runs successfully when `chat_id` is not in `ALLOWED_CHAT_IDS`.
- [ ] `pytest tests/test_memory_handlers.py -v` passes.

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Unauthorized users trigger an error because they lack a profile | Low | The memory fetching safely returns empty lists/0 if a user doesn't exist in the DB. The command correctly displays "No memories stored". |
| `handle_memory_edit_reply` allows unauthorized texting | Low | `handle_memory_edit_reply` only consumes messages if the user has an active pending edit in `_pending_edits` initialized by button press. Otherwise it returns `False`, passing control to `handle_message` which immediately blocks unauthorized chats. |

## Edge Cases

1. User not in allowed chats uses `/memory` -> sees empty state.
2. User not in allowed chats tries to send normal text -> silently ignored.
3. User not in allowed chats edits a fact -> works correctly because edit flow is stateful and intentional.

## Testing Strategy

- Modify unit tests in `tests/test_memory_handlers.py` to ensure `/memory` command logic no longer depends on `ALLOWED_CHAT_IDS`.
- Existing tests in `tests/test_handlers.py` already verify that `handle_message` ignores unauthorized users.
- Command: `pytest -v tests/test_memory_handlers.py tests/test_handlers.py`
