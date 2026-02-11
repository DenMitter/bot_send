from __future__ import annotations

import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MailingStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    done = "done"
    failed = "failed"


class RecipientStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class MessageType(str, enum.Enum):
    text = "text"
    photo = "photo"
    video = "video"
    sticker = "sticker"
    document = "document"
    voice = "voice"
    audio = "audio"


class TargetSource(str, enum.Enum):
    subscribers = "subscribers"
    parsed = "parsed"
    chats = "chats"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True)
    session_string: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    mailings: Mapped[List["Mailing"]] = relationship(back_populates="account")


class BotSubscriber(Base):
    __tablename__ = "bot_subscribers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    first_name: Mapped[Optional[str]] = mapped_column(String(64))
    last_name: Mapped[Optional[str]] = mapped_column(String(64))
    language: Mapped[Optional[str]] = mapped_column(String(8))
    referrer_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    referred_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserBalance(Base):
    __tablename__ = "user_balances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    balance: Mapped[float] = mapped_column(default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PriceConfig(Base):
    __tablename__ = "price_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    price: Mapped[float] = mapped_column(default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BalanceTransaction(Base):
    __tablename__ = "balance_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    amount: Mapped[float] = mapped_column()
    tx_type: Mapped[str] = mapped_column(String(32))
    reason: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ParsedUser(Base):
    __tablename__ = "parsed_users"
    __table_args__ = (UniqueConstraint("owner_id", "user_id", name="ux_parsed_users_owner_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    first_name: Mapped[Optional[str]] = mapped_column(String(64))
    last_name: Mapped[Optional[str]] = mapped_column(String(64))
    access_hash: Mapped[Optional[int]] = mapped_column(BigInteger)
    source: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ParsedChat(Base):
    __tablename__ = "parsed_chats"
    __table_args__ = (UniqueConstraint("owner_id", "chat_id", name="ux_parsed_chats_owner_chat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    username: Mapped[Optional[str]] = mapped_column(String(64))
    chat_type: Mapped[Optional[str]] = mapped_column(String(32))
    access_hash: Mapped[Optional[int]] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ParseFilter(Base):
    __tablename__ = "parse_filters"

    owner_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="all")
    gender: Mapped[str] = mapped_column(String(16), default="any")
    language: Mapped[str] = mapped_column(String(16), default="any")
    activity: Mapped[str] = mapped_column(String(16), default="any")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReferralReward(Base):
    __tablename__ = "referral_rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, index=True)
    referral_id: Mapped[int] = mapped_column(BigInteger, index=True)
    amount: Mapped[float] = mapped_column()
    source_tx_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Mailing(Base):
    __tablename__ = "mailings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id"))
    chat_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    status: Mapped[MailingStatus] = mapped_column(Enum(MailingStatus), default=MailingStatus.pending)
    message_type: Mapped[MessageType] = mapped_column(Enum(MessageType))
    text: Mapped[Optional[str]] = mapped_column(Text)
    media_path: Mapped[Optional[str]] = mapped_column(String(512))
    media_file_id: Mapped[Optional[str]] = mapped_column(String(512))
    sticker_set_name: Mapped[Optional[str]] = mapped_column(String(255))
    sticker_set_index: Mapped[Optional[int]] = mapped_column(Integer)
    mention: Mapped[bool] = mapped_column(Boolean, default=False)

    target_source: Mapped[TargetSource] = mapped_column(Enum(TargetSource))
    delay_seconds: Mapped[float] = mapped_column(default=1.0)
    limit_count: Mapped[int] = mapped_column(default=0)
    repeat_delay_seconds: Mapped[float] = mapped_column(default=0.0)
    repeat_count: Mapped[int] = mapped_column(default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account: Mapped[Optional[Account]] = relationship(back_populates="mailings")
    recipients: Mapped[List["MailingRecipient"]] = relationship(back_populates="mailing")


class MailingRecipient(Base):
    __tablename__ = "mailing_recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mailing_id: Mapped[int] = mapped_column(ForeignKey("mailings.id"))
    user_id: Mapped[int] = mapped_column(BigInteger)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    access_hash: Mapped[Optional[int]] = mapped_column(BigInteger)

    status: Mapped[RecipientStatus] = mapped_column(Enum(RecipientStatus), default=RecipientStatus.pending)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    error: Mapped[Optional[str]] = mapped_column(Text)

    mailing: Mapped[Mailing] = relationship(back_populates="recipients")
