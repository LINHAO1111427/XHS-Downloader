"""Shared ownership for the interactive Xiaohongshu Edge session."""
from __future__ import annotations

from threading import Lock


PROFILE_LOCK = Lock()
