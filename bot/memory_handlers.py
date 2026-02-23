import logging
import math
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from .memory import UserMemory

logger = logging.getLogger(__name__)

FACTS_PER_PAGE = 5
FACT_LABEL_MAX_LEN = 40

ALLOWED_CHAT_IDS: set[int] = {
    int(cid.strip())
    for cid in os.getenv("ALLOWED_CHAT_IDS", "").split(",")
    if cid.strip()
}

user_memory = UserMemory(db_path=os.getenv("DB_PATH", "/app/data/memory.db"))

# Pending edits: (chat_id, user_id) → (fact_id, target_user_id)
_pending_edits: dict[tuple[int, int], tuple[int, int]] = {}


def _truncate(text: str, max_len: int = FACT_LABEL_MAX_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _build_list_keyboard(
    facts: list[dict], page: int, total: int, target_user_id: int
) -> InlineKeyboardMarkup:
    """Build an inline keyboard with fact buttons and pagination."""
    buttons: list[list[InlineKeyboardButton]] = []
    for fact in facts:
        label = _truncate(fact["fact_text"])
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"mem:view:{fact['id']}:{target_user_id}")]
        )

    total_pages = max(1, math.ceil(total / FACTS_PER_PAGE))
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton("◀️", callback_data=f"mem:list:{page - 1}:{target_user_id}")
        )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton("▶️", callback_data=f"mem:list:{page + 1}:{target_user_id}")
        )
    if nav_row:
        buttons.append(nav_row)

    return InlineKeyboardMarkup(buttons)


def _resolve_target_user(update: Update, args: list[str]) -> int:
    """Determine the target user_id for the /memory command.

    In private chat, an optional user_id argument is accepted.
    In group chat, always returns the sender's user_id.
    """
    sender_id = update.effective_user.id  # type: ignore[union-attr]
    is_private = update.effective_chat.type == "private"  # type: ignore[union-attr]
    if is_private and args:
        try:
            return int(args[0])
        except (ValueError, IndexError):
            pass
    return sender_id


