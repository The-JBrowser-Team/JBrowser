# `jbrowser/platform/`: Windows integration

| File | Purpose |
|---|---|
| `win.py` | Win32 and DWM through `ctypes`: Mica / Mica Alt / Acrylic backdrops, dark caption, rounded corners, the custom frame that keeps Aero Snap and the Snap Layouts flyout (its `WM_NCCALCSIZE` / `WM_NCHITTEST` handler is used by `ui/window.py`), the accent colour, the Windows "Animation effects" setting, the AppUserModelID, DPAPI encryption for local secrets, and *Show in folder* |

Each function checks `IS_WINDOWS` and the Windows build first. On older Windows versions it does nothing, or returns a
safe default, so the rest of the app never has to check the OS itself.
