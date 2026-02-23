# Memory Management Commands — Implementation Plan

> Based on specification: `docs/plans/2026-02-23-memory-management-commands-spec.md`

## Technical Analysis

The bot currently uses only `MessageHandler` with `~filters.COMMAND` in `main.py`. We need to add:
- A `CommandHandler` for `/memory`.
- A `CallbackQueryHandler` for inline button interactions (navigation, view, edit, delete).
- A `MessageHandler` with a filter for reply-based editing flow (user types new fact text).

All memory CRUD already exists in `UserMemory` except:
- Listing all facts for a user (with pagination) — `get_user_facts` exists but returns only text, we need IDs too.
- Deleting a single fact by ID.
- Updating a single fact's text by ID.

No schema changes needed — all operations use existing `memory_facts` columns.

### Key Design Decisions

1. **New module `bot/memory_handlers.py`** — keeps the inline-keyboard logic separate from the main message handler, avoiding bloat in `handlers.py`.
2. **Callback data encoding** — use a simple prefix scheme: `mem:list:{page}`, `mem:view:{fact_id}`, `mem:del:{fact_id}`, `mem:edit:{fact_id}` to route button presses.
3. **Edit flow** — uses `ConversationHandler` or a simple in-memory dict to track "awaiting edit text" state per `(chat_id, user_id)`. When the user taps "✏️ Edit", the bot asks for new text. The next text message from that user in that chat is captured as the replacement.
4. **Page size** — 5 facts per page (configurable constant).

## Files to Modify

| File | Action | Description |
|------|--------|-------------|
| `bot/memory.py` | MODIFY | Add `get_user_facts_page`, `delete_fact`, `update_fact_text` methods |
| `bot/memory_handlers.py` | CREATE | New module with `/memory` command handler, callback query handler, edit-reply handler |
| `bot/main.py` | MODIFY | Register new handlers (CommandHandler, CallbackQueryHandler, MessageHandler for edit replies) |
| `tests/test_memory.py` | MODIFY | Add tests for new `UserMemory` methods |
| `tests/test_memory_handlers.py` | CREATE | Tests for the `/memory` command, callback navigation, delete, edit flows |
| `tests/conftest.py` | MODIFY | Clean `memory_facts` table in reset fixture |

## Task Breakdown

### Task 1: Add CRUD methods to `UserMemory`

**Files**: `bot/memory.py`
**Description**: Add three methods:
- `get_user_facts_page(user_id, page, page_size)` → returns `(facts: list[dict], total_count: int)` where each fact dict has `id` and `fact_text` keys. Uses `LIMIT/OFFSET` and a `COUNT(*)` query.
- `delete_fact(fact_id, user_id)` → deletes the row from `memory_facts` where `id = fact_id AND user_id = user_id AND scope = 'user'`. Returns `True` if a row was deleted.
- `update_fact_text(fact_id, user_id, new_text)` → updates `fact_text` and clears `embedding` (since text changed). Returns `True` if a row was updated.

**Acceptance Criteria**:
- [ ] `get_user_facts_page` returns a page of facts with their IDs, ordered by `updated_at DESC`.
- [ ] `get_user_facts_page` returns correct `total_count` for pagination math.
- [ ] `delete_fact` removes only the targeted fact and only if it belongs to the given `user_id`.
- [ ] `update_fact_text` updates text and nullifies the embedding column.
- [ ] Both mutation methods return `False` when the target fact doesn't exist or belongs to another user.

### Task 2: Create `/memory` command and inline keyboard handlers

**Files**: `bot/memory_handlers.py` (CREATE)
**Description**: New module containing:
- `handle_memory_command(update, context)` — parses optional `user_id` arg (only in private chat), calls `get_user_facts_page`, builds inline keyboard, sends message.
- `handle_memory_callback(update, context)` — routes callback queries by prefix:
  - `mem:list:{page}` → refresh the list at a given page.
  - `mem:view:{fact_id}` → show full fact text + Edit/Delete/Back buttons.
  - `mem:del:{fact_id}` → delete fact, confirm, refresh list.
  - `mem:edit:{fact_id}` → store pending edit state, ask user to type new text.
- `handle_memory_edit_reply(update, context)` — captures the next text message from a user with a pending edit, calls `update_fact_text`, confirms, clears state.
- Module-level `_pending_edits: dict[tuple[int, int], int]` to track `(chat_id, user_id) → fact_id`.
- Constant `FACTS_PER_PAGE = 5`.
- `ALLOWED_CHAT_IDS` gate is enforced at command entry.
- Fact button labels are truncated to ~40 chars with "..." suffix.

