"""Per-user sliding-window rate limiter (in-memory)."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException

from .config import get_settings

settings = get_settings()
_windows: dict[int, deque] = defaultdict(deque)


def check_user_rate(user_id: int):
    now = time.time()
    w = _windows[user_id]
    while w and now - w[0] > 60:
        w.popleft()
    if len(w) >= settings.user_rpm_limit:
        raise HTTPException(429, "You're sending questions too fast — wait a few seconds.")
    w.append(now)
