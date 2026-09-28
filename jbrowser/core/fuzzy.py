"""Small, fast fuzzy matcher used by the Lazy Toolbar.

Scores subsequence matches, rewarding consecutive characters, word-boundary hits and
prefix matches — similar in spirit to fzf / VS Code quick-open.
"""
from __future__ import annotations

from dataclasses import dataclass

_BOUNDARY = set(" ./-_:?&=#@|()[]")


@dataclass(slots=True)
class FuzzyMatch:
    score: float
    positions: tuple[int, ...]


def fuzzy_match(pattern: str, text: str) -> FuzzyMatch | None:
    """Return a score (higher is better) and matched indices, or None if no match."""
    if not pattern:
        return FuzzyMatch(0.0, ())
    if not text:
        return None
    p = pattern.lower()
    t = text.lower()

    # Fast path: contiguous substring match gets a large bonus.
    idx = t.find(p)
    if idx >= 0:
        score = 100.0 + len(p) * 8
        if idx == 0:
            score += 60
        elif t[idx - 1] in _BOUNDARY:
            score += 35
        score -= idx * 0.6
        score -= (len(t) - len(p)) * 0.08
        return FuzzyMatch(score, tuple(range(idx, idx + len(p))))

    positions: list[int] = []
    score = 0.0
    ti = 0
    prev = -2
    for ch in p:
        if ch == " ":
            continue
        found = t.find(ch, ti)
        if found < 0:
            return None
        # Prefer a word-boundary occurrence if one exists soon after.
        boundary = found
        probe = found
        while probe >= 0 and probe - found < 24:
            if probe == 0 or t[probe - 1] in _BOUNDARY:
                boundary = probe
                break
            probe = t.find(ch, probe + 1)
        if boundary != found and (prev < 0 or boundary - prev < 12):
            found = boundary
        bonus = 4.0
        if found == prev + 1:
            bonus += 10.0
        if found == 0 or t[found - 1] in _BOUNDARY:
            bonus += 8.0
        bonus -= min(found - prev - 1, 12) * 0.5 if prev >= 0 else found * 0.15
        score += bonus
        positions.append(found)
        prev = found
        ti = found + 1
    score -= (len(t) - len(positions)) * 0.05
    return FuzzyMatch(score, tuple(positions))


def best_match(pattern: str, *fields: str) -> FuzzyMatch | None:
    """Match against several fields; the first field (the title) is slightly preferred."""
    best: FuzzyMatch | None = None
    for i, field in enumerate(fields):
        if not field:
            continue
        m = fuzzy_match(pattern, field)
        if m is None:
            continue
        if i > 0:
            m = FuzzyMatch(m.score * 0.85, ())
        if best is None or m.score > best.score:
            best = m
    return best
