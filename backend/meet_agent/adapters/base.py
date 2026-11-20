"""Abstract MeetingAdapter protocol decoupling MeetAgent core from meeting platform transports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from ..models import ChatMessage, TranscriptSegment
from ..video.status_tile import TileState


@dataclass
class JoinConfig:
    meeting_code: str
    display_name: str
    password: str | None = None
    enable_virtual_cam: bool = True
    enable_tts: bool = True
    workspace_url: str = "http://127.0.0.1:5173"


class MeetingAdapter(ABC):
    """Unified 5-primitive meeting transport interface."""

    adapter_name: str = "base"

    @abstractmethod
    async def join(self, config: JoinConfig) -> None:
        """Join the target meeting as a visible participant."""

    @abstractmethod
    async def leave(self) -> None:
        """Leave the meeting and release A/V handles."""

    @abstractmethod
    def transcript_stream(self) -> AsyncIterator[TranscriptSegment]:
        """Yield live recognized speech segments with speaker attribution."""

    @abstractmethod
    def chat_stream(self) -> AsyncIterator[ChatMessage]:
        """Yield inbound meeting chat messages."""

    @abstractmethod
    async def send_chat(self, text: str) -> bool:
        """Send a visible text message into the meeting chat panel."""

    @abstractmethod
    async def speak_text(self, text: str) -> bool:
        """Speak text aloud into the meeting via TTS + virtual microphone."""

    @abstractmethod
    async def capture_screen(self) -> tuple[bytes | None, float]:
        """Capture current meeting/shared-screen PNG bytes and frame diff score (0..1)."""

    @abstractmethod
    async def get_active_speaker(self) -> str | None:
        """Return currently highlighted speaker name from UI/DOM if available."""

    @abstractmethod
    def update_tile_state(self, state: TileState) -> None:
        """Update Live Status Tile state pushed to virtual camera / preview."""

    @abstractmethod
    def get_tile_jpeg(self) -> bytes:
        """Return latest JPEG frame of the Agent's Live Status Tile."""
