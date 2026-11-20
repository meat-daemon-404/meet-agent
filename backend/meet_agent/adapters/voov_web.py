"""Phase 2 Pluggable Adapter Scaffold: VooV Meeting Web (`https://voovmeeting.com/r`) via Playwright + Xvfb."""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..models import ChatMessage, TranscriptSegment
from ..video.status_tile import LiveStatusTileRenderer, TileState
from .base import JoinConfig, MeetingAdapter


class VooVWebAdapter(MeetingAdapter):
    """Extensible Phase 2 browser bot adapter targeting `https://voovmeeting.com/r`.

    Designed for Linux Docker + Xvfb + PulseAudio multi-concurrency deployments.
    """

    adapter_name = "voov-web"
    join_url = "https://voovmeeting.com/r"

    def __init__(self, tile_renderer: LiveStatusTileRenderer | None = None) -> None:
        self.tile_renderer = tile_renderer or LiveStatusTileRenderer()
        self._tile_state = TileState()

    async def join(self, config: JoinConfig) -> None:
        raise NotImplementedError(
            "VooVWebAdapter 是 Phase 2 容器化扩展位（目标入口 https://voovmeeting.com/r）。"
            "首期请使用 `tencent-desktop`（Windows/Linux 腾讯会议客户端）或 `simulator`。"
        )

    async def leave(self) -> None:
        return

    async def transcript_stream(self) -> AsyncIterator[TranscriptSegment]:
        if False:
            yield  # pragma: no cover

    async def chat_stream(self) -> AsyncIterator[ChatMessage]:
        if False:
            yield  # pragma: no cover

    async def send_chat(self, text: str) -> bool:
        return False

    async def speak_text(self, text: str) -> bool:
        return False

    async def capture_screen(self) -> tuple[bytes | None, float]:
        return None, 0.0

    async def get_active_speaker(self) -> str | None:
        return None

    def update_tile_state(self, state: TileState) -> None:
        self._tile_state = state

    def get_tile_jpeg(self) -> bytes:
        return self.tile_renderer.render_jpeg_bytes(self._tile_state)
