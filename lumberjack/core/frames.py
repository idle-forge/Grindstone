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


VIEWPORT = (4, 4, 516, 338)      # the fixed-mode 3D view (x0, y0, x1, y1)
HALF_DRAWN = 0.08                 # this much pure black in the 3D view: maybe caught mid-draw
REREADS = 2


def _black_share(img):
    x0, y0, x1, y1 = VIEWPORT
    v = img[y0:y1, x0:x1]
    return float((v.max(axis=2) == 0).mean())


def grab():
    """The game's frame. One caught while the game was still drawing its 3D view has big black
    patches (an add-on that copies the frame after drawing never sends those): read it again
    and keep the most complete one."""
    img = _grab_once()
    if img is None or img.shape[:2] != (CANVAS_H, CANVAS_W):
        return img
    global last_error
    black, err = _black_share(img), last_error
    for _ in range(REREADS):
        if black < HALF_DRAWN:
            break
        again = _grab_once()
        if again is None or again.shape != img.shape:
            break
        b = _black_share(again)
        if b < black:
            img, black, err = again, b, last_error
    last_error = err                    # what's said about the frame we return, not a failed re-read
    return img


def _grab_once():
    global _sock, _file, _off_until, last_error, _raw
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
    _raw = (data, w, h)
    img = np.frombuffer(data, np.uint8).reshape(h, w, 4)[..., :3]
    if (w, h) == (CANVAS_W, CANVAS_H):
        last_error = None
        # even a dark frame (loading screen): never fall back to screen grabs while the add-on answers
        return img.copy()
    if w < CANVAS_W or h < CANVAS_H:
        last_error = f"the game is drawing at {w}x{h} - switch it to Fixed screen mode (765x503)"
        return img.copy()
    out = apply_layout(data, w, h)
    if out is None:
        last_error = (f"the game's picture is {w}x{h}, not the game's 765x503, and how the game sits in "
                      "it isn't known yet - keep the game window on screen for a minute while a bot runs "
                      "so Grindstone can learn it")
        return img.copy()
    last_error = None
    return out


# ---- a frame bigger than the game ---------------------------------------------------------
# The game client's frame buffer can be bigger than the 765x503 game (e.g. 1024x768: the window's
# first size). Either the game sits in it at an offset ("crop"), or the game is drawn 765 pixels
# wide into the start of the bigger buffer ("restride"). Which one is learned by comparing with
# the picture on screen while the window is visible (learn_layout), or from the black border
# around a cropped game; remembered per size in configs/frame_crop.json.
_raw = None                       # (bytes, w, h) of the last frame from the add-on
_learn_at = 0.0
LEARN_EVERY_S = 10.0
MATCH_DIFF = 14.0                 # mean difference (0-255) for a layout to count as the same picture


def _layouts():
    global _crop
    if _crop is None:
        try:
            _crop = json.loads(CROP_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _crop = {}
    return _crop


def _save_layout(key, lay):
    if _layouts().get(key) == lay:
        return
    _crop[key] = lay
    try:
        CROP_FILE.parent.mkdir(parents=True, exist_ok=True)
        CROP_FILE.write_text(json.dumps(_crop), encoding="utf-8")
    except OSError:
        pass


def _restride(data):
    n = CANVAS_W * CANVAS_H * 4
    if len(data) < n:
        return None
    return np.frombuffer(data[:n], np.uint8).reshape(CANVAS_H, CANVAS_W, 4)[..., :3].copy()


def apply_layout(data, w, h):
    """The 765x503 game out of a bigger frame, or None while its layout isn't known."""
    key = f"{w}x{h}"
    lay = _layouts().get(key)
    if isinstance(lay, list):                                  # older files: a plain [x, y]
        lay = {"crop": lay}
    if lay and lay.get("restride"):
        return _restride(data)
    img = np.frombuffer(data, np.uint8).reshape(h, w, 4)[..., :3]
    at = crop_offset(img)
    if at is None:
        return None
    x, y = at
    return img[y:y + CANVAS_H, x:x + CANVAS_W].copy()


def crop_offset(img):
    """Where the fixed 765x503 game sits inside a bigger frame: from the non-black area when that
    is exactly 765x503 (black around the game), else what was learned for this size before."""
    h, w = img.shape[:2]
    if w < CANVAS_W or h < CANVAS_H:
        return None
    key = f"{w}x{h}"
    known = _layouts().get(key)
    if isinstance(known, list):
        known = {"crop": known}
    if known and known.get("restride"):
        return None
    ys, xs = np.where(img.max(axis=2) > 8)
    if len(xs):
        x, y = int(xs.min()), int(ys.min())
        if (int(xs.max()) - x + 1, int(ys.max()) - y + 1) == (CANVAS_W, CANVAS_H):
            _save_layout(key, {"crop": [x, y]})
            return x, y
    return tuple(known["crop"]) if known else None


def needs_layout():
    return _raw is not None and (_raw[1], _raw[2]) != (CANVAS_W, CANVAS_H) and \
        apply_layout(*_raw) is None


def learn_layout(screen):
    """The window is on screen and `screen` is the game as copied from it: find which reading
    of the add-on's bigger frame gives the same picture, and remember it. True when learned."""
    global _learn_at
    if not needs_layout() or time.monotonic() - _learn_at < LEARN_EVERY_S:
        return False
    _learn_at = time.monotonic()
    data, w, h = _raw
    key = f"{w}x{h}"
    screen = screen.astype(np.int16)

    def diff(cand):
        return float(np.abs(cand.astype(np.int16) - screen).mean()) if cand is not None and \
            cand.shape == screen.shape else 1e9

    cands = [({"restride": True}, _restride(data))]
    img = np.frombuffer(data, np.uint8).reshape(h, w, 4)[..., :3]
    try:
        import cv2
        r = cv2.matchTemplate(img, screen.astype(np.uint8), cv2.TM_SQDIFF)
        x, y = cv2.minMaxLoc(r)[2]
        cands.append(({"crop": [int(x), int(y)]}, img[y:y + CANVAS_H, x:x + CANVAS_W]))
    except Exception:
        pass
    best = min(cands, key=lambda c: diff(c[1]))
    if diff(best[1]) > MATCH_DIFF:
        return False
    _save_layout(key, best[0])
    return True


class WaitNote:
    """Says once that we're waiting for a minimized game - with why the game's own picture can't
    be used meanwhile - and again whenever that reason changes (at most once a minute)."""

    def __init__(self):
        self.said, self.reason, self.at = False, None, 0.0

    def say(self, log):
        reason = last_error or "no reason given"
        now = time.monotonic()
        if not self.said:
            self.said, self.reason, self.at = True, reason, now
            log.warning("The game window is minimized - waiting until it's back (the game's own "
                        "picture can't be used: %s)", reason)
        elif reason != self.reason and now - self.at > 60:
            self.reason, self.at = reason, now
            log.warning("Still waiting for the game window - now: %s", reason)
