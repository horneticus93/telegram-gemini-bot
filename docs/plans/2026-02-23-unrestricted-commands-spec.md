# Unrestricted Slash Commands — Specification

## Problem Statement

Currently, the bot strictly limits all interactions to users or chats whose IDs are present in the `ALLOWED_CHAT_IDS` environment variable. This means if a user is not in an allowed chat, they cannot interact with the bot at all, even via direct private messages using built-in commands like `/memory`. The user wants to open up command execution so that any user can use slash commands globally, while still preventing unauthorized users from chatting with the bot's AI (texting).

## Proposed Solution

We will remove the restrictive firewall for slash commands. When a user sends a command (like `/memory`), the bot will process it and respond appropriately regardless of whether the user's `chat_id` is in the `ALLOWED_CHAT_IDS` list or not.

However, standard text messages (conversing with the Gemini AI) will remain strictly gated. If an unauthorized user tries to just text the bot, the bot will silently ignore the message, exactly as it does today.

This change focuses on ensuring commands and their interactive UI flows (like inline buttons and edit states) work for everyone.

## Success Criteria

1. An unauthorized user (not in `ALLOWED_CHAT_IDS`) can execute the `/memory` command in a private chat and see the bot's response.
2. An unauthorized user can interact with the inline buttons (pagination, view, edit, delete) on the `/memory` UI.
3. An unauthorized user can complete the edit flow for a fact (which involves sending a text message that gets intercepted as an edit).
4. An unauthorized user sending a regular text message (not a command, and not part of an edit flow) is ignored.
5. Authorized users continue to be able to text the bot and use all commands normally.

## Scope

### In Scope
- Removing the `ALLOWED_CHAT_IDS` check from `/memory` command handlers.
- Ensuring that standard AI text interactions remain protected by `ALLOWED_CHAT_IDS` in `bot/handlers.py`.
- Ensuring the edit-reply flow works for unauthorized users, while regular messages do not.

### Out of Scope
- Adding new commands.
- Changing how the `ALLOWED_CHAT_IDS` list is configured or structured.
- Modifying the AI conversation logic itself.

## Open Questions

None at this moment.
