"""Application configuration loaded from environment variables and .env files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEET_AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8765
    data_dir: Path = Field(default_factory=lambda: Path("data"))
    workspace_dir: Path = Field(default_factory=lambda: Path.cwd())

    # Agent identity & behavior
    default_brain: Literal["auto", "agy-stream", "agy-acp", "opencode-acp", "claude-cli", "demo"] = "auto"
    agent_name: str = "MeetAgent · AI参会助手"
    wake_words: str = "小会,MeetAgent,Antigravity,助手,Agent"
    agy_model: str = "gemini-4-argon-medium"
    agy_effort: str = "medium"

    # Audio & video hints
    audio_input_hint: str = ""
    audio_output_hint: str = "CABLE Input"
    virtual_cam_backend: str = ""

    # ASR settings (defaults to Antigravity's own native multimodal read_file audio understanding!)
    asr_provider: Literal["dashscope", "agy-multimodal", "mock", "faster-whisper", "openai-compatible"] = "agy-multimodal"
    dashscope_api_key: str = ""
    dashscope_asr_model: str = "qwen3-asr-flash"
    asr_api_base: str = ""
    asr_api_key: str = ""
    asr_model: str = "whisper-1"

    # TTS settings
    tts_provider: Literal["edge-tts", "mock"] = "edge-tts"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"

    # Privacy defaults
    save_raw_audio: bool = False
    decision_min_confidence: float = 0.75
    auto_send_join_notice: bool = True

    @property
    def wake_word_list(self) -> list[str]:
        return [w.strip() for w in self.wake_words.split(",") if w.strip()]

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    settings = Settings()
    # Respect explicit workspace path fallback if not overridden
    if not os.getenv("MEET_AGENT_WORKSPACE_DIR"):
        settings.workspace_dir = Path.cwd()
    settings.ensure_dirs()
    return settings
