"""Phone notifications (ntfy) and the phone page's endpoints."""
import logging

import pytest

from lumberjack import notify


@pytest.fixture
def sent(monkeypatch, tmp_path):
    monkeypatch.setattr(notify, "FILE", tmp_path / "notify.json")
    out = []
    monkeypatch.setattr(notify, "send", lambda title, msg, prio=3, tags=(), cfg=None, wait=False:
                        out.append((title, msg, prio)))
    return out


def on(**kw):
    notify.save({**notify.load(), "enabled": True, **kw})


def status(**kw):
    st = {"running": True, "task": "fishing", "state": "fishing", "logs": 1244, "per_hour": 242,
          "cooked": 1154, "burnt": 72, "elapsed": 18500, "error": None, "stop_reason": None,
          "xp": {"cooking": {"level": 78, "levels_gained": 0, "gained": 150000, "per_hour": 29000}},
          "session": {"recoveries": 0}, "updating": False}
    return {**st, **kw}


class FakeCtl:
    def __init__(self):
        self.st = status()

    def status(self):
        return self.st

    def running(self):
        return self.st["running"]


def test_first_load_makes_up_a_private_topic(sent):
    c = notify.load()
    assert c["topic"].startswith("grindstone-") and len(c["topic"]) > 15
    assert notify.load()["topic"] == c["topic"]          # kept, not a new one each time
    assert not c["enabled"]


def test_nothing_is_sent_while_turned_off(sent):
    ctl = FakeCtl()
    w = notify.Watcher(ctl.status, ctl.running)
    w.tick()
    ctl.st = status(running=False, stop_reason="crashed: boom")
    w.tick()
    assert sent == []


def test_a_run_that_stops_by_itself_is_reported_but_not_a_stop_you_pressed(sent):
    on()
    ctl = FakeCtl()
    w = notify.Watcher(ctl.status, ctl.running)
    w.tick()
    ctl.st = status(running=False, stop_reason="Giving up: no fishing spots")
    w.tick()
    assert len(sent) == 1 and "Fishing stopped" in sent[0][0] and "1,244 done" in sent[0][1]
    assert sent[0][2] == 4                                # a problem: high priority
    ctl.st = status()
    w.tick()
    ctl.st = status(running=False, stop_reason="stopped from control panel")
    w.tick()
    ctl.st = status()
    w.tick()
    ctl.st = status(running=False, stop_reason="plan finished")
    w.tick()
    assert len(sent) == 2 and sent[1][2] == 3             # finished: normal priority


def test_level_ups_and_the_summary(sent):
    on(summary_hours=2)
    ctl = FakeCtl()
    w = notify.Watcher(ctl.status, ctl.running)
    w.tick(now=0)
    ctl.st = status(xp={"cooking": {"level": 79, "levels_gained": 1, "gained": 160000}})
    w.tick(now=60)
    assert sent[-1][0] == "Cooking level 79!"
    w.tick(now=2 * 3600 + 1)
    assert "still going" in sent[-1][0] and "Cooking 79 (+1)" in sent[-1][1]
    n = len(sent)
    w.tick(now=2 * 3600 + 60)                             # not again straight away
    assert len(sent) == n


def test_problem_lines_are_pushed_once_per_cooldown(sent):
    on()
    h = notify.ProblemHandler()
    log = logging.getLogger("fishing")
    rec = lambda m: log.makeRecord("fishing", logging.WARNING, __file__, 1, m, (), None)
    h.emit(rec("Giving up after 3 tries in a row"))
    h.emit(rec("Giving up after 3 tries in a row"))
    h.emit(rec("+1 fish - 5 fish"))
    assert [t for t, _, _ in sent] == ["Grindstone gave up on a step"]
    notify.save({**notify.load(), "problems": False})
    h.emit(rec("The game window is minimized - waiting until it's back"))
    assert len(sent) == 1


def test_save_cleans_the_settings(sent):
    c = notify.save({"topic": "my topic/../x", "server": "https://ntfy.sh/", "summary_hours": "bad"})
    assert c["topic"] == "mytopicx" and c["server"] == "https://ntfy.sh" and c["summary_hours"] == 0


