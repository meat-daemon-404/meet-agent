"""Pluggable speech-to-text (ASR) providers:
- `agy-multimodal`: Zero-API-key native multimodal audio understanding via Antigravity (`agy` + `read_file`)
- `faster-whisper`: Local offline Whisper model
- `openai-compatible`: SiliconFlow SenseVoiceSmall / Groq Whisper / OpenAI Whisper API
- `mock`: No-op mock for unit tests
"""

from __future__ import annotations

import asyncio
import io
import shutil
import time
import wave
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from ..config import Settings


def pcm16_to_wav(pcm16: bytes, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16)
    return buf.getvalue()


class AsrProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def transcribe(self, pcm16: bytes, sample_rate: int = 16000) -> str:
        """Convert mono 16-bit PCM audio bytes into text."""


class MockAsrProvider(AsrProvider):
    name = "mock"

    async def transcribe(self, pcm16: bytes, sample_rate: int = 16000) -> str:
        return ""


class DashScopeAsrProvider(AsrProvider):
    """Alibaba Cloud DashScope `qwen3-asr-flash` via the OpenAI-compatible chat endpoint (China site)."""

    name = "dashscope"
    endpoint = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "qwen3-asr-flash") -> None:
        self.api_key = api_key
        self.model = model

    async def transcribe(self, pcm16: bytes, sample_rate: int = 16000) -> str:
        if not pcm16 or not self.api_key:
            return ""
        import base64

        b64 = base64.b64encode(pcm16_to_wav(pcm16, sample_rate)).decode("ascii")
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_audio", "input_audio": {"data": f"data:audio/wav;base64,{b64}"}}
                    ],
                }
            ],
            "asr_options": {"language": "zh", "enable_itn": False},
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=body,
                )
                resp.raise_for_status()
                return str(resp.json()["choices"][0]["message"]["content"]).strip()
        except Exception:
            return ""


class AgyMultimodalAsrProvider(AsrProvider):
    """Uses Antigravity's native multimodal `read_file` tool on temporary WAV files (0 API key required!)."""

    name = "agy-multimodal"

    def __init__(self, data_dir: Path, model: str = "gemini-4-argon-medium") -> None:
        self.audio_dir = (data_dir / "live_audio").resolve()
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.model = model or "gemini-4-argon-medium"
        self.agy_bin = shutil.which("agy") or "agy"

    async def transcribe(self, pcm16: bytes, sample_rate: int = 16000) -> str:
        if not pcm16:
            return ""
        wav_bytes = pcm16_to_wav(pcm16, sample_rate)
        ts_ms = int(time.time() * 1000)
        wav_path = self.audio_dir / f"utt_{ts_ms}.wav"
        latest_path = self.audio_dir / "latest.wav"
        wav_path.write_bytes(wav_bytes)
        latest_path.write_bytes(wav_bytes)

        prompt = (
            f"请调用 read_file 工具读取音频文件 {wav_path} 并直接输出它的中文或英文逐字转写文本。"
            "如果是纯静音或噪音请输出空字符串，不要输出任何额外解释或标点修饰。"
        )
        cmd = [
            self.agy_bin,
            "--model",
            self.model,
            "-p",
            prompt,
            "--add-dir",
            str(self.audio_dir),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.audio_dir),
            )
            stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=45.0)
            if proc.returncode == 0:
                text = stdout_b.decode("utf-8", errors="replace").strip()
                return text
        except Exception:
            pass
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass
        return ""


class OpenAICompatibleAsrProvider(AsrProvider):
    name = "openai-compatible"

    def __init__(self, api_base: str, api_key: str, model: str = "whisper-1") -> None:
        self.api_base = api_base.rstrip("/") or "https://api.openai.com/v1"
        self.api_key = api_key
        self.model = model

    async def transcribe(self, pcm16: bytes, sample_rate: int = 16000) -> str:
        if not self.api_key:
            return ""
        wav_bytes = pcm16_to_wav(pcm16, sample_rate)
        url = f"{self.api_base}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {"file": ("utterance.wav", wav_bytes, "audio/wav")}
        data = {"model": self.model, "language": "zh"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
            resp.raise_for_status()
            payload = resp.json()
            return str(payload.get("text", "")).strip()


class LocalFasterWhisperProvider(AsrProvider):
    name = "faster-whisper"

    def __init__(self, model_size: str = "small") -> None:
        self.model_size = model_size
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]

            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    async def transcribe(self, pcm16: bytes, sample_rate: int = 16000) -> str:
        return await asyncio.to_thread(self._transcribe_sync, pcm16, sample_rate)

    def _transcribe_sync(self, pcm16: bytes, sample_rate: int) -> str:
        try:
            model = self._ensure_model()
            wav_io = io.BytesIO(pcm16_to_wav(pcm16, sample_rate))
            segments, _ = model.transcribe(wav_io, language="zh", vad_filter=True)
            return "".join(s.text for s in segments).strip()
        except Exception:
            return ""


def create_asr_provider(settings: Settings) -> AsrProvider:
    if settings.asr_provider == "dashscope" and settings.dashscope_api_key:
        return DashScopeAsrProvider(settings.dashscope_api_key, settings.dashscope_asr_model)
    if settings.asr_provider == "agy-multimodal":
        return AgyMultimodalAsrProvider(data_dir=settings.data_dir, model=settings.agy_model)
    if settings.asr_provider == "openai-compatible" and settings.asr_api_key:
        return OpenAICompatibleAsrProvider(
            api_base=settings.asr_api_base,
            api_key=settings.asr_api_key,
            model=settings.asr_model,
        )
    if settings.asr_provider == "faster-whisper":
        return LocalFasterWhisperProvider()
    return MockAsrProvider()
