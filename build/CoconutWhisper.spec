from pathlib import Path

# PyInstaller spec for Coconut Whisper
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

project = Path(SPECPATH).parent

datas = [
    (str(project / "assets" / "icon.ico"), "assets"),
    (str(project / "assets" / "icon.png"), "assets"),
    (str(project / "assets" / "tray_idle.png"), "assets"),
    (str(project / "assets" / "tray_recording.png"), "assets"),
    (str(project / "assets" / "tray_busy.png"), "assets"),
]
datas += collect_data_files("faster_whisper")
datas += collect_data_files("onnxruntime")

binaries = collect_dynamic_libs("ctranslate2")
binaries += collect_dynamic_libs("onnxruntime")

hiddenimports = [
    "faster_whisper", "ctranslate2", "onnxruntime", "tokenizers",
    "sounddevice", "_sounddevice_data", "pynput.keyboard._win32",
    "pynput.mouse._win32", "pystray._win32", "PIL._tkinter_finder",
    "winsound", "tkinter", "tkinter.ttk",
]

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
    icon=str(project / "assets" / "icon.ico"),
    version=str(project / "build" / "version_info.txt"),
)
