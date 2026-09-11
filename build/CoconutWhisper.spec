from pathlib import Path

# PyInstaller spec for Coconut Whisper. Windows produces a single exe, macOS
# produces a .app bundle that lives in the menu bar.
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

project = Path(SPECPATH).parent
IS_MAC = sys.platform == "darwin"

datas = [
    (str(project / "assets" / "icon.png"), "assets"),
    (str(project / "assets" / "tray_idle.png"), "assets"),
    (str(project / "assets" / "tray_recording.png"), "assets"),
    (str(project / "assets" / "tray_busy.png"), "assets"),
]
if (project / "assets" / "icon.ico").exists():
    datas.append((str(project / "assets" / "icon.ico"), "assets"))

datas += collect_data_files("faster_whisper")
datas += collect_data_files("onnxruntime")

binaries = collect_dynamic_libs("ctranslate2")
binaries += collect_dynamic_libs("onnxruntime")

hiddenimports = [
    "faster_whisper", "ctranslate2", "onnxruntime", "tokenizers",
    "sounddevice", "_sounddevice_data", "PIL._tkinter_finder",
    "tkinter", "tkinter.ttk",
]
if IS_MAC:
    hiddenimports += ["pynput.keyboard._darwin", "pynput.mouse._darwin",
                      "pystray._darwin"]
else:
    hiddenimports += ["pynput.keyboard._win32", "pynput.mouse._win32",
                      "pystray._win32", "winsound"]

icon = None
if IS_MAC and (project / "assets" / "icon.icns").exists():
    icon = str(project / "assets" / "icon.icns")
elif not IS_MAC:
    icon = str(project / "assets" / "icon.ico")

a = Analysis(
    [str(project / "launcher.py")],
    pathex=[str(project)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["torch", "matplotlib", "scipy", "pandas", "pytest", "setuptools"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if IS_MAC:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="CoconutWhisper",
        debug=False,
        strip=False,
        upx=False,
        console=False,
        icon=icon,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="CoconutWhisper",
    )
    app = BUNDLE(
        coll,
        name="Coconut Whisper.app",
        icon=icon,
        bundle_identifier="com.coconutva.whisper",
        version="0.1.0",
        info_plist={
            "CFBundleName": "Coconut Whisper",
            "CFBundleDisplayName": "Coconut Whisper",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            # menu bar app, no icon in the dock
            "LSUIElement": True,
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription":
                "Coconut Whisper listens while you hold the dictation key and "
                "turns your speech into text on this Mac.",
            "NSAppleEventsUsageDescription":
                "Coconut Whisper pastes the text you dictated into the app you "
                "are using.",
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="CoconutWhisper",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        runtime_tmpdir=None,
        console=False,
        icon=icon,
        version=str(project / "build" / "version_info.txt"),
    )