def test_phone_page_and_its_endpoints(sent, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from lumberjack.web import server
    c = TestClient(server.app)
    assert "Phone notifications" in c.get("/m").text
    assert c.get("/phone.svg").headers["content-type"].startswith("image/svg+xml")
    assert "wss" in c.get("/").text
    assert "data-fold" in c.get("/").text                 # the info lists under Start fold away                      # the live log works over Tailscale's https too
    cfg = c.get("/api/notify").json()
    assert cfg["topic"].startswith("grindstone-")
    r = c.post("/api/notify", json={**cfg, "enabled": True, "summary_hours": 4}).json()
    assert r["enabled"] and r["summary_hours"] == 4 and notify.load()["enabled"]
    assert c.post("/api/notify/test").json()["ok"] and sent[-1][0] == "Grindstone test"
    info = c.get("/api/start_saved").json()
    assert "task" in info and "plan_steps" in info
    monkeypatch.setattr(server, "load_plan", lambda: server.Plan(steps=[]))
    r = c.post("/api/start_saved", json={"what": "plan"})
    assert r.status_code == 400 and "no plan" in r.json()["error"]


def test_send_posts_to_the_topic_with_plain_headers(monkeypatch, tmp_path):
    monkeypatch.setattr(notify, "FILE", tmp_path / "notify.json")
    got = {}

    class R:
        def close(self):
            pass

    def urlopen(req, timeout):
        got.update(url=req.full_url, data=req.data, headers=dict(req.header_items()))
        return R()

    monkeypatch.setattr(notify.urllib.request, "urlopen", urlopen)
    cfg = notify.save({"topic": "grindstone-abc", "click": "https://pc.tail.ts.net/m"})
    assert notify.send("Cooking level 79! 🎉", "yay", 2, ("tada",), cfg, wait=True) is None
    assert got["url"] == "https://ntfy.sh/grindstone-abc" and got["data"] == b"yay"
    h = {k.lower(): v for k, v in got["headers"].items()}
    assert h["title"] == "Cooking level 79!" and h["priority"] == "2" and h["tags"] == "tada"
    assert h["click"] == "https://pc.tail.ts.net/m"
    monkeypatch.setattr(notify.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    assert "offline" in notify.send("x", "y", cfg=cfg, wait=True)       # never raises


def test_phone_live_view_frames_shrink_for_mobile_data(monkeypatch):
    import cv2
    import numpy as np
    from fastapi.testclient import TestClient
    from lumberjack.web import server

    class Win:
        def grab(self):
            rng = np.random.default_rng(1)
            return (rng.random((503, 765, 3)) * 255).astype(np.uint8)

    monkeypatch.setattr(server, "window", lambda: Win())
    c = TestClient(server.app)
    full = c.get("/snapshot.jpg?marks=false")
    small = c.get("/snapshot.jpg?q=45&scale=0.6&marks=false")
    assert full.status_code == small.status_code == 200 and small.headers["content-type"] == "image/jpeg"
    assert len(small.content) < len(full.content) / 2
    img = cv2.imdecode(np.frombuffer(small.content, np.uint8), cv2.IMREAD_COLOR)
    assert img.shape[1] == round(765 * 0.6)
    assert c.get("/snapshot.jpg?q=1000&scale=9&marks=false").status_code == 200      # clamped, not an error
    page = c.get("/m").text
    assert "Watch live" in page and "visibilitychange" in page


def test_a_reconnecting_page_gets_no_log_line_twice():
    import logging
    from fastapi.testclient import TestClient
    from lumberjack.web import server
    c = TestClient(server.app)
    log = logging.getLogger("fishing")
    log.info("line A")
    with c.websocket_connect("/ws") as w:
        first = w.receive_json()
    assert "line A" in " ".join(first["log"])
    log.info("line B")
    with c.websocket_connect(f"/ws?since={first['log_seq']}") as w:
        again = w.receive_json()
    assert not any("line A" in t for t in again["log"]) and any("line B" in t for t in again["log"])
    with c.websocket_connect(f"/ws?since={first['log_seq'] + 10**6}") as w:     # a panel restarted
        assert w.receive_json()["log"]


def test_connection_reset_tracebacks_are_not_printed():
    import logging
    import sys
    from lumberjack.web import server  # noqa: F401  (adds the filter)
    lg = logging.getLogger("asyncio")
    try:
        raise ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host")
    except ConnectionResetError:
        rec = lg.makeRecord("asyncio", logging.ERROR, __file__, 1, "Exception in callback", (), sys.exc_info())
    assert not lg.filter(rec)
    assert lg.filter(lg.makeRecord("asyncio", logging.ERROR, __file__, 1, "something else", (), None))
