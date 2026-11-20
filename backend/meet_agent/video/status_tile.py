"""Renders a 1280x720 animated Live Status Tile for Virtual Camera (`pyvirtualcam`) and Web preview."""

from __future__ import annotations

import io
import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..models import AgentVisualState


@dataclass
class TileState:
    agent_name: str = "MeetAgent · AI参会助手"
    brain_label: str = "Antigravity"
    meeting_title: str = "会议未开始"
    visual_state: AgentVisualState = AgentVisualState.IDLE
    subtitle: str = "等待加入会议"
    active_speaker: str | None = None
    decisions_count: int = 0
    ideas_count: int = 0
    actions_count: int = 0
    artifacts_count: int = 0
    workspace_url: str = "http://127.0.0.1:5173"
    audio_level: float = 0.15


STATE_META: dict[AgentVisualState, tuple[str, tuple[int, int, int]]] = {
    AgentVisualState.IDLE: ("STANDBY", (148, 163, 184)),
    AgentVisualState.LISTENING: ("LISTENING", (34, 211, 238)),
    AgentVisualState.THINKING: ("THINKING", (167, 139, 250)),
    AgentVisualState.BUILDING_ARTIFACT: ("BUILDING ARTIFACT", (52, 211, 153)),
    AgentVisualState.SPEAKING: ("SPEAKING", (251, 191, 36)),
    AgentVisualState.WAITING_APPROVAL: ("NEEDS APPROVAL", (251, 113, 133)),
    AgentVisualState.PAUSED: ("PAUSED", (100, 116, 139)),
}


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        # Windows CJK + Latin fonts
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\seguisb.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        # Linux CJK / Noto / DejaVu fallbacks
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


