"""Tests for Live Status Tile rendering, Audio VAD, and EchoMuteGate."""

from __future__ import annotations

import numpy as np

from meet_agent.audio.capture import EchoMuteGate, EnergyVadSegmenter
from meet_agent.models import AgentVisualState
from meet_agent.video.status_tile import LiveStatusTileRenderer, TileState


def test_live_status_tile_renders_valid_rgb_and_jpeg():
    renderer = LiveStatusTileRenderer(width=1280, height=720)
    for vs in (
        AgentVisualState.LISTENING,
        AgentVisualState.THINKING,
        AgentVisualState.BUILDING_ARTIFACT,
        AgentVisualState.WAITING_APPROVAL,
        AgentVisualState.PAUSED,
    ):
        state = TileState(
            agent_name="MeetAgent · Antigravity",
            brain_label="agy-stream",
            visual_state=vs,
            subtitle="正在分析系统架构白板",
            decisions_count=3,
            ideas_count=5,
            actions_count=4,
            artifacts_count=2,
        )
        arr = renderer.render_rgb_array(state)
        assert arr.shape == (720, 1280, 3)
        assert arr.dtype == np.uint8

        jpg = renderer.render_jpeg_bytes(state)
        assert jpg[:2] == b"\xff\xd8"  # Valid JPEG header
        assert len(jpg) > 5000


def test_vad_segmenter_and_echo_mute_gate():
    vad = EnergyVadSegmenter(sample_rate=16000, rms_threshold=0.02, silence_hangover_sec=0.3, min_speech_sec=0.2)
    gate = EchoMuteGate(release_tail_sec=0.05)

    # Generate 0.3s of loud 440Hz tone (simulated speech)
    t = np.linspace(0, 0.3, int(16000 * 0.3), endpoint=False)
    loud_pcm = (np.sin(2 * np.pi * 440 * t) * 12000).astype(np.int16).tobytes()
    silent_pcm = np.zeros(int(16000 * 0.4), dtype=np.int16).tobytes()

    # Suppressed while agent is speaking
    gate.start_speaking()
    assert gate.is_muted is True
    assert vad.push_pcm16(loud_pcm, suppressed=gate.is_muted) is None
    gate.stop_speaking()

    # Normal speech followed by silence flushes a segment
    assert vad.push_pcm16(loud_pcm, suppressed=False) is None
    seg = vad.push_pcm16(silent_pcm, suppressed=False)
    assert seg is not None
    assert seg.duration_sec >= 0.3
