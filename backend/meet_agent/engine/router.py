"""Wake-word, chat @mention, and privacy control command router."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PAUSE_PATTERNS = ("暂停记录", "停止监听", "先别记", "暂停听会", "pause recording", "stop listening", "/pause")
RESUME_PATTERNS = ("恢复记录", "继续监听", "继续记录", "resume recording", "/resume")
LEAVE_PATTERNS = ("退出会议", "你可以退会了", "离开会议", "请退会", "leave meeting", "/leave")
CHAT_PREFIXES = ("@agent", "@小会", "@meetagent", "@antigravity", "/doc", "/board", "/ask", "/sync")


@dataclass
class RoutedIntent:
    action: Literal["pause", "resume", "leave", "interactive", "observe"]
    cleaned_query: str = ""
    matched_trigger: str | None = None


def route_utterance(text: str, wake_words: list[str], *, is_chat: bool = False) -> RoutedIntent:
    """Classify an utterance or chat message into privacy control, interactive query, or passive observation."""
    stripped = text.strip()
    lower = stripped.lower()

    # 1. Privacy & lifecycle controls take absolute precedence
    for kw in LEAVE_PATTERNS:
        if kw in lower:
            return RoutedIntent(action="leave", cleaned_query=stripped, matched_trigger=kw)
    for kw in PAUSE_PATTERNS:
        if kw in lower:
            return RoutedIntent(action="pause", cleaned_query=stripped, matched_trigger=kw)
    for kw in RESUME_PATTERNS:
        if kw in lower:
            return RoutedIntent(action="resume", cleaned_query=stripped, matched_trigger=kw)

    # 2. Chat direct commands / mentions
    if is_chat:
        for prefix in CHAT_PREFIXES:
            if prefix in lower:
                return RoutedIntent(action="interactive", cleaned_query=stripped, matched_trigger=prefix)

    # 3. Spoken wake words
    for word in wake_words:
        w = word.strip()
        if w and w.lower() in lower:
            return RoutedIntent(action="interactive", cleaned_query=stripped, matched_trigger=w)

    return RoutedIntent(action="observe", cleaned_query=stripped)
