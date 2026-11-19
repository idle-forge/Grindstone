"""Construction (garden builds) and Summoning (pouches at the obelisk) with a fake game."""
import sys
import types

_stub = types.ModuleType("lumberjack.core.input")
_stub.VK_LEFT, _stub.VK_RIGHT, _stub.VK_UP, _stub.VK_DOWN, _stub.VK_SHIFT = 0x25, 0x27, 0x26, 0x28, 0x10


class _NoInput:
    def __init__(self, *a, **k):
        raise RuntimeError("tests must never create AgentInput")


_stub.AgentInput = _NoInput
sys.modules.setdefault("lumberjack.core.input", _stub)

from lumberjack import actions  # noqa: E402
from lumberjack.core import backpack, gamestate  # noqa: E402
from lumberjack.skills import house_tasks as H  # noqa: E402


def test_best_garden_decoration_by_level():
    assert H.best_deco(15363, 1) is None                       # trees from 5
    assert H.best_deco(15363, 5)[1] == "Dead tree"
    assert H.best_deco(15363, 99)[1] == "Magic tree" and H.best_deco(15363, 99)[0] == 6
    assert H.best_deco(15366, 1)[1] == "Plant" and H.best_deco(15366, 12)[1] == "Fern"
    assert H.SLOT_OF[6] == 5 and H.SLOT_OF[3] == 6               # the box's slot order (BuildingUtils)


def test_best_pouch_and_a_backpack_load():
    assert H.best_pouch(1)[1] == "Spirit wolf pouch"
    assert H.best_pouch(23)[1] == "Albino rat pouch"             # 202 xp beats the tz-kih's 97
    assert H.best_pouch(99)[1] == "Talon beast pouch"
    wolf = H.best_pouch(1)
    assert H.per_load(wolf) == 13                                 # charms + shards stack: 26 slots / 2
    golem = next(p for p in H.POUCHES if p[1] == "Obsidian golem pouch")
    assert H.per_load(golem) == 25                                # only the empty pouch doesn't stack


def builder(gs, monkeypatch):
    c = H.Constructor.__new__(H.Constructor)
    c.gs, c.ctx, c.state, c.log = gs, None, "", __import__("logging").getLogger("t")
    c.built = c.removed = 0
    c.sleep = lambda s: None
    monkeypatch.setattr(gamestate, "skill", lambda name: {"base": 20, "xp": 0})
    return c


def test_construction_removes_first_then_builds_the_best(monkeypatch):
    locs = [{"id": 13431, "name": "Plant", "ops": ["Remove"], "tile": [1, 1], "dist": 2},
            {"id": 15363, "name": "Tree space", "ops": ["Build"], "tile": [2, 2], "dist": 3},
            {"id": 15366, "name": "Small plant space 1", "ops": ["Build"], "tile": [3, 3], "dist": 1}]
    gs = types.SimpleNamespace(locs=lambda radius=15, name=None: locs)
    c = builder(gs, monkeypatch)
    did = []
    c.remove = lambda loc: did.append(("remove", loc["id"])) or True
    c.build = lambda loc, deco: did.append(("build", loc["id"], deco[1])) or True
    assert c.tick() and did == [("remove", 13431)]
    locs.pop(0)
    assert c.tick() and did[-1] == ("build", 15366, "Fern")       # 100 xp beats the oak tree's 70 at level 20


def test_summoning_spawns_a_backpack_of_ingredients(monkeypatch):
    inv = [{"id": 12047, "key": "spirit_wolf_pouch", "count": 1}] * 13 + [{"id": -1, "key": None}] * 15
    monkeypatch.setattr(backpack, "slots", lambda: inv)
    s = H.Summoner.__new__(H.Summoner)
    s.gs, s.ctx, s.state, s.log = object(), None, "", __import__("logging").getLogger("t")
    s.sleep = lambda x: None
    dropped, spawned = [], []

    def drop(ctx, gs, slots):
        dropped.extend(slots)
        for i in slots:
            inv[i] = {"id": -1, "key": None}
    monkeypatch.setattr(actions, "drop_known", drop)

    def spawn(iid, n):
        spawned.append((iid, n))
        if iid in H.STACKS:
            inv[next(i for i, x in enumerate(inv) if x["id"] < 0)] = {"id": iid, "key": "x", "count": n}
        else:
            for _ in range(n):
                inv[next(i for i, x in enumerate(inv) if x["id"] < 0)] = {"id": iid, "key": "x", "count": 1}
    s.spawn_id = spawn
    wolf = H.best_pouch(1)
    s.restock(wolf)
    assert dropped == list(range(13))                              # the last load's pouches
    assert spawned == [(12158, 13), (12155, 13), (2859, 13), (12183, 91)] and s.has_load(wolf)


