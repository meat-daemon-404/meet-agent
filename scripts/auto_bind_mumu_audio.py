"""One-click auto-detect and bind MuMu / Virtual Audio output device into .env."""

from __future__ import annotations

from pathlib import Path

from meet_agent.audio.devices import list_output_devices

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

PREFERRED_KEYWORDS = [
    "cable input",
    "vb-audio",
    "voicemeeter",
    "virtual",
    "mumu",
    "扬声器",
    "speaker",
    "headphones",
]


def pick_best_output_device() -> str | None:
    devices = list_output_devices()
    if not devices:
        return None
    for kw in PREFERRED_KEYWORDS:
        for dev in devices:
            if kw in dev.name.lower():
                return dev.name
    return devices[0].name


def update_env(device_name: str) -> None:
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    hint_key = "MEET_AGENT_AUDIO_OUTPUT_HINT="
    tts_key = "MEET_AGENT_ENABLE_TTS="
    legacy_hint_key = "AUDIO_OUTPUT_HINT="
    legacy_tts_key = "ENABLE_TTS="
    found_hint = False
    found_tts = False
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith(hint_key) or stripped.startswith(legacy_hint_key):
            if not found_hint:
                new_lines.append(f"{hint_key}{device_name}")
                found_hint = True
        elif stripped.startswith(tts_key) or stripped.startswith(legacy_tts_key):
            if not found_tts:
                new_lines.append(f"{tts_key}true")
                found_tts = True
        else:
            new_lines.append(line)

    if not found_hint:
        new_lines.append(f"{hint_key}{device_name}")
    if not found_tts:
        new_lines.append(f"{tts_key}true")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def main() -> None:
    best = pick_best_output_device()
    if not best:
        print("[!] 未检测到可用音频输出设备，请确认声卡或虚拟声卡驱动已安装。")
        return
    update_env(best)
    print(f"[✓] 已自动绑定输出声卡到 .env: MEET_AGENT_AUDIO_OUTPUT_HINT={best}")


if __name__ == "__main__":
    main()
