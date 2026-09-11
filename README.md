# Coconut Whisper

Local push to talk dictation for the Coconut team. Hold a key, speak, and the
text is inserted wherever the cursor is. Speech recognition runs on the user's
own machine with [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
so there are no API calls, no credits and no audio leaving the computer.

English, Portuguese and Tagalog. The interface is English only.

## How it works

| Piece | File | Notes |
| --- | --- | --- |
| Global hotkey | `app/hotkey.py` | Hold to talk or press to toggle, no admin rights |
| Microphone | `app/audio.py` | 16 kHz mono capture through sounddevice |
| Speech to text | `app/transcribe.py` | faster-whisper, CPU int8 or CUDA float16 |
| Cleanup | `app/postprocess.py` | Filler removal, word replacements, no model involved |
| Text delivery | `app/inject.py` | Clipboard paste, restores the previous clipboard |
| Tray and state | `app/main.py` | pystray icon, tkinter overlay, single instance guard |
| Settings window | `app/ui.py` | tkinter, Coconut colours |

Models download once into `%LOCALAPPDATA%\CoconutWhisper\models` and run offline
after that. Settings, logs and history live in `%APPDATA%\CoconutWhisper`.

The app picks a model based on the machine: turbo when there is a usable NVIDIA
GPU or 12 or more CPU cores, small from 6 cores, base below that. A GPU is only
used when the CUDA runtime libraries are actually present, otherwise it falls
back to the processor instead of crashing.

## Running from source

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m app.main
```

## Building the executable

```bash
.venv/Scripts/python.exe -m pip install pyinstaller
.venv/Scripts/python.exe build/gen_icons.py
.venv/Scripts/python.exe -m PyInstaller --noconfirm --clean \
  --distpath dist --workpath .pybuild build/CoconutWhisper.spec
```

The result is a single `dist/CoconutWhisper.exe`, about 100 MB, no installer and
no Python needed on the target machine.

## Tests

```bash
.venv/Scripts/python.exe test_core.py
powershell build/e2e_test.ps1 -Wav path/to/speech.wav
```

`test_core.py` covers the text cleanup and hotkey parsing. The PowerShell script
is a real end to end check: it holds the hotkey, plays speech through the
speakers, and reads back what was pasted into Notepad.

## Accuracy testing

Settings has a pilot mode that keeps the audio and the text of every dictation
in `%APPDATA%\CoconutWhisper\recordings`. Turn it on for a few volunteers,
collect the pairs, and the word error rate can be measured on real team speech
rather than on benchmarks.

## The download page

`site/` is a static page pointing at the latest GitHub release asset.
