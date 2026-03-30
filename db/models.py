from sqlalchemy import Column, String, BigInteger, Integer, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timezone


class Base(DeclarativeBase):
    pass


class Config(Base):
    __tablename__ = "config"
    key = Column(String, primary_key=True)
    value = Column(JSONB, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Chat(Base):
    __tablename__ = "chats"
    chat_id = Column(BigInteger, primary_key=True)
    title = Column(String)
    bot_aliases = Column(ARRAY(Text), default=list)
    active = Column(Boolean, default=True)


class MessageLog(Base):
    __tablename__ = "message_logs"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger)
    username = Column(String)
    role = Column(String, nullable=False)  # 'user' | 'assistant'
    content = Column(Text, nullable=False)
    content_type = Column(String, default="text")  # text|photo|url|forward
    tokens_used = Column(Integer)
    model_used = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class NodeEmbedding(Base):
    __tablename__ = "node_embeddings"
    node_id = Column(BigInteger, primary_key=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # embedding column added via raw SQL in migration (pgvector type)
