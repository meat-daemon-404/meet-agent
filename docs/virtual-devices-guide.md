# Virtual Audio & Virtual Camera Setup Guide

MeetAgent works **out of the box on Windows** for listening via **WASAPI Loopback** (no virtual driver needed) and displays the Live Status Tile in the browser workspace. Installing virtual A/V devices unlocks full bidirectional isolation, TTS voice output into Tencent Meeting, and showing the Live Status Tile as your Tencent Meeting camera feed.

## Windows

### 1. Virtual Audio Cable (for Isolated Listening + Agent Voice Output)
1. Download and install the free **VB-Cable** driver from https://vb-audio.com/Cable/ (restart once after install).
2. In **Tencent Meeting → Settings → Audio**:
   - **Speaker**: select `CABLE Input (VB-Audio Virtual Cable)` (or keep your physical speaker if using WASAPI Loopback).
   - **Microphone**: select `CABLE Output (VB-Audio Virtual Cable)` if you want the Agent's TTS voice to speak into the meeting.
3. Verify with `meet-agent doctor` — `has_virtual_audio_cable` should become `true`.

### 2. Virtual Camera (for Live Status Tile in Tencent Meeting)
1. Install **OBS Studio** (includes OBS Virtual Camera) or **Unity Capture**.
2. Start MeetAgent and join a meeting with `enable_virtual_cam: true`.
3. In **Tencent Meeting → Settings → Video**, select **`OBS Virtual Camera`** (or `Unity Video Capture`).
4. Participants will see the live 1280×720 animated Agent status card showing listening waveform, current state, decision/action counters, and collaborative workspace URL.

### 3. Local Offline ASR (Zero API Key)
To transcribe Tencent Meeting audio completely locally without any cloud ASR API key:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[asr-local]"
```

Then set `MEET_AGENT_ASR_PROVIDER=faster-whisper` in `.env`.

## Linux (PulseAudio / PipeWire + v4l2loopback)

```bash
# Virtual audio sink & source
pactl load-module module-null-sink sink_name=meet_speaker sink_properties=device.description=MeetAgent_Speaker
pactl load-module module-null-sink sink_name=meet_mic sink_properties=device.description=MeetAgent_Mic

# Virtual camera kernel module
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="MeetAgent Virtual Cam" exclusive_caps=1
```
