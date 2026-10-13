"""Let a bot keep going when its game window gets minimized.

A minimized game stops drawing frames, and the bot needs those frames (and the game data that's
read on each frame), so it used to wait until the window came back. While a bot runs, a
minimized game window is instead put back up off-screen ("parked") without taking the focus:
it keeps drawing, and you don't see it. Clicking it on the taskbar (or Alt+Tab to it) brings it
back where it was; when the run ends it goes back to minimized, the way you left it.

Takes the win32gui / win32api modules as arguments so the logic can be tested off Windows."""
import logging
import time

SW_SHOWNORMAL = 1
SW_SHOWNOACTIVATE = 4
SW_SHOWMINNOACTIVE = 7
HWND_BOTTOM = 1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
OFF_SCREEN_GAP = 200        # px left of the leftmost monitor
SETTLE_S = 2.0              # just parked: the focus may still be moving - don't read it as a click
CHECK_S = 0.5

log = logging.getLogger("panel")
_parked = {}                # hwnd -> its normal rectangle before it was parked


def is_parked(hwnd):
    return hwnd in _parked


class Parker:
    def __init__(self, gui, api, find_hwnd, running):
        self.gui, self.api = gui, api
        self.find_hwnd, self.running = find_hwnd, running    # callables
        self.parked_at = 0.0
        self.told = False

    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        running = self.running()
        if not running and not _parked:
            return                              # nothing to do (and no need to look for the game)
        try:
            hwnd = self.find_hwnd()
        except Exception:
            hwnd = None
        if not hwnd:
            _parked.clear()                     # the game closed (or restarted): nothing to keep
            return
        gui = self.gui
        if running:
            if gui.IsIconic(hwnd):
                self.park(hwnd, now)
            elif hwnd in _parked and now - self.parked_at > SETTLE_S and gui.GetForegroundWindow() == hwnd:
                self.unpark(hwnd, minimize=False)
                log.info("The game window is back on screen")
        elif hwnd in _parked:
            self.unpark(hwnd, minimize=True)    # run over: minimized again, as it was left

    def park(self, hwnd, now):
        gui = self.gui
        flags, show, pt_min, pt_max, rect = gui.GetWindowPlacement(hwnd)
        normal = _parked.get(hwnd, rect)
        w, h = normal[2] - normal[0], normal[3] - normal[1]
        x = self.api.GetSystemMetrics(SM_XVIRTUALSCREEN) - w - OFF_SCREEN_GAP
        y = self.api.GetSystemMetrics(SM_YVIRTUALSCREEN)
        _parked[hwnd] = normal
        gui.SetWindowPlacement(hwnd, (0, SW_SHOWNOACTIVATE, pt_min, pt_max, (x, y, x + w, y + h)))
        gui.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
        self.parked_at = now
        if not self.told:
            self.told = True
            log.info("The game window was minimized - Grindstone keeps it running off-screen so the "
                     "bot carries on. Click it on the taskbar to bring it back")

    def unpark(self, hwnd, minimize):
        normal = _parked.pop(hwnd)
        try:
            flags, show, pt_min, pt_max, _ = self.gui.GetWindowPlacement(hwnd)
            self.gui.SetWindowPlacement(hwnd, (0, SW_SHOWMINNOACTIVE if minimize else SW_SHOWNORMAL,
                                               pt_min, pt_max, normal))
        except Exception as e:                  # the window went away meanwhile
            log.debug("couldn't put the game window back: %s", e)

    def release(self):
        """The panel is closing: put a parked window back (minimized), never leave it off-screen."""
        for hwnd in list(_parked):
            self.unpark(hwnd, minimize=True)

    def loop(self):
        while True:
            time.sleep(CHECK_S)
            try:
                self.tick()
            except Exception:
                log.debug("park check failed", exc_info=True)