async def handle_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /memory command — show paginated list of user facts."""
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id

    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "🔒 For your privacy, please send me the `/memory` command in our direct messages."
        )
        return

    target_user_id = _resolve_target_user(update, context.args or [])
    facts, total = user_memory.get_user_facts_page(target_user_id, page=0)

    if not facts:
        await update.message.reply_text("🧠 No memories stored yet.")
        return

    total_pages = max(1, math.ceil(total / FACTS_PER_PAGE))
    header = f"🧠 Memories (page 1/{total_pages}, {total} total):"
    keyboard = _build_list_keyboard(facts, page=0, total=total, target_user_id=target_user_id)
    await update.message.reply_text(header, reply_markup=keyboard)


async def handle_memory_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route inline button presses for the /memory UI."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    data = query.data or ""
    parts = data.split(":")

    if len(parts) < 3:
        return

    # Clear any pending edits for this user in this chat if they tap any button
    if query.message and query.from_user:
        _pending_edits.pop((query.message.chat_id, query.from_user.id), None)

    action = parts[1]

    if action == "list":
        await _cb_list(query, parts)
    elif action == "view":
        await _cb_view(query, parts)
    elif action == "del":
        await _cb_delete(query, parts)
    elif action == "edit":
        await _cb_edit(query, parts)
    elif action == "back":
        await _cb_list(query, parts)


async def _cb_list(query, parts: list[str]) -> None:
    """Show paginated fact list."""
    try:
        page = int(parts[2])
        target_user_id = int(parts[3])
    except (IndexError, ValueError):
        return

    facts, total = user_memory.get_user_facts_page(target_user_id, page=page)
    if not facts and page > 0:
        # Current page is empty (e.g. after deletion), go to previous page
        page = max(0, page - 1)
        facts, total = user_memory.get_user_facts_page(target_user_id, page=page)

    if not facts:
        await query.edit_message_text("🧠 No memories stored yet.")
        return

    total_pages = max(1, math.ceil(total / FACTS_PER_PAGE))
    header = f"🧠 Memories (page {page + 1}/{total_pages}, {total} total):"
    keyboard = _build_list_keyboard(facts, page=page, total=total, target_user_id=target_user_id)
    await query.edit_message_text(header, reply_markup=keyboard)


async def _cb_view(query, parts: list[str]) -> None:
    """Show full fact text with action buttons."""
    try:
        fact_id = int(parts[2])
        target_user_id = int(parts[3])
    except (IndexError, ValueError):
        return

    # Fetch the fact to display its full text
    facts, _ = user_memory.get_user_facts_page(target_user_id, page=0, page_size=9999)
    fact = next((f for f in facts if f["id"] == fact_id), None)

    if not fact:
        await query.edit_message_text("⚠️ Fact not found — it may have been deleted.")
        return

    text = f"📝 Fact #{fact_id}:\n\n{fact['fact_text']}"
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✏️ Edit", callback_data=f"mem:edit:{fact_id}:{target_user_id}"),
                InlineKeyboardButton("🗑 Delete", callback_data=f"mem:del:{fact_id}:{target_user_id}"),
            ],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"mem:back:0:{target_user_id}")],
        ]
    )
    await query.edit_message_text(text, reply_markup=keyboard)


async def _cb_delete(query, parts: list[str]) -> None:
    """Delete a fact and refresh the list."""
    try:
        fact_id = int(parts[2])
        target_user_id = int(parts[3])
    except (IndexError, ValueError):
        return

    deleted = user_memory.delete_fact(fact_id=fact_id, user_id=target_user_id)
    if deleted:
        logger.info("User deleted fact #%s for user_id=%s", fact_id, target_user_id)
    else:
        logger.warning("Failed to delete fact #%s for user_id=%s", fact_id, target_user_id)

    # Refresh the list at page 0
    facts, total = user_memory.get_user_facts_page(target_user_id, page=0)
    status = "✅ Deleted." if deleted else "⚠️ Fact not found."
    
    if not facts:
        await query.edit_message_text(f"{status}\n\n🧠 No memories stored yet.")
        return

    total_pages = max(1, math.ceil(total / FACTS_PER_PAGE))
    header = f"{status}\n\n🧠 Memories (page 1/{total_pages}, {total} total):"
    keyboard = _build_list_keyboard(facts, page=0, total=total, target_user_id=target_user_id)
    await query.edit_message_text(header, reply_markup=keyboard)


async def _cb_edit(query, parts: list[str]) -> None:
    """Start the edit flow — ask user to type new text."""
    try:
        fact_id = int(parts[2])
        target_user_id = int(parts[3])
    except (IndexError, ValueError):
        return

    chat_id = query.message.chat_id
    sender_id = query.from_user.id
    _pending_edits[(chat_id, sender_id)] = (fact_id, target_user_id)

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data=f"mem:view:{fact_id}:{target_user_id}")]]
    )

    await query.edit_message_text(
        f"✏️ Editing fact #{fact_id}.\n\nType the new text for this fact:",
        reply_markup=keyboard,
    )


async def handle_memory_edit_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Capture a text message if the user has a pending edit.

    Returns True if the message was consumed (edit completed), False otherwise.
    The caller should check this return value to decide whether to pass the
    message to the normal ``handle_message`` handler.
    """
    if not update.message or not update.message.text:
        return False

    user = update.message.from_user
    if user is None:
        return False

    chat_id = update.message.chat_id
    key = (chat_id, user.id)

    if key not in _pending_edits:
        return False

    fact_id, target_user_id = _pending_edits.pop(key)
    new_text = update.message.text.strip()

    if not new_text:
        await update.message.reply_text("⚠️ Empty text — edit cancelled.")
        return True

    updated = user_memory.update_fact_text(
        fact_id=fact_id, user_id=target_user_id, new_text=new_text
    )

    if updated:
        await update.message.reply_text(f"✅ Fact #{fact_id} updated.")
        logger.info("User %s updated fact #%s", user.id, fact_id)
    else:
        await update.message.reply_text(f"⚠️ Fact #{fact_id} not found — update failed.")

    return True
