# `assets/sounds/`: welcome-screen sound effects

| File | Played | Notes |
|---|---|---|
| `intro.wav` | Once, during the animated intro | Its loudness envelope sets the intro's timing (`T_FORM`, `T_LOGO`, … in `jbrowser/ui/onboarding.py`) |
| `click.wav` | On each *Next* in the welcome (not on the first slide after the intro) | Played softly (volume 0.35 in `jbrowser/ui/sounds.py`) |

Both are 16-bit PCM WAV, because the native Windows audio backend plays WAV with the lowest latency and needs no
FFmpeg. They are converted from the source MP3s:

```powershell
.\.venv\Scripts\python.exe tools\convert_sounds.py <source.mp3> assets\sounds\click.wav --start-seconds 0.05
```

The converter also prints the loudness envelope, which helps line an animation up with the sound. Sounds can be
turned off in *Settings → Appearance*. Sources and credits are in [CREDITS.txt](CREDITS.txt).
