"""Process-wide admission for expensive media renders; desktop is unlimited."""

from functools import wraps
from threading import BoundedSemaphore, Lock, local


_lock = Lock()
_thread = local()
_slots = None
_pending = 0
_max_pending = 16
_browser_slots = None


def configure_media_limits(workers=2, pending=16, browsers=2):
    global _slots, _max_pending, _browser_slots
    if workers < 1 or pending < workers or browsers < 1:
        raise ValueError("媒体并发和排队数量配置无效")
    with _lock:
        if _pending:
            raise RuntimeError("媒体任务运行中，请在重启时调整容量")
        _slots, _max_pending = BoundedSemaphore(workers), pending
        _browser_slots = BoundedSemaphore(browsers)


def limited_browser(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        slots = _browser_slots
        if slots is None:
            return function(*args, **kwargs)
        if not slots.acquire(timeout=10):
            raise ValueError("商品采集任务较多，请稍后重试")
        try:
            return function(*args, **kwargs)
        finally:
            slots.release()

    return wrapper


def limited_media(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        global _pending
        slots = _slots
        if slots is None or getattr(_thread, "active", False):
            return function(*args, **kwargs)
        with _lock:
            if _pending >= _max_pending:
                raise ValueError("媒体任务队列已满，请稍后重试")
            _pending += 1
        acquired = False
        try:
            acquired = slots.acquire(timeout=300)
            if not acquired:
                raise ValueError("媒体任务排队超时，请稍后重试")
            _thread.active = True
            return function(*args, **kwargs)
        finally:
            _thread.active = False
            if acquired:
                slots.release()
            with _lock:
                _pending -= 1

    return wrapper
