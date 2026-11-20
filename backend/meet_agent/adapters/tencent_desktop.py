"""Windows / Linux Tencent Meeting Desktop Adapter.

Drives the official Tencent Meeting client (`WeMeetApp.exe` / Linux `wemeet`) via:
1. Official `wemeet://page/inmeeting?meeting_code=...` URL scheme + Windows UI Automation
2. PyAudioWPatch (prefers VB-Cable virtual audio, zero-install fallback to WASAPI Loopback)
3. Pluggable ASR (faster-whisper local / OpenAI-compatible API)
4. Edge-TTS + Virtual Microphone playback with EchoMuteGate
5. Pillow + pyvirtualcam 1280x720 Live Status Tile (OBS Virtual Camera / Unity Capture / v4l2loopback)
6. mss meeting window screen capture with perceptual frame-diff gating
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import subprocess
import sys
from collections.abc import AsyncIterator

import numpy as np
from PIL import Image

from ..audio.capture import EchoMuteGate, SystemAudioCapturer
from ..audio.playback import VirtualMicPlayer
from ..config import Settings
from ..models import ChatMessage, TranscriptSegment
from ..providers.asr import AsrProvider
from ..providers.tts import TtsProvider
from ..video.status_tile import LiveStatusTileRenderer, TileState
from .base import JoinConfig, MeetingAdapter


def sanitize_meeting_code(raw: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", raw or "")


def build_wemeet_url(meeting_code: str) -> str:
    clean = sanitize_meeting_code(meeting_code)
    return f"wemeet://page/inmeeting?meeting_code={clean}"


class TencentMeetingDesktopAdapter(MeetingAdapter):
    adapter_name = "tencent-desktop"

    def __init__(
        self,
        settings: Settings,
        asr: AsrProvider,
        tts: TtsProvider,
        tile_renderer: LiveStatusTileRenderer | None = None,
    ) -> None:
        self.settings = settings
        self.asr = asr
        self.tts = tts
        self.tile_renderer = tile_renderer or LiveStatusTileRenderer()
        self.echo_gate = EchoMuteGate()
        self.capturer = SystemAudioCapturer(
            device_hint=settings.audio_input_hint,
            echo_gate=self.echo_gate,
        )
        self.player = VirtualMicPlayer(
            device_hint=settings.audio_output_hint,
            echo_gate=self.echo_gate,
        )
        self._tile_state = TileState(agent_name=settings.agent_name)
        self._running = False
        self._tile_task: asyncio.Task[None] | None = None
        self._chat_queue: asyncio.Queue[ChatMessage] = asyncio.Queue(maxsize=64)
        self._prev_thumb: np.ndarray | None = None
        self._active_speaker: str | None = None
        self._config: JoinConfig | None = None

    async def join(self, config: JoinConfig) -> None:
        self._config = config
        self._running = True
        self._tile_state.agent_name = config.display_name
        self._tile_state.workspace_url = config.workspace_url

        # 1. Start virtual camera if requested and installed
        if config.enable_virtual_cam:
            self.tile_renderer.start_virtual_camera(
                backend=self.settings.virtual_cam_backend or None,
                fps=15,
            )
            self._tile_task = asyncio.create_task(self._tile_push_loop())

        # 2. Launch / invoke Tencent Meeting desktop app via official URL scheme
        clean_code = sanitize_meeting_code(config.meeting_code)
        if clean_code:
            await asyncio.to_thread(self._launch_client_and_join, clean_code, config.display_name, config.password)

        # 3. Start system audio capture (VB-Cable or WASAPI Loopback)
        loop = asyncio.get_running_loop()
        self.capturer.start(loop)

    def _launch_client_and_join(self, meeting_code: str, display_name: str, password: str | None) -> None:
        url = build_wemeet_url(meeting_code)
        if sys.platform == "win32":
            try:
                os.startfile(url)  # type: ignore[attr-defined]
            except Exception:
                return
            self._automate_windows_join(display_name, password)
        elif sys.platform.startswith("linux"):
            for cmd in (["xdg-open", url], ["/opt/wemeet/wemeetapp.sh", url]):
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                except Exception:
                    continue

    def _automate_windows_join(self, display_name: str, password: str | None) -> None:
        """Best-effort Windows UI Automation to fill display name/password and confirm join."""
        if sys.platform != "win32":
            return
        try:
            import time

            import uiautomation as auto  # type: ignore[import-untyped]

            with auto.UIAutomationInitializerInThread():
                # Wait briefly for Tencent Meeting join dialog to appear
                for _ in range(10):
                    win = auto.WindowControl(searchDepth=1, SubName="腾讯会议")
                    if win.Exists(0.5):
                        # Attempt to locate nickname edit field and set Agent's visible name
                        edits = []
                        for ctrl, _depth in auto.WalkControl(win, maxDepth=6):
                            if ctrl.ControlTypeName == "EditControl":
                                edits.append(ctrl)
                        if len(edits) >= 2 and display_name:
                            try:
                                edits[1].Click()
                                edits[1].SendKeys("{Ctrl}a" + display_name)
                            except Exception:
                                pass

                        # Click join button if present
                        join_btn = win.ButtonControl(SubName="加入会议")
                        if join_btn.Exists(0.5):
                            join_btn.Click()
                            time.sleep(1.0)

                        # Handle optional password prompt
                        if password:
                            pwd_edit = win.EditControl(SubName="密码")
                            if pwd_edit.Exists(1.5):
                                pwd_edit.Click()
                                pwd_edit.SendKeys(password + "{Enter}")
                        break
                    time.sleep(0.5)
        except Exception:
            # Never crash if Tencent Meeting UI layout changed; user can still click Join manually
            return

    async def _tile_push_loop(self) -> None:
        while self._running:
            self._tile_state.audio_level = self.capturer.current_level
            if self.tile_renderer.vcam_active:
                self.tile_renderer.push_to_virtual_camera(self._tile_state)
            await asyncio.sleep(1.0 / 15.0)

    async def leave(self) -> None:
        self._running = False
        if self._tile_task:
            self._tile_task.cancel()
        self.capturer.stop()
        self.tile_renderer.stop_virtual_camera()

    async def transcript_stream(self) -> AsyncIterator[TranscriptSegment]:
        async for audio_seg in self.capturer.segments():
            if not self._running:
                break
            text = await self.asr.transcribe(audio_seg.pcm16, audio_seg.sample_rate)
            if not text:
                continue
            speaker = await self.get_active_speaker() or "腾讯会议参会者"
            yield TranscriptSegment(
                speaker=speaker,
                text=text,
                source="audio",
            )

    async def chat_stream(self) -> AsyncIterator[ChatMessage]:
        while self._running:
            try:
                msg = await asyncio.wait_for(self._chat_queue.get(), timeout=0.5)
                yield msg
            except asyncio.TimeoutError:
                continue

    async def send_chat(self, text: str) -> bool:
        """Best-effort send chat into Tencent Meeting chat input box via Windows UIA."""
        if sys.platform != "win32":
            return False
        return await asyncio.to_thread(self._send_chat_windows, text)

    def _send_chat_windows(self, text: str) -> bool:
        try:
            import uiautomation as auto  # type: ignore[import-untyped]

            with auto.UIAutomationInitializerInThread():
                win = auto.WindowControl(searchDepth=1, SubName="腾讯会议")
                if not win.Exists(0.5):
                    return False
                # Find chat edit box if chat drawer is open
                chat_edit = win.EditControl(SubName="说点什么")
                if not chat_edit.Exists(0.5):
                    chat_btn = win.ButtonControl(SubName="聊天")
                    if chat_btn.Exists(0.5):
                        chat_btn.Click()
                chat_edit = win.EditControl(SubName="说点什么")
                if chat_edit.Exists(1.0):
                    chat_edit.Click()
                    auto.SetClipboardText(text)
                    chat_edit.SendKeys("{Ctrl}v{Enter}")
                    return True
        except Exception:
            return False
        return False

    async def speak_text(self, text: str) -> bool:
        if not self._config or not self._config.enable_tts or not text.strip():
            return False
        mp3_bytes = await self.tts.synthesize_mp3(text)
        if not mp3_bytes:
            return False
        return await self.player.play_mp3_bytes(mp3_bytes)

    @staticmethod
    def _mp3_to_wav_ffmpeg(mp3_bytes: bytes) -> bytes | None:
        try:
            proc = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-f", "wav", "-ar", "16000", "-ac", "1", "pipe:1"],
                input=mp3_bytes,
                capture_output=True,
                timeout=15,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout
        except Exception:
            return None
        return None

    async def capture_screen(self) -> tuple[bytes | None, float]:
        return await asyncio.to_thread(self._capture_screen_sync)

    def _capture_screen_sync(self) -> tuple[bytes | None, float]:
        try:
            import mss

            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(monitor)
                img = Image.frombytes("RGB", shot.size, shot.rgb)
                thumb = np.asarray(img.resize((160, 90)), dtype=np.float32) / 255.0
                diff = 1.0
                if self._prev_thumb is not None:
                    diff = float(np.mean(np.abs(thumb - self._prev_thumb)))
                self._prev_thumb = thumb

                # Downscale to max 1280px wide for compact VLM / preview transfer
                if img.width > 1280:
                    ratio = 1280 / img.width
                    img = img.resize((1280, int(img.height * ratio)))
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=75)
                return buf.getvalue(), diff
        except Exception:
            return None, 0.0

    async def get_active_speaker(self) -> str | None:
        if sys.platform == "win32":
            detected = await asyncio.to_thread(self._detect_active_speaker_windows)
            if detected:
                self._active_speaker = detected
        return self._active_speaker

    def _detect_active_speaker_windows(self) -> str | None:
        try:
            import uiautomation as auto  # type: ignore[import-untyped]

            with auto.UIAutomationInitializerInThread():
                win = auto.WindowControl(searchDepth=1, SubName="腾讯会议")
                if not win.Exists(0.2):
                    return None
                for ctrl, _depth in auto.WalkControl(win, maxDepth=4):
                    name = ctrl.Name or ""
                    if "正在讲话" in name or "发言" in name:
                        return name.replace("正在讲话：", "").replace("正在讲话:", "").strip() or None
        except Exception:
            return None
        return None

    def update_tile_state(self, state: TileState) -> None:
        self._tile_state = state

    def get_tile_jpeg(self) -> bytes:
        return self.tile_renderer.render_jpeg_bytes(self._tile_state)
