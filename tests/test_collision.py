import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, User
from bot.handlers import handle_message, session_manager, user_memory
import os

def make_user(user_id: int, first_name: str):
    user = MagicMock(spec=User)
    user.id = user_id
    user.first_name = first_name
    user.username = f"user_{user_id}"
    return user

def make_update(text: str, chat_id: int, user: User) -> Update:
    message = MagicMock(spec=Message)
    message.text = text
    message.chat_id = chat_id
    message.from_user = user
    message.reply_text = AsyncMock()
    message.chat.type = "private" # To trigger bot response without mention

    update = MagicMock(spec=Update)
    update.message = message
    return update

@pytest.mark.asyncio
async def test_user_name_collision_repro():
    """
    This test demonstrates that currently Gemini might get confused 
    if two users have the same name, as they are both just 'Oleksandr' in history.
    """
    chat_id = 999
    user1 = make_user(1, "Oleksandr")
    user2 = make_user(2, "Oleksandr")
    
    # Store profiles
    user_memory.increment_message_count(1, chat_id, "olex1", "Oleksandr")
    user_memory.update_profile(1, "Oleksandr [1] is an engineer.")
    
    user_memory.increment_message_count(2, chat_id, "olex2", "Oleksandr")
    user_memory.update_profile(2, "Oleksandr [2] is a teacher.")

    context = MagicMock()
    context.bot.username = "bot"

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {chat_id}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.return_value = ("Hello!", False)
            mock_gemini.embed_text.return_value = [0.1] * 768
            
            with patch("bot.handlers.user_memory") as mock_memory:
                mock_memory.get_profile.return_value = "Oleksandr [2] is a teacher."
                mock_memory.get_user_facts.return_value = []
                mock_memory.get_chat_members.return_value = [(1, "Oleksandr"), (2, "Oleksandr")]
                mock_memory.search_facts_by_embedding.return_value = [
                    {
                        "fact_id": 1,
                        "scope": "user",
                        "user_id": 1,
                        "owner_name": "Oleksandr",
                        "fact_text": "Oleksandr [1] is an engineer.",
                        "score": 0.9,
                    }
                ]
                mock_memory.increment_message_count.return_value = 1
                
                # User 2 writes
                update2 = make_update("What is my job?", chat_id, user2)
                await handle_message(update2, context)
                
                # Check what was passed to Gemini
                call_kwargs = mock_gemini.ask.call_args.kwargs
                history = call_kwargs["history"]
                chat_members = call_kwargs["chat_members"]
                retrieved_profiles = call_kwargs["retrieved_profiles"]
                
                print(f"\nHistory entry author: {history[-1]['author']}")
                print(f"Chat members: {chat_members}")
                print(f"Retrieved profiles: {retrieved_profiles}")
                
                assert history[-1]["author"] == "Oleksandr [ID: 2]"
                assert "Oleksandr [ID: 2]" in chat_members
                assert "Oleksandr [ID: 1]" in retrieved_profiles[0]
