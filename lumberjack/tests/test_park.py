"""A minimized game window is kept up off-screen while a bot runs (core/park.py)."""
import pytest

from lumberjack.core import park


class Gui:
    """A pretend win32gui with one window."""

    def __init__(self):
        self.iconic, self.fg = False, None
        self.place = (0, park.SW_SHOWNORMAL, (-1, -1), (-1, -1), (100, 50, 900, 650))
        self.calls = []

    def IsIconic(self, h):
        return self.iconic

    def GetForegroundWindow(self):
        return self.fg

    def GetWindowPlacement(self, h):
        return self.place

    def SetWindowPlacement(self, h, p):
        self.calls.append(p[1])
        self.place = p
        self.iconic = p[1] == park.SW_SHOWMINNOACTIVE

    def SetWindowPos(self, *a):
        self.calls.append("bottom")


class Api:
    @staticmethod
    def GetSystemMetrics(i):
        return -1920 if i == park.SM_XVIRTUALSCREEN else 0     # a second monitor on the left


@pytest.fixture(autouse=True)
def clean():
    park._parked.clear()
    yield
    park._parked.clear()


def make(running=True):
    g = Gui()
    state = {"run": running}
    return g, state, park.Parker(g, Api(), lambda: 7, lambda: state["run"])


def test_minimized_while_running_goes_off_screen_without_focus():
    g, st, p = make()
    p.tick(now=0)
    assert g.calls == []                                     # on screen: left alone
    g.iconic = True                                          # you minimize it
    p.tick(now=1)
    show, rect = g.place[1], g.place[4]
    assert show == park.SW_SHOWNOACTIVATE and "bottom" in g.calls
    assert rect[2] <= -1920 and rect[2] - rect[0] == 800 and rect[3] - rect[1] == 600   # same size, left of every screen
    assert park.is_parked(7)


def test_clicking_it_on_the_taskbar_brings_it_back_where_it_was():
    g, st, p = make()
    g.iconic = True
    p.tick(now=0)
    g.fg = 7                                                 # Windows gave it the focus
    p.tick(now=1)                                            # too soon after parking: ignored
    assert park.is_parked(7)
    p.tick(now=5)
    assert not park.is_parked(7) and g.place[1] == park.SW_SHOWNORMAL and g.place[4] == (100, 50, 900, 650)


def test_when_the_run_ends_it_is_minimized_again_as_it_was_left():
    g, st, p = make()
    g.iconic = True
    p.tick(now=0)
    st["run"] = False
    p.tick(now=5)
    assert not park.is_parked(7) and g.place[1] == park.SW_SHOWMINNOACTIVE and g.place[4] == (100, 50, 900, 650)


def test_nothing_happens_when_no_bot_runs():
    g, st, p = make(running=False)
    g.iconic = True                                          # a minimized game while idle stays minimized
    p.tick(now=0)
    assert g.calls == [] and not park.is_parked(7)


def test_closing_the_panel_never_leaves_it_off_screen():
    g, st, p = make()
    g.iconic = True
    p.tick(now=0)
    p.release()
    assert not park.is_parked(7) and g.place[4] == (100, 50, 900, 650)
