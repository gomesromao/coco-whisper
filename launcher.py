"""Entry point used by the packaged executable."""
import multiprocessing
import sys


def selftest() -> int:
    """Import everything the app needs and report. Used by CI to catch a
    packaging mistake on a platform we cannot click through by hand."""
    modules = [
        "faster_whisper", "ctranslate2", "onnxruntime", "sounddevice",
        "numpy", "pynput.keyboard", "pystray", "pyperclip", "tkinter",
        "app.main", "app.ui", "app.transcribe", "app.platform_support",
    ]
    failed = []
    for name in modules:
        try:
            __import__(name)
            print("ok   " + name)
        except Exception as exc:
            failed.append(name)
            print("FAIL " + name + ": " + str(exc))
    if failed:
        print("selftest failed: " + ", ".join(failed))
        return 1
    print("selftest passed on " + sys.platform)
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    if "--version" in sys.argv:
        from app.main import VERSION

        print("Coconut Whisper " + VERSION)
        raise SystemExit(0)

    from app.main import main

    main()