**Acceptance Criteria**:
- [ ] `/memory` in an allowed chat shows inline buttons for the user's facts (or "no memories" message).
- [ ] Pagination buttons appear when there are more facts than `FACTS_PER_PAGE`.
- [ ] Tapping a fact shows its full text with Edit / Delete / Back buttons.
- [ ] Delete removes the fact and refreshes the list.
- [ ] Edit flow stores pending state, captures next message, updates fact, and confirms.
- [ ] In private chat, `/memory 12345` shows facts for user 12345.
- [ ] In group chat, the `user_id` argument is ignored.

**Depends on**: Task 1

### Task 3: Register handlers in `bot/main.py`

**Files**: `bot/main.py`
**Description**: Import from `bot.memory_handlers` and register:
1. `CommandHandler("memory", handle_memory_command)` — must be added *before* the general `MessageHandler`.
2. `CallbackQueryHandler(handle_memory_callback, pattern=r"^mem:")` — for inline button presses.
3. `MessageHandler(filters.TEXT & ~filters.COMMAND, handle_memory_edit_reply)` — for edit replies, must be added *before* the existing `handle_message` handler, so it can check `_pending_edits` and pass through if no pending edit.

Alternative: integrate the edit-reply check into `handle_memory_edit_reply` so it only consumes the message when a pending edit exists, and returns early otherwise so the existing `handle_message` still runs. This avoids ordering conflicts.

**Acceptance Criteria**:
- [ ] `/memory` command is recognized by the bot.
- [ ] Inline button presses trigger the callback handler.
- [ ] Edit-reply messages are captured when pending, normal messages still reach `handle_message`.
- [ ] Existing tests still pass.

**Depends on**: Task 2

### Task 4: Update test fixtures

**Files**: `tests/conftest.py`
**Description**: Add `DELETE FROM memory_facts` to the `reset_user_memory_db` fixture so facts don't leak between tests.

**Acceptance Criteria**:
- [ ] `memory_facts` table is cleaned between tests.

### Task 5: Add unit tests for new `UserMemory` methods

**Files**: `tests/test_memory.py`
**Description**: Add tests:
- `test_get_user_facts_page_returns_paginated_results` — insert >5 facts, verify page 0 returns 5, page 1 returns remainder, total_count is correct.
- `test_delete_fact_removes_fact` — insert fact, delete by ID, verify gone.
- `test_delete_fact_wrong_user_returns_false` — insert fact for user A, try to delete as user B, verify it stays.
- `test_update_fact_text_changes_text_and_clears_embedding` — insert fact with embedding, update text, verify new text and null embedding.
- `test_update_fact_text_wrong_user_returns_false`.

**Acceptance Criteria**:
- [ ] All new tests pass with `pytest tests/test_memory.py -v`.

**Depends on**: Task 1, Task 4

### Task 6: Add handler tests for `/memory` command and callbacks

**Files**: `tests/test_memory_handlers.py` (CREATE)
**Description**: Add tests using mocks following the same patterns as `test_handlers.py`:
- `test_memory_command_shows_facts` — mock `user_memory.get_user_facts_page`, verify `edit_message_text` or reply with inline keyboard.
- `test_memory_command_no_facts` — verify friendly empty message.
- `test_memory_callback_delete` — mock callback query with `mem:del:1`, verify `delete_fact` called.
- `test_memory_callback_view` — mock callback with `mem:view:1`, verify full text shown.
- `test_memory_callback_pagination` — verify page navigation.
- `test_memory_command_private_chat_user_id_override` — verify `user_id` parsing in private chat.
- `test_memory_command_group_chat_ignores_user_id` — verify `user_id` ignored in group.

**Acceptance Criteria**:
- [ ] All new tests pass with `pytest tests/test_memory_handlers.py -v`.

**Depends on**: Task 2, Task 3, Task 4

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Edit-reply handler consuming messages meant for `handle_message` | High | Check `_pending_edits` first; if no pending edit, return immediately without consuming |
| Callback data length exceeding Telegram's 64-byte limit | Low | Our prefix scheme is short (`mem:del:123` = ~11 bytes) |
| Race condition on `_pending_edits` dict | Low | Python dict operations are GIL-protected; single-process bot |

## Edge Cases

1. User with zero facts sends `/memory` → friendly "no memories" message.
2. User deletes the last fact on a page → show previous page or "no memories".
3. User taps Edit but then sends a command instead of text → pending edit should timeout or be cleared.
4. Fact text is very long → truncate button label to ~40 chars.
5. Multiple rapid button presses → Telegram `answer_callback_query` should be called to dismiss loading spinner.
6. `/memory 999` in a group chat → `999` is ignored, shows sender's facts.

## Testing Strategy

- **Unit tests**: `pytest tests/test_memory.py -v` for data-layer CRUD methods.
- **Handler tests**: `pytest tests/test_memory_handlers.py -v` for command/callback handlers.
- **Full suite**: `pytest -v` to verify no regressions.
- **Existing tests that must still pass**: all tests in `test_handlers.py`, `test_memory.py`, `test_session.py`, `test_gemini.py`.
