"""The game's frame straight from the add-on (`frame` command): the software renderer's buffer,
read inside the client. No PrintWindow / BitBlt on the game window, so capturing can't wedge the
game's UI thread (a frozen game was traced to screen grabs waiting on it).

    grab() -> 503x765x3 BGR array, or None (add-on too old / HD mode / not answering)

An add-on without the command is asked again after RETRY_S (a restarted game has the new one).
"""
import json
import socket
import threading
import time
from pathlib import Path

import numpy as np

from lumberjack.core.agent import PORT

CANVAS_W, CANVAS_H = 765, 503
CROP_FILE = Path(__file__).resolve().parents[1] / "configs" / "frame_crop.json"
_crop = None                      # {"WxH": [x, y]}: where the 765x503 game sits in a bigger frame

TIMEOUT_S = 3.0
RETRY_S = 300

_lock = threading.Lock()
_sock = None
_file = None
_off_until = 0.0
last_error = None                 # why the last grab() gave None (shown when the window can't help)


def _close():
    global _sock, _file
    try:
        if _sock:
            _sock.close()
    except OSError:
        pass
    _sock = _file = None


def grab():
    global _sock, _file, _off_until, last_error
    if time.monotonic() < _off_until:
        last_error = "the game's add-on is too old to send frames (restart the game with the Grindstone icon)"
        return None
    with _lock:
        try:
            if _sock is None:
                _sock = socket.create_connection(("127.0.0.1", PORT), timeout=TIMEOUT_S)
                _file = _sock.makefile("rb")
            _sock.sendall(b"frame\n")
            head = _file.readline().decode("ascii", "replace").split()
            if not head or head[0] != "ok":
                why = " ".join(head)
                last_error = ("the game has no picture to send (switching graphics mode? An add-on from "
                              "before HD support also says this - restart the game with the Grindstone icon)"
                              if "no frame buffer" in why else f"the add-on answered: {why or 'nothing'}")
                if head and "unknown command" in " ".join(head):
                    _off_until = time.monotonic() + RETRY_S       # old add-on: use the screen grab
                    _close()
                return None
            w, h = int(head[1]), int(head[2])
            data = _file.read(w * h * 4)
            if len(data) != w * h * 4:
                last_error = "the frame came through cut short"
                _close()
                return None
        except (OSError, ValueError, IndexError) as e:
            last_error = f"the game's add-on isn't answering ({e})"
            _close()
            return None
    img = np.frombuffer(data, np.uint8).reshape(h, w, 4)[..., :3]
    if (w, h) == (CANVAS_W, CANVAS_H):
        last_error = None
        # even a dark frame (loading screen): never fall back to screen grabs while the add-on answers
        return img.copy()
    at = crop_offset(img)
    if at is None:
        last_error = f"the game is drawing at {w}x{h} - switch it to Fixed screen mode (765x503)"
        return img.copy()
    last_error = None
    x, y = at
    return img[y:y + CANVAS_H, x:x + CANVAS_W].copy()


def _load_crop():
    global _crop
    if _crop is None:
        try:
            _crop = json.loads(CROP_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _crop = {}
    return _crop


def crop_offset(img):
    """Where the fixed 765x503 game sits inside a bigger frame (Fixed screen mode in a bigger
    window: the game is drawn at an offset with black around it). Found from the non-black
    area when that is exactly 765x503, then remembered per frame size - a dark scene later
    (night, a loading screen) can't move it. None until it has been seen once."""
    h, w = img.shape[:2]
    if w < CANVAS_W or h < CANVAS_H:
        return None
    key = f"{w}x{h}"
    known = _load_crop().get(key)
    ys, xs = np.where(img.max(axis=2) > 8)
    if len(xs):
        x, y = int(xs.min()), int(ys.min())
        if (int(xs.max()) - x + 1, int(ys.max()) - y + 1) == (CANVAS_W, CANVAS_H):
            if known != [x, y]:
                _crop[key] = [x, y]
                try:
                    CROP_FILE.parent.mkdir(parents=True, exist_ok=True)
                    CROP_FILE.write_text(json.dumps(_crop), encoding="utf-8")
                except OSError:
                    pass
            return x, y
    return tuple(known) if known else None
