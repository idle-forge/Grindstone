"""Dropping known items: shift-click when the game makes Drop the left-click option with Shift
held, the right-click menu when it doesn't - decided from the game's own menu, never guessed."""
import pytest

from lumberjack import actions
from lumberjack.core import regions as R
from lumberjack.core.input import VK_SHIFT


class Inp:
    def __init__(self, game):
        self.game, self.shift, self.pos, self.calls = game, False, (0, 0), []

    def key_down(self, vk):
        assert vk == VK_SHIFT
        self.shift = True

    def key_up(self, vk):
        self.shift = False

    def move(self, x, y, steps=None):
        self.pos = (x, y)
        self.game.menu_open = False

    def right_click(self, x, y):
        self.pos = (x, y)
        self.calls.append("right")
        self.game.menu_open = True

    def click(self, x=None, y=None):
        if x is not None:
            self.pos = (x, y)
        g = self.game
        if g.menu_open:
            self.calls.append("menu")
            g.drop_hovered(g.menu_slot)
            g.menu_open = False
        else:
            self.calls.append("shift" if self.shift else "left")
            if self.shift and g.shift_drops:
                g.drop_hovered(g.slot_at(self.pos))
            else:
                g.wrong_clicks += 1


class Game:
    def __init__(self, shift_drops):
        self.shift_drops, self.menu_open, self.menu_slot, self.wrong_clicks = shift_drops, False, None, 0
        self.inv = {i: "raw_karambwan" for i in range(25)}
        self.inp = None

    def slot_at(self, pos):
        return min(R.INV_SLOTS, key=lambda i: abs(R.INV_SLOTS[i].center[0] - pos[0]) +
                   abs(R.INV_SLOTS[i].center[1] - pos[1])) if isinstance(R.INV_SLOTS, dict) else \
            min(range(len(R.INV_SLOTS)), key=lambda i: abs(R.INV_SLOTS[i].center[0] - pos[0]) +
                abs(R.INV_SLOTS[i].center[1] - pos[1]))

    def drop_hovered(self, i):
        self.inv.pop(i, None)

    def menu(self):
        i = self.slot_at(self.inp.pos)
        if self.menu_open:
            self.menu_slot = i
            return {"open": True, "x": 0, "y": 0, "w": 100, "entries": [
                {"verb": "Use", "subject": "Raw karambwan", "row": 0},
                {"verb": "Drop", "subject": "Raw karambwan", "row": 1}]}
        top = "Drop" if (self.inp.shift and self.shift_drops) else "Use"
        return {"open": False, "entries": [{"verb": top, "subject": "Raw karambwan", "row": 0}]}


class Ctx:
    def __init__(self, game):
        self.inp = game.inp

    def sleep(self, s):
        pass


@pytest.fixture
def setup(monkeypatch):
    def make(shift_drops):
        monkeypatch.setattr(actions, "SHIFT_DROP_MENU", None)
        monkeypatch.setattr(actions, "open_tab", lambda ctx, t: None)
        monkeypatch.setattr(actions, "cancel_selection", lambda ctx, force=False: False)
        from lumberjack.core import gamestate
        monkeypatch.setattr(gamestate, "menu_row_point", lambda m, row: (50, 10 + 15 * row))
        g = Game(shift_drops)
        g.inp = Inp(g)
        return g, Ctx(g)
    return make


def test_shift_click_is_used_when_the_game_offers_drop(setup):
    g, ctx = setup(True)
    assert actions.drop_known(ctx, g, list(g.inv)) == 25
    assert not g.inv and g.wrong_clicks == 0
    assert g.inp.calls == ["shift"] * 25                  # no right-click menus at all
    assert actions.SHIFT_DROP_MENU is True and not g.inp.shift     # Shift let go afterwards


def test_a_client_without_it_falls_back_to_the_menu_and_never_misclicks(setup):
    g, ctx = setup(False)
    assert actions.drop_known(ctx, g, list(g.inv)) == 25
    assert not g.inv and g.wrong_clicks == 0
    assert "shift" not in g.inp.calls and g.inp.calls.count("menu") == 25
    assert actions.SHIFT_DROP_MENU is False and not g.inp.shift
    g.inv = {0: "raw_karambwan"}
    g.inp.calls.clear()
    actions.drop_known(ctx, g, [0])                       # remembered: no Shift tried again
    assert g.inp.calls == ["right", "menu"]
