"""Burns CPU without touching the sound card.

If the hiss shows up here too, it is electrical noise from the processor load
reaching the analog audio output, not anything the app is playing.
"""
import multiprocessing
import time

SECONDS = 15


def burn(stop_at):
    x = 0.0
    while time.time() < stop_at:
        for i in range(200000):
            x += i ** 0.5


if __name__ == "__main__":
    multiprocessing.freeze_support()
    workers = max(2, min(8, multiprocessing.cpu_count()))
    print("No audio is played by this script. Listen to your speakers.")
    print(f"Loading {workers} cores for {SECONDS} seconds, starting in 3...")
    time.sleep(3)
    stop_at = time.time() + SECONDS
    procs = [multiprocessing.Process(target=burn, args=(stop_at,)) for _ in range(workers)]
    print("LOAD ON")
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    print("LOAD OFF")
    print()
    print("Heard the same hiss while it said LOAD ON? Then it is the processor,")
    print("not the app, and a smaller model or fewer threads will reduce it.")
