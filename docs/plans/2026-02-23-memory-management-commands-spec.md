# Memory Management Commands — Specification

## Problem Statement

Users have no visibility or control over the facts the bot stores about them. If the LLM incorrectly extracts a fact (e.g., misattributes a preference or records situational banter as a permanent trait), the user has no way to discover or correct the mistake. This erodes trust and can lead to awkward or wrong responses based on stale/inaccurate memory.

## Proposed Solution

Add a single `/memory` Telegram command that displays stored facts as an **interactive inline keyboard UI**. Each fact is a tappable button. Tapping a fact opens a sub-menu where the user can **edit** or **delete** it. Pagination handles large fact lists.

### Interaction Flow

1. **User sends `/memory`** → Bot replies with a message containing inline buttons, one per fact (showing truncated fact text). Navigation buttons (◀ / ▶) appear if facts exceed one page.
2. **User taps a fact button** → The message updates to show the full fact text with two action buttons: "✏️ Edit" and "🗑 Delete", plus "⬅️ Back" to return to the list.
3. **User taps "🗑 Delete"** → The fact is deleted from the database. The message updates to confirm deletion, then returns to the updated list.
4. **User taps "✏️ Edit"** → The bot asks the user to type the new text in a reply message. Once the user replies, the fact is updated and the bot confirms.
5. **User taps "⬅️ Back"** → Returns to the paginated fact list.

### Target User Identification

- By default, `/memory` shows facts for the user who sent the command.
- In a **private (1-on-1) chat** with the bot, `/memory {user_id}` shows facts for the specified user.
- In a **group chat**, the `{user_id}` parameter is ignored — the command always shows the sender's own facts.

## Success Criteria

1. `/memory` replies with an inline keyboard listing the user's active facts (scope=user), paginated.
2. Tapping a fact button shows the full fact text with Edit and Delete action buttons.
3. "🗑 Delete" removes the fact from the database and refreshes the list.
4. "✏️ Edit" prompts the user for new text; upon reply, the fact is updated in the database.
5. Pagination (◀ / ▶) works correctly when there are more facts than fit on one page.
6. In a private chat, `/memory {user_id}` displays facts for the specified user.
7. In a group chat, the optional `{user_id}` is ignored.
8. Invalid arguments or empty memory produce friendly messages.
9. All new functionality is covered by automated tests.
10. The `ALLOWED_CHAT_IDS` gate applies — the command only works in allowed chats.

## Scope

### In Scope
- `/memory` command handler with inline keyboard UI.
- Callback query handlers for navigation, viewing, editing, and deleting facts.
- New methods in `UserMemory` for listing and deleting individual facts.
- Pagination logic (configurable page size).
- Registration of new handlers in `bot/main.py`.
- Unit tests for the new handlers and memory methods.

### Out of Scope
- Managing chat-scope facts (only user-scope facts are manageable via this command).
- Admin-only commands or role-based permissions beyond the private-chat `user_id` override.
- Editing/deleting facts from the inline keyboard in a non-allowed chat.

## Open Questions

None — requirements are clear from the user's request.
