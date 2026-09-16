# پروزه اتوماسیون بورسی
"""آزمون ایمن حرکت نشانگر ماوس در ویندوز؛ بدون کلیک یا ورود متن."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import math
import time


user32 = ctypes.windll.user32


def get_cursor_position() -> tuple[int, int]:
    """موقعیت فعلی نشانگر را برمی‌گرداند."""
    point = ctypes.wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError()
    return point.x, point.y


def move_cursor_in_circle(duration: float, radius: int, interval: float) -> None:
    """نشانگر را برای مدت مشخص، آهسته روی یک مسیر دایره‌ای حرکت می‌دهد."""
    start_x, start_y = get_cursor_position()
    screen_width = user32.GetSystemMetrics(0)
    screen_height = user32.GetSystemMetrics(1)
    started_at = time.monotonic()

    print("Mouse motion test started. No clicks will be performed. Press Ctrl+C to stop.")
    try:
        while True:
            elapsed = time.monotonic() - started_at
            if elapsed >= duration:
                break

            angle = elapsed * math.tau / 3.0
            x = round(start_x + radius * math.cos(angle))
            y = round(start_y + radius * math.sin(angle))
            x = max(0, min(screen_width - 1, x))
            y = max(0, min(screen_height - 1, y))
            user32.SetCursorPos(x, y)
            time.sleep(interval)
    finally:
        user32.SetCursorPos(start_x, start_y)
        print("Mouse motion test finished. Cursor returned to its starting point.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=15.0, help="مدت حرکت بر حسب ثانیه")
    parser.add_argument("--radius", type=int, default=120, help="شعاع حرکت بر حسب پیکسل")
    parser.add_argument("--interval", type=float, default=0.03, help="فاصلهٔ هر به‌روزرسانی بر حسب ثانیه")
    args = parser.parse_args()

    if args.duration <= 0 or args.radius <= 0 or args.interval <= 0:
        parser.error("duration، radius و interval باید مثبت باشند.")

    move_cursor_in_circle(args.duration, args.radius, args.interval)


if __name__ == "__main__":
    main()
