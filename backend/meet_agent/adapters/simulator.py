"""High-fidelity Chinese multi-speaker meeting simulator for zero-setup end-to-end testing."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from ..models import ChatMessage, TranscriptSegment
from ..video.status_tile import LiveStatusTileRenderer, TileState
from .base import JoinConfig, MeetingAdapter

DEMO_SCRIPT: list[tuple[str, str, str]] = [
    (
        "audio",
        "陈产品",
        "大家好，今天我们评审腾讯会议 AI 参会者项目，目标是让 Antigravity 和 OpenCode 这类现有 Agent 直接以参会者身份进会协作。",
    ),
    (
        "audio",
        "李开发",
        "要不我们也可以先考虑做个 Chrome 浏览器插件，只抓网页端字幕，开发量会不会更小？",
    ),
    (
        "audio",
        "王测试",
        "有个风险不太确定：国内很多团队开了仅企业内部成员入会或者强实名，如果只靠 VooV 网页版会不会被拦截？",
    ),
    (
        "audio",
        "李开发",
        "感觉可以先把浏览器和桌面端都留好扩展位，我个人倾向于后面再补网页版。",
    ),
    (
        "audio",
        "张架构",
        "那就这么定了，首期最终确认采用可插拔架构：会议身体优先实现 Windows 腾讯会议桌面端适配器，大脑直接桥接原生 agy stream-json 和通用 ACP 协议。",
    ),
    (
        "audio",
        "张架构",
        "林工负责本周五前把 Windows UIA 自动入会和 WASAPI Loopback 零配置音频采集跑通。",
    ),
    (
        "audio",
        "陈产品",
        "另外还需要明天下午前补一下虚拟摄像头状态卡和双语 README 的端到端测试用例。",
    ),
    (
        "audio",
        "陈产品",
        "小会，结合我们刚才聊的模块划分，帮我们在协同工作台实时画一个系统架构白板吧。",
    ),
    (
        "chat",
        "张架构",
        "@Agent 请把今天明确拍板的决策同步到团队看板，注意别把未定想法发出去。",
    ),
]


class SimulatorAdapter(MeetingAdapter):
    """Plays a realistic meeting timeline while also accepting live manual utterances & chat."""

    adapter_name = "simulator"

    def __init__(
        self,
        tile_renderer: LiveStatusTileRenderer | None = None,
        step_interval_sec: float = 2.8,
        auto_play: bool = True,
    ) -> None:
        self.tile_renderer = tile_renderer or LiveStatusTileRenderer()
        self.step_interval_sec = step_interval_sec
        self.auto_play = auto_play
        self._tile_state = TileState()
        self._running = False
        self._active_speaker: str | None = None
        self._transcript_queue: asyncio.Queue[TranscriptSegment] = asyncio.Queue()
        self._chat_queue: asyncio.Queue[ChatMessage] = asyncio.Queue()
        self._driver_task: asyncio.Task[None] | None = None
        self._script_index = 0
        self.outbound_chats: list[str] = []
        self.spoken_texts: list[str] = []

    async def join(self, config: JoinConfig) -> None:
        self._running = True
        self._script_index = 0
        self._tile_state.agent_name = config.display_name
        self._tile_state.workspace_url = config.workspace_url
        if self.auto_play:
            self._driver_task = asyncio.create_task(self._script_driver())

    async def _script_driver(self) -> None:
        try:
            while self._running and self._script_index < len(DEMO_SCRIPT):
                await asyncio.sleep(self.step_interval_sec)
                if not self._running:
                    break
                await self.trigger_next_script_line()
        except asyncio.CancelledError:
            return

    async def trigger_next_script_line(self) -> bool:
        if self._script_index >= len(DEMO_SCRIPT):
            return False
        kind, speaker, text = DEMO_SCRIPT[self._script_index]
        self._script_index += 1
        self._active_speaker = speaker
        if kind == "chat":
            await self._chat_queue.put(ChatMessage(sender=speaker, text=text, direction="inbound"))
        else:
            await self._transcript_queue.put(TranscriptSegment(speaker=speaker, text=text, source="simulator"))
        return True

    async def inject_utterance(self, speaker: str, text: str) -> None:
        self._active_speaker = speaker
        await self._transcript_queue.put(TranscriptSegment(speaker=speaker, text=text, source="manual"))

    async def inject_chat(self, sender: str, text: str) -> None:
        self._active_speaker = sender
        await self._chat_queue.put(ChatMessage(sender=sender, text=text, direction="inbound"))

    async def leave(self) -> None:
        self._running = False
        if self._driver_task:
            self._driver_task.cancel()

    async def transcript_stream(self) -> AsyncIterator[TranscriptSegment]:
        while self._running:
            try:
                seg = await asyncio.wait_for(self._transcript_queue.get(), timeout=0.4)
                yield seg
            except asyncio.TimeoutError:
                continue

    async def chat_stream(self) -> AsyncIterator[ChatMessage]:
        while self._running:
            try:
                msg = await asyncio.wait_for(self._chat_queue.get(), timeout=0.4)
                yield msg
            except asyncio.TimeoutError:
                continue

    async def send_chat(self, text: str) -> bool:
        self.outbound_chats.append(text)
        return True

    async def speak_text(self, text: str) -> bool:
        self.spoken_texts.append(text)
        return True

    async def capture_screen(self) -> tuple[bytes | None, float]:
        return None, 0.0

    async def get_active_speaker(self) -> str | None:
        return self._active_speaker

    def update_tile_state(self, state: TileState) -> None:
        self._tile_state = state

    def get_tile_jpeg(self) -> bytes:
        return self.tile_renderer.render_jpeg_bytes(self._tile_state)
