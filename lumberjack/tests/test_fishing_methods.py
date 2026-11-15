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
    assert fishing.TOOL_ITEMS["karambwan"] == ["karambwan_vessel"]
    assert fishing.SLOT_BAIT["karambwan"] == "raw_karambwanji"
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


def slots(*keys):
    # as the game sends them: an empty slot's key is None
    return [{"id": 1 if k else -1, "key": k or None} for k in keys] + [{"id": -1, "key": None}] * (28 - len(keys))


def karambwan_fisher(monkeypatch, inv):
    from lumberjack.core import backpack
    monkeypatch.setattr(backpack, "slots", lambda: inv)
    f = fishing.Fisher.__new__(fishing.Fisher)
    f.method, f.keep_slots, f.drop_at = "karambwan", {0, 1}, 26
    return f


def occ(inv):
    return [s["id"] >= 0 for s in inv]


def test_one_per_slot_bait_fills_a_load_and_isnt_counted_as_fish(monkeypatch):
    # a load: vessel + coins kept, 24 karambwanji - a "full" backpack that is really just bait
    inv = slots("karambwan_vessel", "coins", *["raw_karambwanji"] * 24)
    f = karambwan_fisher(monkeypatch, inv)
    assert not f.load_full(occ(inv))                      # bait left: keep fishing
    assert f.catch_count(occ(inv)) == 0
    inv[2] = {"id": 3142, "key": "raw_karambwan"}        # a catch turns one bait into a fish
    assert f.catch_count(occ(inv)) == 1
    for i in range(3, 26):
        inv[i] = {"id": 3142, "key": "raw_karambwan"}     # all bait used up
    assert f.catch_count(occ(inv)) == 24 and f.load_full(occ(inv))


def test_the_main_loop_spawns_a_load_of_bait_not_a_stack(monkeypatch):
    inv = slots("karambwan_vessel", "coins")
    f = karambwan_fisher(monkeypatch, inv)
    spawned = []
    f.spawn_slot_bait = lambda key, n: spawned.append((key, n))
    key, bait = f.slot_bait()
    o = occ(inv)
    assert key == "raw_karambwanji" and not bait and sum(o) < f.drop_at
    f.spawn_slot_bait(key, f.drop_at - sum(o))
    assert spawned == [("raw_karambwanji", 24)]           # the free slots, leaving room as drop_at says


def test_not_cooking_drops_the_axe_and_tinderbox_but_keeps_coins(monkeypatch):
    from lumberjack import actions
    from lumberjack.core import backpack
    from lumberjack.skills import fish_cook
    inv = slots("coins", "rune_axe", None, "tinderbox", "karambwan_vessel")
    monkeypatch.setattr(backpack, "slots", lambda: inv)
    dropped = []
    monkeypatch.setattr(actions, "drop_known", lambda ctx, gs, s: dropped.extend(s))
    b = fish_cook.FishCooker.__new__(fish_cook.FishCooker)
    b.ctx, b.gs, b.spawn_tools, b.keep_slots = None, object(), True, {0, 1, 3, 4}
    b.log = __import__("logging").getLogger("t")
    b.drop_fire_tools()
    assert sorted(dropped) == [1, 3] and b.keep_slots == {0, 4}


def test_a_bait_load_always_leaves_one_slot_empty(monkeypatch):
    # not cooking: drop_at is 28 - but the game won't fish with the backpack full of bait
    inv = slots("karambwan_vessel", "coins")
    f = karambwan_fisher(monkeypatch, inv)
    f.drop_at = 28
    assert f.load_size() == 27
    for i in range(2, 27):
        inv[i] = {"id": 3142, "key": "raw_karambwan"}      # bait all used up: 27 filled
    assert f.load_full(occ(inv))                          # drop now - no 0-bait spawn loop
    inv[26] = {"id": -1, "key": None}
    assert not f.load_full(occ(inv)) and f.load_size() - sum(occ(inv)) == 1
