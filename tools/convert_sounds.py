"""Decode the UI sound effects (MP3) into 16-bit PCM WAV files for QSoundEffect.

QSoundEffect gives low-latency playback but only reads WAV, so the source MP3s are converted
once at development time with Qt's own decoder (no extra tools needed):

    python tools/convert_sounds.py SOURCE.mp3 assets/sounds/NAME.wav [--start-seconds N] [--max-seconds N] [--fade-ms N]

``--envelope`` prints a loudness envelope, which is how the first-run intro is timed to the audio.
"""
from __future__ import annotations

import argparse
import array
import sys
import wave

from PyQt6.QtCore import QCoreApplication, QUrl
from PyQt6.QtMultimedia import QAudioDecoder, QAudioFormat


def decode(path: str) -> tuple[bytes, int, int]:
    """Return (interleaved int16 PCM, sample rate, channels)."""
    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    fmt = QAudioFormat()
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    fmt.setSampleRate(44100)
    fmt.setChannelCount(2)
    dec = QAudioDecoder()
    dec.setAudioFormat(fmt)
    dec.setSource(QUrl.fromLocalFile(path))
    out = bytearray()
    info = {"rate": 44100, "channels": 2, "error": ""}

    def ready():
        while dec.bufferAvailable():
            buf = dec.read()
            f = buf.format()
            info["rate"], info["channels"] = f.sampleRate(), f.channelCount()
            out.extend(bytes(buf.constData().asstring(buf.byteCount())))

    dec.bufferReady.connect(ready)
    dec.finished.connect(app.quit)
    dec.error.connect(lambda _e: (info.__setitem__("error", dec.errorString()), app.quit()))
    dec.start()
    app.exec()
    if info["error"] and not out:
        raise RuntimeError(info["error"])
    return bytes(out), info["rate"], info["channels"]


def envelope(pcm: bytes, rate: int, channels: int, step_ms: int = 50) -> list[tuple[float, float]]:
    samples = array.array("h", pcm)
    frame = max(1, int(rate * step_ms / 1000)) * channels
    out = []
    for i in range(0, len(samples), frame):
        chunk = samples[i:i + frame]
        peak = max((abs(s) for s in chunk), default=0) / 32768
        out.append((i / channels / rate, peak))
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("target", nargs="?")
    p.add_argument("--start-seconds", type=float, default=0, help="trim leading silence")
    p.add_argument("--max-seconds", type=float, default=0)
    p.add_argument("--fade-ms", type=int, default=0)
    p.add_argument("--envelope", action="store_true")
    a = p.parse_args()
    pcm, rate, channels = decode(a.source)
    total = len(pcm) / 2 / channels / rate
    print(f"{a.source}: {total:.2f}s, {rate} Hz, {channels} ch")
    if a.envelope:
        for t, peak in envelope(pcm, rate, channels):
            print(f"{t:5.2f}s {'#' * int(peak * 60):<60} {peak:.2f}")
    if a.target:
        samples = array.array("h", pcm)
        if a.start_seconds:
            samples = samples[int(a.start_seconds * rate) * channels:]
        if a.max_seconds:
            samples = samples[:int(a.max_seconds * rate) * channels]
        if a.fade_ms:
            n = min(len(samples) // channels, int(rate * a.fade_ms / 1000))
            start = len(samples) // channels - n
            for f in range(n):
                g = 1.0 - (f + 1) / n
                for c in range(channels):
                    idx = (start + f) * channels + c
                    samples[idx] = int(samples[idx] * g)
        with wave.open(a.target, "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(samples.tobytes())
        print(f"wrote {a.target} ({len(samples) // channels / rate:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
