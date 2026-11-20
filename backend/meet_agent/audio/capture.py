"""Meeting audio capture (WASAPI Loopback / Virtual Cable) with energy VAD and echo mute gate."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

import numpy as np


@dataclass
class AudioSegment:
    pcm16: bytes
    sample_rate: int = 16000
    duration_sec: float = 0.0
    rms_level: float = 0.0


class EchoMuteGate:
    """Prevents the Agent from transcribing its own TTS voice output."""

    def __init__(self, release_tail_sec: float = 0.6) -> None:
        self._release_tail_sec = release_tail_sec
        self._muted_until: float = 0.0
        self._speaking: bool = False

    def start_speaking(self) -> None:
        self._speaking = True

    def stop_speaking(self) -> None:
        self._speaking = False
        self._muted_until = time.monotonic() + self._release_tail_sec

    @property
    def is_muted(self) -> bool:
        return self._speaking or time.monotonic() < self._muted_until


class EnergyVadSegmenter:
    """Lightweight streaming energy VAD that slices 16kHz PCM audio into spoken utterances."""

    def __init__(
        self,
        sample_rate: int = 16000,
        rms_threshold: float = 0.015,
        silence_hangover_sec: float = 1.1,
        min_speech_sec: float = 0.6,
        max_utterance_sec: float = 15.0,
    ) -> None:
        self.sample_rate = sample_rate
        self.rms_threshold = rms_threshold
        self.silence_hangover_sec = silence_hangover_sec
        self.min_speech_sec = min_speech_sec
        self.max_utterance_sec = max_utterance_sec
        self._buf = bytearray()
        self._in_speech = False
        self._silence_elapsed = 0.0
        self._speech_elapsed = 0.0
        self.last_rms = 0.0

    def push_pcm16(self, pcm16: bytes, *, suppressed: bool = False) -> AudioSegment | None:
        if not pcm16:
            return None
        samples = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        chunk_sec = len(samples) / self.sample_rate
        rms = float(np.sqrt(np.mean(samples * samples))) if len(samples) else 0.0
        self.last_rms = 0.0 if suppressed else rms

        if suppressed:
            if self._in_speech and self._speech_elapsed >= self.min_speech_sec:
                return self._flush()
            self._reset()
            return None

        if rms >= self.rms_threshold:
            self._in_speech = True
            self._silence_elapsed = 0.0
            self._speech_elapsed += chunk_sec
            self._buf.extend(pcm16)
            if self._speech_elapsed >= self.max_utterance_sec:
                return self._flush()
            return None

        if self._in_speech:
            self._buf.extend(pcm16)
            self._silence_elapsed += chunk_sec
            if self._silence_elapsed >= self.silence_hangover_sec:
                if self._speech_elapsed >= self.min_speech_sec:
                    return self._flush()
                self._reset()
        return None

    def _flush(self) -> AudioSegment:
        data = bytes(self._buf)
        duration = len(data) / (2 * self.sample_rate)
        rms = self.last_rms
        self._reset()
        return AudioSegment(pcm16=data, sample_rate=self.sample_rate, duration_sec=duration, rms_level=rms)

    def _reset(self) -> None:
        self._buf.clear()
        self._in_speech = False
        self._silence_elapsed = 0.0
        self._speech_elapsed = 0.0


def _downsample_to_16k_mono(raw: bytes, src_rate: int, src_channels: int) -> bytes:
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if src_channels > 1:
        arr = arr.reshape(-1, src_channels).mean(axis=1)
    if src_rate != 16000 and len(arr) > 0:
        target_len = max(1, int(len(arr) * 16000 / src_rate))
        xp = np.linspace(0.0, 1.0, len(arr), endpoint=False)
        x_new = np.linspace(0.0, 1.0, target_len, endpoint=False)
        arr = np.interp(x_new, xp, arr)
    return np.clip(arr, -32768, 32767).astype(np.int16).tobytes()


class SystemAudioCapturer:
    """Captures meeting audio via PyAudioWPatch (prefers virtual cable hint, falls back to WASAPI Loopback)."""

    def __init__(
        self,
        device_hint: str = "",
        echo_gate: EchoMuteGate | None = None,
    ) -> None:
        self.device_hint = device_hint.lower().strip()
        self.echo_gate = echo_gate or EchoMuteGate()
        self.vad = EnergyVadSegmenter()
        self.active_device_name: str = "未连接"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._queue: asyncio.Queue[AudioSegment] = asyncio.Queue(maxsize=32)
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def current_level(self) -> float:
        return min(1.0, self.vad.last_rms * 8.0)

    def start(self, loop: asyncio.AbstractEventLoop) -> bool:
        self._loop = loop
        self._stop_event.clear()
        try:
            import pyaudiowpatch as pyaudio  # type: ignore[import-untyped]
        except Exception:
            self.active_device_name = "Unavailable (PyAudioWPatch not installed)"
            return False

        self._thread = threading.Thread(target=self._run_capture, args=(pyaudio,), daemon=True)
        self._thread.start()
        return True

    def _select_device(self, pa: object) -> dict | None:
        # 1. Match explicit hint (e.g. "CABLE Output")
        if self.device_hint:
            for idx in range(pa.get_device_count()):  # type: ignore[attr-defined]
                info = pa.get_device_info_by_index(idx)  # type: ignore[attr-defined]
                if int(info.get("maxInputChannels", 0)) > 0 and self.device_hint in str(info.get("name", "")).lower():
                    return info

        # 2. Prefer VB-Cable Output if installed
        for idx in range(pa.get_device_count()):  # type: ignore[attr-defined]
            info = pa.get_device_info_by_index(idx)  # type: ignore[attr-defined]
            name = str(info.get("name", "")).lower()
            if int(info.get("maxInputChannels", 0)) > 0 and "cable output" in name:
                return info

        # 3. Fallback to default WASAPI loopback speaker (zero-install listening!)
        try:
            wasapi = pa.get_host_api_info_by_type(pa.paWASAPI)  # type: ignore[attr-defined]
            default_speakers = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])  # type: ignore[attr-defined]
            if not default_speakers.get("isLoopbackDevice"):
                for loopback in pa.get_loopback_device_info_generator():  # type: ignore[attr-defined]
                    if default_speakers["name"] in loopback["name"]:
                        return loopback
            return default_speakers
        except Exception:
            return None

    def _run_capture(self, pyaudio_mod: object) -> None:
        pa = pyaudio_mod.PyAudio()  # type: ignore[attr-defined]
        stream = None
        try:
            dev = self._select_device(pa)
            if not dev:
                self.active_device_name = "未找到可用采集设备"
                return

            self.active_device_name = str(dev.get("name", "WASAPI Loopback"))
            src_rate = int(dev.get("defaultSampleRate", 48000))
            src_channels = max(1, min(2, int(dev.get("maxInputChannels", 2))))
            frames_per_buf = max(512, int(src_rate * 0.1))

            stream = pa.open(
                format=pyaudio_mod.paInt16,  # type: ignore[attr-defined]
                channels=src_channels,
                rate=src_rate,
                frames_per_buffer=frames_per_buf,
                input=True,
                input_device_index=int(dev["index"]),
            )
            while not self._stop_event.is_set():
                try:
                    raw = stream.read(frames_per_buf, exception_on_overflow=False)
                except Exception:
                    time.sleep(0.05)
                    continue
                pcm16k = _downsample_to_16k_mono(raw, src_rate, src_channels)
                seg = self.vad.push_pcm16(pcm16k, suppressed=self.echo_gate.is_muted)
                if seg and self._loop:
                    self._loop.call_soon_threadsafe(self._enqueue_nowait, seg)
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            pa.terminate()

    def _enqueue_nowait(self, seg: AudioSegment) -> None:
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self._queue.put_nowait(seg)

    async def segments(self) -> AsyncIterator[AudioSegment]:
        while not self._stop_event.is_set():
            try:
                seg = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                yield seg
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
