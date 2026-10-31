# Whisper Shortcut

A Windows-first voice dictation utility. Press a global hotkey to start
recording, press it again to stop, and the transcript is pasted into the
application that was active when recording started.

In local mode (the default) audio stays on the machine: the app uses
`faster-whisper`, keeps its model loaded between recordings, and falls back to
CPU if CUDA cannot be used. In OpenAI API mode the recording is uploaded to
OpenAI for transcription instead.

## Default hotkeys

- `Ctrl+Alt+Space`: start or stop recording
- `Ctrl+Alt+V`: paste the most recent transcript again
- `Ctrl+Alt+C`: open or close the recent-transcripts window
- `Ctrl+Alt+M`: switch between local and OpenAI API transcription
- `Ctrl+Alt+Q`: quit Whisper Shortcut

While recording, the indicator shows a live level meter and elapsed time; if
the bars stay flat, the microphone is not picking you up.

The recent-transcripts window lists the last 50 transcripts (stored in
`%LOCALAPPDATA%\WhisperShortcut\history.json`). Click one, or select it and
press Enter, to copy it; it also becomes the transcript that `Ctrl+Alt+V`
pastes.

## OpenAI API mode

Put your key in `%LOCALAPPDATA%\WhisperShortcut\.env` (created on first
launch):

```text
OPENAI_API_KEY=sk-...
```

An `OPENAI_API_KEY` environment variable, or a `.env` file in the directory the
app is started from, also works. Then press `Ctrl+Alt+M`. The chosen mode is
remembered across restarts, and the key is read on each use, so no restart is
needed after adding it.

The transcript is copied to the clipboard before every automatic paste.
Windows does not provide a universal way to verify that arbitrary applications
accepted pasted text. If automatic insertion misses its target, focus the
desired field and press the paste-last hotkey (or ordinary `Ctrl+V`).

## Run from source

Python 3.11 or 3.12 is recommended.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m whisper_shortcut
```

On first launch, the configured Whisper model is downloaded in the background
to the normal Hugging Face cache. The default `small` model is a reasonable
quality/speed starting point. Subsequent use can be offline.

## Configuration

The app creates:

```text
%LOCALAPPDATA%\WhisperShortcut\config.toml
```

Restart the app after editing it. The complete default file is:

```toml
[hotkeys]
toggle_recording = "<ctrl>+<alt>+<space>"
paste_last = "<ctrl>+<alt>+v"
history = "<ctrl>+<alt>+c"
toggle_mode = "<ctrl>+<alt>+m"
quit = "<ctrl>+<alt>+q"

[audio]
device = ""
sample_rate = 16000

[transcription]
model = "small"
language = ""
device = "auto"
compute_type = "auto"
beam_size = 5

[openai]
model = "gpt-transcribe"
base_url = "https://api.openai.com/v1"
timeout = 120

[indicator]
anchor = "top-center"
x_offset = 0
y_offset = 8
width = 210
height = 42
```

Valid indicator anchors are `top-left`, `top-center`, and `top-right`.
`x_offset` and `y_offset` make it easy to place the indicator beside or within
the area occupied by a Komorebi bar. The current version is an independent
always-on-top window; native bar integration can be added later.

Set `language` to a Whisper language code such as `"en"` or `"de"` to skip
language detection. `device = "auto"` tries CUDA and retries on CPU if CUDA
initialization or inference fails. For NVIDIA acceleration, the CUDA/cuDNN
runtime versions required by the installed `ctranslate2` release must also be
available.

To select a microphone, set `audio.device` to its numeric sounddevice index.
You can list devices with:

```powershell
python -c "import sounddevice; print(sounddevice.query_devices())"
```

## Test and check

```powershell
pytest
ruff check .
mypy
```

## Build the executable

The PyInstaller configuration creates a one-folder build. This is more reliable
and starts faster than extracting a large one-file executable on every launch.
The Whisper model is intentionally not bundled.

```powershell
pyinstaller --noconfirm --clean whisper_shortcut.spec
.\dist\WhisperShortcut\WhisperShortcut.exe
```

## Start automatically at sign-in

After building, install the Startup-folder shortcut:

```powershell
.\scripts\startup.ps1 -Action Install
```

To point it at a build elsewhere:

```powershell
.\scripts\startup.ps1 -Action Install -Executable "D:\Apps\WhisperShortcut.exe"
```

Remove autostart with:

```powershell
.\scripts\startup.ps1 -Action Remove
```

## Troubleshooting

Logs are written to:

```text
%LOCALAPPDATA%\WhisperShortcut\whisper-shortcut.log
```

If a hotkey does nothing, another application may already own that combination;
change it in `config.toml`. If text cannot be inserted into an elevated
application, run Whisper Shortcut at the same integrity level or paste manually
from the clipboard. Windows generally prevents a non-elevated process from
sending input to an elevated one.
