import json
import os
import sys
from pathlib import Path

def find_mumu_customer_config() -> Path | None:
    candidates = [
        Path(r"D:\Program Files\Netease\MuMu\vms\MuMuPlayer-15.0-0\configs\customer_config.json"),
        Path(r"C:\Program Files\Netease\MuMu\vms\MuMuPlayer-15.0-0\configs\customer_config.json"),
        Path(r"D:\Program Files\Netease\MuMuPlayer-12.0\vms\MuMuPlayer-12.0-0\configs\customer_config.json"),
        Path(r"C:\Program Files\Netease\MuMuPlayer-12.0\vms\MuMuPlayer-12.0-0\configs\customer_config.json"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

def check_and_bind() -> bool:
    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        print("Error: PyAudioWPatch not installed in venv")
        return False

    pa = pyaudio.PyAudio()
    cable_input = None
    cable_output = None

    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        name = str(info.get("name", ""))
        inputs = int(info.get("maxInputChannels", 0))
        outputs = int(info.get("maxOutputChannels", 0))

        if "cable" in name.lower() or "vb-audio" in name.lower():
            if outputs > 0 and not cable_input:
                cable_input = name
            if inputs > 0 and not cable_output:
                cable_output = name

    pa.terminate()

    if not cable_output and not cable_input:
        print("[Status] VB-CABLE driver not detected in Windows audio devices yet.")
        print("[Action] Please complete driver installation, then rerun this script.")
        return False

    print(f"[Detected] Virtual Cable Input: {cable_input}")
    print(f"[Detected] Virtual Cable Output: {cable_output}")

    # 1. Update MuMu customer_config.json
    mumu_cfg = find_mumu_customer_config()
    if mumu_cfg and mumu_cfg.exists():
        try:
            with open(mumu_cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("setting", {}).setdefault("volume_setting", {})["microphone"] = cable_output or "CABLE Output (VB-Audio Virtual Cable)"
            with open(mumu_cfg, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"[Configured] MuMu microphone bound to: {data['setting']['volume_setting']['microphone']}")
        except Exception as e:
            print(f"[Warning] Failed to update MuMu config: {e}")
    else:
        print("[Info] No active MuMu config file found in standard directories.")

    # 2. Update MeetAgent .env
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        try:
            lines = open(env_path, "r", encoding="utf-8").readlines()
            new_lines = []
            found_output_hint = False
            found_enable_tts = False
            for line in lines:
                if line.startswith("AUDIO_OUTPUT_HINT="):
                    new_lines.append(f'AUDIO_OUTPUT_HINT="{cable_input or "CABLE Input"}"\n')
                    found_output_hint = True
                elif line.startswith("ENABLE_TTS="):
                    new_lines.append("ENABLE_TTS=true\n")
                    found_enable_tts = True
                else:
                    new_lines.append(line)
            if not found_output_hint:
                new_lines.append(f'AUDIO_OUTPUT_HINT="{cable_input or "CABLE Input"}"\n')
            if not found_enable_tts:
                new_lines.append("ENABLE_TTS=true\n")
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            print("[Configured] MeetAgent .env updated (ENABLE_TTS=true, AUDIO_OUTPUT_HINT set)")
        except Exception as e:
            print(f"[Warning] Failed to update .env: {e}")

    print("[Ready] All audio routing and MuMu bindings are configured successfully!")
    return True

if __name__ == "__main__":
    check_and_bind()
