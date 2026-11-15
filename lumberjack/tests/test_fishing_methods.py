"""Monkfish and karambwan: their own spots (by NPC id), gear, places and route tiers."""
from lumberjack.core import backpack
from lumberjack.nav import training
from lumberjack.skills import fishing
from lumberjack.skills.cooking_task import CATCH_LEVELS


def spot(i, ops, tile=(0, 0)):
    return {"id": i, "ops": ops, "tile": list(tile), "dist": 3, "screen": [200, 200], "body": [200, 190]}


def test_high_levels_go_to_karambwan_then_monkfish_on_the_route():
    assert training.pick("fishing", 96) == ("★ Karamja karambwan", {"fish_method": "karambwan", "auto_fish": False})
    assert training.pick("fishing", 63)[1]["fish_method"] == "monkfish"
    assert training.pick("fishing", 55)[1]["fish_method"] == "harpoon"
    for name in ("★ Karamja karambwan", "★ Piscatoris fishing"):
        assert name in training.STARTER_PLACES
    # the "by level" switch on: Start goes there; a plain harpoon pick still means Catherby
    assert training.start_for("fishing", {"auto_fish": True}, 96)[0] == "★ Karamja karambwan"
    assert training.start_for("fishing", {"fish_method": "karambwan"}, 96)[0] == "★ Karamja karambwan"
    assert training.start_for("fishing", {"fish_method": "harpoon"}, 96)[0] == "★ Catherby fishing"


def test_gear_bait_and_catches_are_known():
    assert fishing.TOOL_ITEMS["karambwan"] == ["karambwan_vessel", "raw_karambwanji"]
    assert fishing.TOOL_ITEMS["monkfish"] == ["small_fishing_net"]
    assert fishing.METHOD_VERB["karambwan"] == "Fish" and fishing.METHOD_VERB["monkfish"] == "Net"
    # the bait is a tool to keep, not a raw fish to cook or drop
    assert backpack.kind("raw_karambwanji") == "tool" and backpack.kind("karambwan_vessel") == "tool"
    assert backpack.needed_for("raw_karambwanji", "fishing") and backpack.needed_for("karambwan_vessel", "fishing")
    assert backpack.kind("raw_karambwan") == "raw" and backpack.kind("cooked_karambwan") == "cooked"
    assert CATCH_LEVELS["raw_karambwan"] == 30 and CATCH_LEVELS["raw_monkfish"] == 62
    from lumberjack import items
    assert items.BY_KEY["karambwan_vessel"][1] == 3157 and items.BY_KEY["raw_karambwanji"][1] == 3150


def test_monkfish_spots_are_not_mistaken_for_shark_spots():
    shark = spot(313, ["Net", "Harpoon"])
    monk = spot(3848, ["Net", "Harpoon"])
    assert fishing.harpoon_spots([shark, monk], "harpoon", 96) == [shark]


def test_only_the_method_s_own_spots_are_clicked(monkeypatch):
    f = fishing.Fisher.__new__(fishing.Fisher)
    f.method, f.levels, f.log = "monkfish", {"fishing": 96}, __import__("logging").getLogger("t")
    calls = []

    class Gs:
        def npcs(self, name):
            return [spot(316, ["Net", "Bait"]), spot(313, ["Net", "Harpoon"])]   # Catherby: no monkfish spots

        def player(self):
            return {"tile": [0, 0]}

    f.gs = Gs()
    from lumberjack.nav import spot_memory
    monkeypatch.setattr(spot_memory, "remember", lambda sp: None)
    f.walk_to_remembered_spot = lambda verb: calls.append(verb) or False
    f.report_gs = lambda what: None
    f.auto = False
    assert f.find_and_use_spot_gs() is False
    assert calls == ["Net"]                       # looked for its own spots instead of big-netting here


def test_new_methods_need_the_game_data_and_their_own_place():
    assert fishing.missing_templates("karambwan")             # no pixel templates for these
    ok, why = fishing.usable_method("karambwan", "cage", set(), [])
    assert not ok and "Settings" in why
    assert fishing.usable_method("karambwan", "cage", {"karambwan"}, [])[0]
    assert fishing.pick_method(["harpoon", "karambwan", "monkfish"], 96) == "karambwan"
    assert fishing.pick_method(["harpoon", "karambwan", "monkfish"], 63) == "monkfish"