class LiveStatusTileRenderer:
    """Renders sleek 1280x720 RGB frames for both pyvirtualcam and browser JPEG preview."""

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = width
        self.height = height
        self._font_title = _load_font(44, bold=True)
        self._font_sub = _load_font(26, bold=False)
        self._font_badge = _load_font(22, bold=True)
        self._font_metric_num = _load_font(42, bold=True)
        self._font_metric_lbl = _load_font(20, bold=False)
        self._font_small = _load_font(20, bold=False)
        self._vcam = None
        self.vcam_active = False
        self.vcam_device_name: str | None = None

    def start_virtual_camera(self, backend: str | None = None, fps: int = 15) -> bool:
        try:
            import pyvirtualcam  # type: ignore[import-untyped]

            kwargs = {"width": self.width, "height": self.height, "fps": fps}
            if backend:
                kwargs["backend"] = backend
            self._vcam = pyvirtualcam.Camera(**kwargs)
            self.vcam_active = True
            self.vcam_device_name = getattr(self._vcam, "device", "Virtual Camera")
            return True
        except Exception:
            self._vcam = None
            self.vcam_active = False
            self.vcam_device_name = None
            return False

    def stop_virtual_camera(self) -> None:
        if self._vcam is not None:
            try:
                self._vcam.close()
            except Exception:
                pass
        self._vcam = None
        self.vcam_active = False

    def render_image(self, state: TileState, now: float | None = None) -> Image.Image:
        t = now if now is not None else time.monotonic()
        label, accent = STATE_META.get(state.visual_state, ("LISTENING", (34, 211, 238)))

        img = Image.new("RGB", (self.width, self.height), (11, 15, 25))
        draw = ImageDraw.Draw(img)

        # Subtle architectural grid background
        grid_color = (22, 30, 48)
        for x in range(0, self.width, 64):
            draw.line([(x, 0), (x, self.height)], fill=grid_color, width=1)
        for y in range(0, self.height, 64):
            draw.line([(0, y), (self.width, y)], fill=grid_color, width=1)

        # Outer card frame
        draw.rounded_rectangle(
            (40, 36, self.width - 40, self.height - 36),
            radius=28,
            fill=(16, 22, 36),
            outline=(38, 50, 74),
            width=2,
        )

        # Top bar: live status pill + brain tag
        pill_x1, pill_y1 = 80, 76
        draw.rounded_rectangle(
            (pill_x1, pill_y1, pill_x1 + 310, pill_y1 + 50),
            radius=25,
            fill=(24, 34, 54),
            outline=accent,
            width=2,
        )
        pulse_r = 8 + int(2 * math.sin(t * 5.0))
        cx, cy = pill_x1 + 30, pill_y1 + 25
        draw.ellipse((cx - pulse_r, cy - pulse_r, cx + pulse_r, cy + pulse_r), fill=accent)
        draw.text((pill_x1 + 54, pill_y1 + 11), label, font=self._font_badge, fill=accent)

        # Brain badge on top right
        brain_text = f"BRAIN: {state.brain_label}"
        draw.rounded_rectangle(
            (self.width - 420, 76, self.width - 80, 126),
            radius=25,
            fill=(24, 32, 52),
            outline=(71, 85, 105),
            width=1,
        )
        draw.text((self.width - 394, 88), brain_text[:28], font=self._font_small, fill=(203, 213, 225))

        # Main title & live subtitle
        draw.text((80, 162), state.agent_name[:30], font=self._font_title, fill=(248, 250, 252))
        draw.text((80, 226), state.subtitle[:48], font=self._font_sub, fill=(148, 163, 184))

        # Dynamic audio / thinking visualizer bars
        bar_count = 32
        bar_area_x = 80
        bar_area_y = 304
        bar_area_w = self.width - 160
        bar_gap = 10
        bar_w = max(8, (bar_area_w - bar_gap * (bar_count - 1)) // bar_count)
        amp_scale = 0.25 if state.visual_state == AgentVisualState.PAUSED else max(0.35, min(1.0, state.audio_level + 0.35))

        for i in range(bar_count):
            phase = t * 4.5 + i * 0.42
            wave_val = 0.5 + 0.5 * math.sin(phase) * math.cos(phase * 0.47 + i * 0.1)
            h = max(14, int(108 * amp_scale * (0.25 + 0.75 * wave_val)))
            x0 = bar_area_x + i * (bar_w + bar_gap)
            y0 = bar_area_y + (116 - h) // 2
            draw.rounded_rectangle((x0, y0, x0 + bar_w, y0 + h), radius=6, fill=accent)

        # Four KPI metric cards
        metrics = [
            ("拍板决策", str(state.decisions_count), (52, 211, 153)),
            ("讨论想法", str(state.ideas_count), (56, 189, 248)),
            ("行动项", str(state.actions_count), (251, 191, 36)),
            ("实时产物", str(state.artifacts_count), (167, 139, 250)),
        ]
        card_w = 255
        card_h = 112
        card_gap = 33
        start_x = 80
        card_y = 468
        for idx, (m_label, m_val, m_color) in enumerate(metrics):
            x0 = start_x + idx * (card_w + card_gap)
            draw.rounded_rectangle(
                (x0, card_y, x0 + card_w, card_y + card_h),
                radius=18,
                fill=(22, 30, 48),
                outline=(45, 58, 84),
                width=1,
            )
            draw.text((x0 + 24, card_y + 16), m_val, font=self._font_metric_num, fill=m_color)
            draw.text((x0 + 24, card_y + 72), m_label, font=self._font_metric_lbl, fill=(148, 163, 184))

        # Footer: active speaker + live workspace URL + transparency notice
        speaker_str = f"当前发言：{state.active_speaker}" if state.active_speaker else "可见 AI 参会者 · 支持随时口头喊停"
        draw.text((80, self.height - 96), speaker_str[:38], font=self._font_small, fill=(203, 213, 225))
        draw.text(
            (self.width - 520, self.height - 96),
            f"Live Workspace: {state.workspace_url}",
            font=self._font_small,
            fill=(100, 116, 139),
        )
        return img

    def render_rgb_array(self, state: TileState) -> np.ndarray:
        img = self.render_image(state)
        return np.asarray(img, dtype=np.uint8)

    def render_jpeg_bytes(self, state: TileState, quality: int = 82) -> bytes:
        img = self.render_image(state)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()

    def push_to_virtual_camera(self, state: TileState) -> bool:
        if not self._vcam or not self.vcam_active:
            return False
        try:
            frame = self.render_rgb_array(state)
            self._vcam.send(frame)
            return True
        except Exception:
            return False
