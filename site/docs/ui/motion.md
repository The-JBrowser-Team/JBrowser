---
title: Motion and animation
nav_title: Motion
description: The global motion policy that every animation goes through, and how to animate safely.
---

Every animation in JBrowser asks one object, [`Motion`](api:jbrowser.core.motion.Motion)
([core/motion.py](source:jbrowser/core/motion.py)), for its duration. When *Fluid animations*
(`appearance.animations`) is off, every duration becomes 0 ms and every transition jumps straight to its end. On the
first run the setting follows Windows' "Animation effects" accessibility option.

## Using it

```python
from jbrowser.core.motion import motion

# animate a Qt property
motion().animate_property(widget, b"sidebarWidth", start, end, 220, on_finished=done)

# animate any value through a callback
self._anim = motion().animate_value(self, 0.0, 1.0, self._on_frame, duration=300,
                                    easing=QEasingCurve.Type.OutCubic, on_finished=self._done)

# a plain duration for your own timer
ms = motion().ms(Motion.NORMAL)          # 200, or 0 with animations off
```

- Standard durations: `Motion.FAST` (120 ms), `NORMAL` (200 ms), `SLOW` (280 ms).
- With animations off, `animate_*` call `on_value(end)` / set the property and `on_finished()` **immediately** and
  return `None`. Code must work when the returned animation is `None`.
- `motion().changed` fires when the setting changes; long-running effects (the canvas's pull indicator, the Gallery,
  web-page smooth scrolling) listen to it.

## Stopping an animation safely

Animations are started with `QAbstractAnimation.DeletionPolicy.DeleteWhenStopped`: Qt deletes them when they finish.
A Python reference kept to an animation can therefore outlive the C++ object, and calling `.stop()` on it raises
`RuntimeError: wrapped C/C++ object … has been deleted`. Stop stored animations defensively:

```python
def _stop(anim) -> None:
    if anim is not None:
        try:
            anim.stop()
        except RuntimeError:        # it already finished and deleted itself
            pass
```

<!-- if >= 1.5.0 -->
`ui/gallery.py` has exactly this helper, and clears its references in `on_finished`.
<!-- endif -->

## Painting animations

For effects with many moving parts (the welcome, the Gallery's pop-in, the canvas layout), JBrowser animates **one
number** (a time or a progress from 0 to 1) and computes everything else from it in `paintEvent`. That keeps effects
in sync, makes them cheap, and means "animations off" only has to set the number to its end.

Easing helpers used across the UI: `out_cubic`, `out_quint`, `in_out_cubic`, `out_back` (overshoot) and `seg(t, a, b)`
(the progress of `t` through the window `a…b`), defined in `ui/onboarding.py`<!-- if >= 1.5.0 --> and `ui/gallery.py`<!-- endif -->.

## Guidelines

- 120 to 300 ms for UI transitions; longer only for deliberate moments (the welcome).
- Ease out for things arriving, ease in-out for things moving between two places.
- Never animate something the user is waiting on, such as a page load.
- Always test with *Fluid animations* off.