def test_construction_goes_back_in_when_clicks_build_nothing(monkeypatch):
    """6 min of clicking with 0 built: after a run of empty tries it goes in through the portal
    again, and if that changes nothing either, it stops (Autopilot moves on)."""
    gs = types.SimpleNamespace(locs=lambda radius=15, name=None: [])
    c = builder(gs, monkeypatch)
    c.reentered, c.stop_reason = False, None
    c.prepare = c.check_stop = lambda: None
    c.inp = types.SimpleNamespace(close=lambda: None)
    c.stats = lambda: ""
    monkeypatch.setattr(gamestate, "shared", lambda: gs)
    monkeypatch.setattr(actions, "dismiss_dialog", lambda ctx: None)
    c.tick = lambda: True                       # always "doing something", never building
    c.in_house = lambda: True
    entered = []
    c.enter_house = lambda force=False: entered.append(force)
    c.run()
    assert entered == [False, True] and "nothing to build" in c.stop_reason


class PouchList:
    """The infusing screen: 78 pouches in a list whose visible part is 4 rows (y 60-220)."""
    def __init__(self, wheel=True):
        self.scroll, self.mouse, self.can_wheel = 0, (0, 0), wheel

    def comps(self):
        out = []
        filler = [(1, f"Pouch {k}", 20000 + k, 0, []) for k in range(30)]    # the low-level pouches first
        for n, (_, name, obj, _, _) in enumerate(filler + H.POUCHES):
            out.append({"if": H.INFUSE_BOX, "x": 20 + (n % 8) * 50, "y": 60 + (n // 8) * 40 - self.scroll,
                        "w": 40, "h": 36, "obj": obj, "text": "", "name": name, "ops": []})
        return out

    def under_mouse(self):
        x, y = self.mouse
        if not 60 <= y < 220:
            return None                       # outside the list's view: the list doesn't get it
        return next((w for w in self.comps() if w["x"] <= x < w["x"] + w["w"] and w["y"] <= y < w["y"] + w["h"]), None)

    def menu(self):
        w = self.under_mouse()
        return {"open": False, "entries": [{"verb": "Infuse", "subject": w["name"], "row": 0}] if w else
                [{"verb": "Walk here", "subject": "", "row": 0}]}


def test_a_pouch_below_the_lists_view_is_scrolled_into_it(monkeypatch):
    """v165: "No Infuse-All for Bronze minotaur pouch" every try - the list holds every pouch, and
    the higher ones have a position below its visible part: hovering there isn't the pouch."""
    from lumberjack.ui import widgets
    for wheel_works in (True, False):
        g = PouchList(wheel_works)
        monkeypatch.setattr(widgets, "find", lambda gs, match=None: g.comps())
        s = H.Summoner.__new__(H.Summoner)
        s.gs, s.ctx, s.state, s.log = g, None, "", __import__("logging").getLogger("t")
        s.sleep = lambda x: None

        def wheel(x, y, n):
            if not g.can_wheel:
                return False
            g.scroll += 40 * n // 3
            return True
        s.inp = types.SimpleNamespace(move=lambda x, y: setattr(g, "mouse", (x, y)), wheel=wheel)
        pouch = next(p for p in H.POUCHES if "Bronze minotaur" in p[1])
        item = s.pouch_in_view(pouch, g.comps())
        if wheel_works:
            assert item is not None and 60 <= widgets.center(item)[1] < 220 and g.scroll > 0
            assert g.under_mouse()["name"] == pouch[1]
        else:
            assert item is None and s._told_wheel                     # says to restart the game once
