"""Pluggable Text-to-Speech (TTS) providers: zero-config Edge-TTS and Mock."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import Settings


class TtsProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def synthesize_mp3(self, text: str) -> bytes:
        """Synthesize spoken audio as MP3 bytes."""


class MockTtsProvider(TtsProvider):
    name = "mock"

    async def synthesize_mp3(self, text: str) -> bytes:
        return b""


class EdgeTtsProvider(TtsProvider):
    """Zero-config neural Chinese/English TTS powered by Microsoft Edge TTS."""

    name = "edge-tts"

    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural") -> None:
        self.voice = voice

    async def synthesize_mp3(self, text: str) -> bytes:
        if not text.strip():
            return b""
        try:
            import edge_tts

            comm = edge_tts.Communicate(text=text, voice=self.voice)
            chunks = bytearray()
            async for chunk in comm.stream():
                if chunk.get("type") == "audio":
                    chunks.extend(chunk["data"])
            return bytes(chunks)
        except Exception:
            return b""


def create_tts_provider(settings: Settings) -> TtsProvider:
    if settings.tts_provider == "edge-tts":
        return EdgeTtsProvider(voice=settings.tts_voice)
    return MockTtsProvider()
