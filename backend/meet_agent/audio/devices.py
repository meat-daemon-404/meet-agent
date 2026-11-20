"""Hardware, virtual audio/video device, and Tencent Meeting client probing."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

from ..brains.base import discover_local_agents
from ..models import EnvironmentReport

VIRTUAL_AUDIO_KEYWORDS = ("cable", "virtual", "vb-audio", "blackhole", "voicemeeter", "pulse", "monitor")
VIRTUAL_CAM_KEYWORDS = ("obs", "unity", "virtual", "v4l2", "manycam", "snap")


def find_tencent_meeting_windows() -> tuple[bool, str | None, bool]:
    """Detect WeMeetApp.exe on Windows via running processes, registry wemeet:// scheme, and common paths."""
    running = False
    found_path: str | None = None

    # 1. Check running processes via PowerShell / WMI (non-blocking fast check)
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-Process -Name 'WeMeetApp' -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Path)",
            ],
            text=True,
            timeout=3,
            stderr=subprocess.DEVNULL,
        ).strip()
        if out and Path(out).exists():
            running = True
            found_path = out
    except Exception:
        pass

    # 2. Check Windows Registry for registered `wemeet://` URL scheme
    if not found_path and sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"wemeet\shell\open\command") as key:
                cmd_val, _ = winreg.QueryValueEx(key, "")
                # Parse quoted executable path
                if '"' in cmd_val:
                    candidate = cmd_val.split('"')[1]
                else:
                    candidate = cmd_val.split()[0]
                if Path(candidate).exists():
                    found_path = candidate
        except Exception:
            pass

    # 3. Check standard installation paths across drives
    if not found_path:
        candidates = [
            Path(r"C:\Program Files (x86)\Tencent\WeMeet\WeMeetApp.exe"),
            Path(r"C:\Program Files\Tencent\WeMeet\WeMeetApp.exe"),
            Path(r"D:\腾讯会议\WeMeet\WeMeetApp.exe"),
            Path(r"D:\Program Files\Tencent\WeMeet\WeMeetApp.exe"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Tencent" / "WeMeet" / "WeMeetApp.exe",
        ]
        for c in candidates:
            if c.exists():
                found_path = str(c)
                break

    return bool(found_path), found_path, running


def probe_audio_devices() -> tuple[list[str], list[str], list[str], bool]:
    """Probe audio inputs, WASAPI loopbacks, and outputs using PyAudioWPatch when available."""
    inputs: list[str] = []
    loopbacks: list[str] = []
    outputs: list[str] = []
    has_virtual = False

    try:
        import pyaudiowpatch as pyaudio  # type: ignore[import-untyped]

        pa = pyaudio.PyAudio()
        try:
            for idx in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(idx)
                name = str(info.get("name", "")).strip()
                if not name:
                    continue
                lower = name.lower()
                if any(kw in lower for kw in VIRTUAL_AUDIO_KEYWORDS):
                    has_virtual = True
                if info.get("isLoopbackDevice"):
                    if name not in loopbacks:
                        loopbacks.append(name)
                elif int(info.get("maxInputChannels", 0)) > 0:
                    if name not in inputs:
                        inputs.append(name)
                if int(info.get("maxOutputChannels", 0)) > 0:
                    if name not in outputs:
                        outputs.append(name)
        finally:
            pa.terminate()
    except Exception:
        pass

    return inputs, loopbacks, outputs, has_virtual


def probe_virtual_camera() -> tuple[bool, str | None]:
    """Check whether OBS Virtual Camera, Unity Capture, or Linux v4l2loopback is installed."""
    if sys.platform.startswith("linux"):
        for dev in sorted(Path("/dev").glob("video*")):
            return True, f"v4l2loopback ({dev})"
        return False, None

    if sys.platform == "win32":
        # Check Windows PnP cameras + OBS Virtual Camera DLL registration
        try:
            out = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-PnpDevice -Class Camera,Image -Status OK -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FriendlyName)",
                ],
                text=True,
                timeout=3,
                stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                lower = line.strip().lower()
                if any(kw in lower for kw in VIRTUAL_CAM_KEYWORDS):
                    return True, line.strip()
        except Exception:
            pass

        # OBS Virtual Camera registers CLSID in DirectShow even when not listed under Camera class
        obs_paths = [
            Path(r"C:\Program Files\obs-studio\bin\64bit\obs-virtualcam-module64.dll"),
            Path(r"C:\Program Files (x86)\obs-studio\bin\64bit\obs-virtualcam-module64.dll"),
        ]
        for p in obs_paths:
            if p.exists():
                return True, "obs"

    return False, None


def inspect_environment() -> EnvironmentReport:
    """Build a complete diagnostic report of local Tencent Meeting, A/V devices, and Agent CLIs."""
    sys_name = f"{platform.system()} {platform.release()}"
    warnings: list[str] = []

    if sys.platform == "win32":
        tm_installed, tm_path, tm_running = find_tencent_meeting_windows()
    else:
        tm_installed, tm_path, tm_running = False, None, False
        for linux_bin in ("/opt/wemeet/wemeetapp.sh", "/usr/bin/wemeet"):
            if Path(linux_bin).exists():
                tm_installed = True
                tm_path = linux_bin
                break

    from ..adapters.mumu_android import find_mumu_paths

    mumu_mgr, mumu_adb = find_mumu_paths()
    inputs, loopbacks, outputs, has_vac = probe_audio_devices()
    has_vcam, vcam_backend = probe_virtual_camera()
    agents = discover_local_agents()

    if not tm_installed and not mumu_mgr:
        warnings.append("未检测到腾讯会议客户端或 MuMu 模拟器，仍可使用 SimulatorAdapter 体验完整流程。")
    if not has_vac:
        if loopbacks:
            warnings.append(
                "未检测到 VB-Cable 虚拟声卡：已自动启用 WASAPI Loopback 零配置听会；如需 Agent 语音开口发言，建议安装免费 VB-Cable。"
            )
        else:
            warnings.append("未检测到虚拟声卡或 Loopback 设备，建议安装 VB-Cable（Windows）或启用 PulseAudio（Linux）。")
    if not has_vcam:
        warnings.append(
            "未检测到 OBS Virtual Camera / Unity Capture：Live Status Tile 将在协同工作台实时预览；安装 OBS 后可推送为腾讯会议摄像头画面。"
        )

    return EnvironmentReport(
        platform=sys_name,
        tencent_meeting_installed=tm_installed,
        tencent_meeting_path=tm_path,
        tencent_meeting_running=tm_running,
        mumu_installed=bool(mumu_mgr),
        mumu_manager_path=mumu_mgr,
        mumu_adb_path=mumu_adb,
        audio_input_devices=inputs,
        audio_loopback_devices=loopbacks,
        audio_output_devices=outputs,
        has_virtual_audio_cable=has_vac,
        has_virtual_camera=has_vcam,
        virtual_camera_backend=vcam_backend,
        discovered_agents=agents,
        warnings=warnings,
    )
