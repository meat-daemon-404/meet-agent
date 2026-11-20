"""Virtual microphone audio playback with EchoMuteGate coordination."""

from __future__ import annotations

import asyncio
import io
import wave

from .capture import EchoMuteGate


class VirtualMicPlayer:
    """Plays PCM/WAV audio into a virtual audio input (e.g. VB-Cable Input) or default output."""

    def __init__(self, device_hint: str = "CABLE Input", echo_gate: EchoMuteGate | None = None) -> None:
        self.device_hint = device_hint.lower().strip()
        self.echo_gate = echo_gate or EchoMuteGate()

    async def play_wav_bytes(self, wav_bytes: bytes) -> bool:
        if not wav_bytes:
            return False
        self.echo_gate.start_speaking()
        try:
            return await asyncio.to_thread(self._play_sync, wav_bytes)
        finally:
            self.echo_gate.stop_speaking()

    async def play_mp3_bytes(self, mp3_bytes: bytes) -> bool:
        if not mp3_bytes:
            return False
        wav_bytes = await asyncio.to_thread(self._mp3_to_wav, mp3_bytes)
        if wav_bytes:
            return await self.play_wav_bytes(wav_bytes)
        return False

    @staticmethod
    def _mp3_to_wav(mp3_bytes: bytes) -> bytes | None:
        try:
            import miniaudio

            decoded = miniaudio.decode(mp3_bytes)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(decoded.nchannels)
                wf.setsampwidth(decoded.sample_width)
                wf.setframerate(decoded.sample_rate)
                wf.writeframes(decoded.samples)
            return buf.getvalue()
        except Exception:
            pass
        try:
            import subprocess

            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    "pipe:0",
                    "-f",
                    "wav",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "pipe:1",
                ],
                input=mp3_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            return proc.stdout
        except Exception:
            return None

    def _play_sync(self, wav_bytes: bytes) -> bool:
        try:
            import pyaudiowpatch as pyaudio  # type: ignore[import-untyped]
        except Exception:
            return False

        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
        except Exception:
            return False

        pa = pyaudio.PyAudio()
        stream = None
        try:
            target_idx: int | None = None
            if self.device_hint:
                for idx in range(pa.get_device_count()):
                    info = pa.get_device_info_by_index(idx)
                    if (
                        int(info.get("maxOutputChannels", 0)) > 0
                        and self.device_hint in str(info.get("name", "")).lower()
                    ):
                        target_idx = idx
                        break

            stream = pa.open(
                format=pa.get_format_from_width(sampwidth),
                channels=channels,
                rate=framerate,
                output=True,
                output_device_index=target_idx,
            )
            chunk_size = 4096
            for offset in range(0, len(frames), chunk_size):
                stream.write(frames[offset : offset + chunk_size])
            return True
        except Exception:
            return False
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            pa.terminate()
