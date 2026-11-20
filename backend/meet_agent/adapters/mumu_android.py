"""MuMu Android Emulator Adapter (`mumu-android`) for Tencent Meeting.

Runs Tencent Meeting (`com.tencent.wemeet.app`) inside Netease MuMu Android Emulator via `MuMuManager.exe` and `adb`.
Key advantage: 100% isolated inside the emulator — NEVER steals the host Windows mouse, keyboard, or window focus,
and allows running a separate Agent Tencent Meeting session while the user uses their PC (or their own host Tencent Meeting) normally.
"""

from __future__ import annotations

import asyncio
import io
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator
from pathlib import Path

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
from .tencent_desktop import sanitize_meeting_code

WEMEET_ANDROID_PKG = "com.tencent.wemeet.app"
BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def find_mumu_paths() -> tuple[str | None, str | None]:
    """Locate MuMuManager.exe and adb.exe on the host machine."""
    manager_candidates = [
        Path(r"D:\Program Files\Netease\MuMu\nx_main\MuMuManager.exe"),
        Path(r"C:\Program Files\Netease\MuMu\nx_main\MuMuManager.exe"),
        Path(r"D:\Program Files\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe"),
        Path(r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe"),
    ]
    manager_path: str | None = None
    for c in manager_candidates:
        if c.exists():
            manager_path = str(c)
            break

    adb_candidates = [
        Path(r"D:\Program Files\Netease\MuMu\nx_main\adb.exe"),
        Path(r"D:\Program Files\Netease\MuMu\nx_device\15.0\shell\adb.exe"),
        Path(r"C:\Program Files\Netease\MuMu\nx_main\adb.exe"),
    ]
    adb_path: str | None = shutil.which("adb")
    for c in adb_candidates:
        if c.exists():
            adb_path = str(c)
            break

    return manager_path, adb_path


def parse_bounds_center(bounds_str: str) -> tuple[int, int] | None:
    m = BOUNDS_RE.search(bounds_str or "")
    if not m:
        return None
    x1, y1, x2, y2 = (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
    return ((x1 + x2) // 2, (y1 + y2) // 2)


class MuMuAndroidAdapter(MeetingAdapter):
    """Drives Tencent Meeting inside MuMu Android Emulator via ADB without touching host PC mouse/keyboard."""

    adapter_name = "mumu-android"

    def __init__(
        self,
        settings: Settings,
        asr: AsrProvider,
        tts: TtsProvider,
        tile_renderer: LiveStatusTileRenderer | None = None,
        vm_index: int = 0,
        adb_serial: str = "127.0.0.1:16384",
    ) -> None:
        self.settings = settings
        self.asr = asr
        self.tts = tts
        self.tile_renderer = tile_renderer or LiveStatusTileRenderer()
        self.vm_index = vm_index
        self.adb_serial = adb_serial
        self.manager_path, self.adb_path = find_mumu_paths()
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
        self._chat_queue: asyncio.Queue[ChatMessage] = asyncio.Queue(maxsize=64)
        self._prev_thumb: np.ndarray | None = None
        self._active_speaker: str | None = None
        self._config: JoinConfig | None = None

    def _adb(self, *args: str, timeout: float = 10.0) -> subprocess.CompletedProcess[bytes]:
        if not self.adb_path:
            raise RuntimeError("未找到 MuMu adb.exe")
        cmd = [self.adb_path, "-s", self.adb_serial, *args]
        return subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)

    async def ensure_emulator_ready(self) -> None:
        if not self.adb_path:
            raise RuntimeError("未检测到 MuMu 模拟器或 adb.exe。")

        # Connect ADB
        await asyncio.to_thread(
            subprocess.run,
            [self.adb_path, "connect", self.adb_serial],
            capture_output=True,
            timeout=6,
            check=False,
        )
        res = await asyncio.to_thread(self._adb, "shell", "getprop", "sys.boot_completed")
        if res.stdout.decode("utf-8", errors="ignore").strip() != "1":
            if not self.manager_path:
                raise RuntimeError("MuMu 模拟器尚未启动，请先打开 MuMu 模拟器。")
            # Launch MuMu detached so it stays alive independently
            subprocess.Popen(
                [self.manager_path, "control", "-v", str(self.vm_index), "-ver", "15", "launch"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            for _ in range(25):
                await asyncio.sleep(2.0)
                await asyncio.to_thread(
                    subprocess.run,
                    [self.adb_path, "connect", self.adb_serial],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                chk = await asyncio.to_thread(self._adb, "shell", "getprop", "sys.boot_completed")
                if chk.stdout.decode("utf-8", errors="ignore").strip() == "1":
                    break

    async def is_wemeet_installed(self) -> bool:
        res = await asyncio.to_thread(self._adb, "shell", "pm", "list", "packages", WEMEET_ANDROID_PKG)
        return WEMEET_ANDROID_PKG in res.stdout.decode("utf-8", errors="ignore")

    async def join(self, config: JoinConfig) -> None:
        self._config = config
        self._running = True
        self._tile_state.agent_name = config.display_name
        self._tile_state.workspace_url = config.workspace_url

        await self.ensure_emulator_ready()
        if not await self.is_wemeet_installed():
            raise RuntimeError(
                "MuMu 模拟器内尚未安装腾讯会议 Android 版 (com.tencent.wemeet.app)。"
                "请先在模拟器中安装并登录腾讯会议，然后重试。"
            )

        clean_code = sanitize_meeting_code(config.meeting_code)
        if clean_code:
            deep_link = f"wemeet://page/inmeeting?meeting_code={clean_code}"
            await asyncio.to_thread(
                self._adb,
                "shell",
                "am",
                "start",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                deep_link,
            )
            await asyncio.sleep(2.2)
            await asyncio.to_thread(self._tap_join_buttons_if_present)

        loop = asyncio.get_running_loop()
        self.capturer.start(loop)

    def _dump_ui_xml(self) -> ET.Element | None:
        try:
            self._adb("shell", "uiautomator", "dump", "/sdcard/meet_agent_uidump.xml", timeout=6.0)
            res = self._adb("exec-out", "cat", "/sdcard/meet_agent_uidump.xml", timeout=6.0)
            xml_text = res.stdout.decode("utf-8", errors="ignore").strip()
            if not xml_text or "<hierarchy" not in xml_text:
                return None
            start = xml_text.find("<hierarchy")
            return ET.fromstring(xml_text[start:])
        except Exception:
            return None

    def _tap_join_buttons_if_present(self) -> bool:
        root = self._dump_ui_xml()
        if root is None:
            return False
        for node in root.iter("node"):
            text = (node.attrib.get("text") or "").strip()
            desc = (node.attrib.get("content-desc") or "").strip()
            label = f"{text} {desc}"
            if any(k in label for k in ("加入会议", "Join Meeting", "立即加入")):
                center = parse_bounds_center(node.attrib.get("bounds", ""))
                if center:
                    self._adb("shell", "input", "tap", str(center[0]), str(center[1]))
                    return True
        return False

    async def leave(self) -> None:
        self._running = False
        self.capturer.stop()
        try:
            await asyncio.to_thread(self._adb, "shell", "am", "force-stop", WEMEET_ANDROID_PKG)
        except Exception:
            pass

    async def transcript_stream(self) -> AsyncIterator[TranscriptSegment]:
        async for audio_seg in self.capturer.segments():
            if not self._running:
                break
            text = await self.asr.transcribe(audio_seg.pcm16, audio_seg.sample_rate)
            if not text:
                continue
            speaker = await self.get_active_speaker() or "腾讯会议参会者"
            yield TranscriptSegment(speaker=speaker, text=text, source="audio")

    async def chat_stream(self) -> AsyncIterator[ChatMessage]:
        while self._running:
            try:
                msg = await asyncio.wait_for(self._chat_queue.get(), timeout=0.5)
                yield msg
            except asyncio.TimeoutError:
                continue

    def _is_mic_muted(self) -> bool:
        """Check if microphone in Tencent Meeting is currently muted."""
        root = self._dump_ui_xml()
        if root is None:
            return True
        for node in root.iter("node"):
            text = (node.attrib.get("text") or "").strip()
            desc = (node.attrib.get("content-desc") or "").strip()
            # If button text or desc says '解除静音', mic is currently MUTED
            if "解除静音" in text or "解除静音" in desc:
                return True
            # If button text or desc says '静音', mic is currently UNMUTED (active)
            if text == "静音" or desc == "静音":
                return False
        return True

    def _toggle_mic(self) -> bool:
        """Click the bottom microphone button to toggle mute/unmute."""
        root = self._dump_ui_xml()
        if root is not None:
            for node in root.iter("node"):
                rid = node.attrib.get("resource-id", "")
                text = node.attrib.get("text", "")
                desc = node.attrib.get("content-desc", "")
                if "llInMeetingBottomMicNormal" in rid or "解除静音" in text or "解除静音" in desc or text == "静音" or desc == "静音":
                    center = parse_bounds_center(node.attrib.get("bounds", ""))
                    if center:
                        self._adb("shell", "input", "tap", str(center[0]), str(center[1]))
                        return True
        # Fallback to standard 1080x1920 layout bottom-left mic position
        self._adb("shell", "input", "tap", "108", "1837")
        return True

    async def send_chat(self, text: str) -> bool:
        """Best-effort send text message via Tencent Meeting Android UI."""
        if not text.strip():
            return False
        return await asyncio.to_thread(self._send_chat_sync, text)

    def _send_chat_sync(self, text: str) -> bool:
        try:
            # Tap '发送弹幕' icon (resource-id ivSuperInteractiveChat, bounds [93,1698][163,1768])
            self._adb("shell", "input", "tap", "128", "1733")
            time.sleep(0.5)
            # Encode text for ADB
            clean = text.replace("\n", " ").strip()
            self._adb("shell", "am", "broadcast", "-a", "ADB_INPUT_TEXT", "--es", "msg", clean)
            time.sleep(0.2)
            self._adb("shell", "input", "keyevent", "66")  # Enter
            return True
        except Exception:
            return False

    async def speak_text(self, text: str) -> bool:
        if not self._config or not self._config.enable_tts or not text.strip():
            return False
        mp3_bytes = await self.tts.synthesize_mp3(text)
        if not mp3_bytes:
            return False

        # 1. Unmute mic before speaking if currently muted
        was_muted = await asyncio.to_thread(self._is_mic_muted)
        if was_muted:
            await asyncio.to_thread(self._toggle_mic)
            await asyncio.sleep(0.3)

        # 2. Play audio through VirtualMicPlayer (targets CABLE Input or default output)
        try:
            played = await self.player.play_mp3_bytes(mp3_bytes)
        finally:
            # 3. EchoMuteGate: Re-mute mic after speech finishes
            if was_muted:
                await asyncio.sleep(0.3)
                await asyncio.to_thread(self._toggle_mic)
        return played

    async def capture_screen(self) -> tuple[bytes | None, float]:
        """Capture Android screen directly from MuMu framebuffer via `adb exec-out screencap -p`."""
        return await asyncio.to_thread(self._capture_screen_adb)

    def _capture_screen_adb(self) -> tuple[bytes | None, float]:
        try:
            res = self._adb("exec-out", "screencap", "-p", timeout=6.0)
            if res.returncode != 0 or not res.stdout:
                return None, 0.0
            img = Image.open(io.BytesIO(res.stdout)).convert("RGB")
            thumb = np.asarray(img.resize((160, 90)), dtype=np.float32) / 255.0
            diff = 1.0
            if self._prev_thumb is not None:
                diff = float(np.mean(np.abs(thumb - self._prev_thumb)))
            self._prev_thumb = thumb

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=78)
            return buf.getvalue(), diff
        except Exception:
            return None, 0.0

    async def get_active_speaker(self) -> str | None:
        detected = await asyncio.to_thread(self._detect_speaker_from_ui)
        if detected:
            self._active_speaker = detected
        return self._active_speaker

    def _detect_speaker_from_ui(self) -> str | None:
        root = self._dump_ui_xml()
        if root is None:
            return None
        for node in root.iter("node"):
            text = (node.attrib.get("text") or "").strip()
            if "正在讲话" in text or "Speaking" in text:
                return text.replace("正在讲话：", "").replace("正在讲话:", "").strip() or None
        return None

    def update_tile_state(self, state: TileState) -> None:
        self._tile_state = state

    def get_tile_jpeg(self) -> bytes:
        return self.tile_renderer.render_jpeg_bytes(self._tile_state)
