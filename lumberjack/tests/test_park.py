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


def test_the_game_is_found_inside_a_bigger_frame_and_remembered(tmp_path, monkeypatch):
    import numpy as np
    from lumberjack.core import frames
    monkeypatch.setattr(frames, "CROP_FILE", tmp_path / "frame_crop.json")
    monkeypatch.setattr(frames, "_crop", None)
    big = np.zeros((768, 1024, 3), np.uint8)                 # Fixed screen mode in a 1024x768 window
    big[0:503, 129:129 + 765] = 60                            # the game, black all around
    big[0, 129] = big[502, 129 + 764] = 200
    assert frames.crop_offset(big) == (129, 0)
    dark = np.zeros((768, 1024, 3), np.uint8)                 # a loading screen: nothing to see
    dark[200:210, 300:310] = 90
    assert frames.crop_offset(dark) == (129, 0)               # still knows where the game is
    monkeypatch.setattr(frames, "_crop", None)                # ... also after a restart
    assert frames.crop_offset(dark) == (129, 0)
    assert frames.crop_offset(np.zeros((700, 900, 3), np.uint8)) is None    # a size never seen


def test_the_add_on_frame_is_cropped_to_the_game(tmp_path, monkeypatch):
    import numpy as np
    from lumberjack.core import frames
    monkeypatch.setattr(frames, "CROP_FILE", tmp_path / "frame_crop.json")
    monkeypatch.setattr(frames, "_crop", None)
    big = np.zeros((768, 1024, 4), np.uint8)
    big[0:503, 129:129 + 765, :3] = 77
    payload = big.tobytes()

    class Sock:
        def sendall(self, b):
            pass

    class File:
        def __init__(self):
            self.lines = [b"ok 1024 768\n"]

        def readline(self):
            return self.lines.pop(0)

        def read(self, n):
            return payload[:n]

    monkeypatch.setattr(frames, "_sock", Sock())
    monkeypatch.setattr(frames, "_file", File())
    monkeypatch.setattr(frames, "_off_until", 0.0)
    img = frames.grab()
    assert img.shape == (503, 765, 3) and int(img.min()) == 77 and frames.last_error is None
