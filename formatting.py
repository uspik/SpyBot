from __future__ import annotations

import html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Chat, Message, User


def escape(text: str | None) -> str:
    return html.escape(text or "", quote=False)


def user_label(user: "User | None") -> str:
    if user is None:
        return "неизвестно"
    if user.username:
        return f"@{escape(user.username)}"
    name = " ".join(part for part in (user.first_name, user.last_name) if part)
    return escape(name or f"id{user.id}")


def chat_label(chat: "Chat | None") -> str:
    if chat is None:
        return "неизвестный чат"
    if chat.title:
        return escape(chat.title)
    if chat.username:
        return f"@{escape(chat.username)}"
    if chat.first_name:
        return escape(chat.first_name)
    return f"чат {chat.id}"


def message_content(message: "Message") -> str:
    if message.text:
        return message.text
    if message.caption:
        media = _media_type(message)
        return f"[{media}] {message.caption}"

    media = _media_type(message)
    if media != "сообщение":
        return f"[{media}]"
    return "[пустое или служебное сообщение]"


def _media_type(message: "Message") -> str:
    checks = [
        (message.photo, "фото"),
        (message.video, "видео"),
        (message.voice, "голосовое"),
        (message.audio, "аудио"),
        (message.document, "файл"),
        (message.sticker, "стикер"),
        (message.animation, "GIF"),
        (message.video_note, "кружок"),
        (message.contact, "контакт"),
        (message.location, "геолокация"),
        (message.poll, "опрос"),
        (message.dice, "кубик"),
    ]
    for value, label in checks:
        if value:
            return label
    return "сообщение"
