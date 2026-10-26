"""Auto login: Start tries straight away (and lifts a pause); it says why it isn't logging in."""
import logging
import threading
import time

from lumberjack.web import server


class FakeGs:
    def __init__(self, state=10, ok=True, why=None):
        self.state, self.ok, self.why, self.logins = state, ok, why, 0

    def _q(self, what):
        return {"state": self.state}

    def login(self, user, pw):
        self.logins += 1
        return {"ok": self.ok, "why": self.why}

    def login_status(self):
        return {"state": 30}


def run_loop(monkeypatch, gs, cfg, seconds=0.6):
    from lumberjack.core import gamestate
    monkeypatch.setattr(gamestate, "GameState", lambda: gs)
    monkeypatch.setattr(server, "load_login", lambda: cfg)
    monkeypatch.setattr(server, "_click_play", lambda gs, log: None)
    monkeypatch.setattr(server, "_login_why", None)
    kick = threading.Event()
    monkeypatch.setattr(server, "_login_kick", kick)
    real_sleep = time.sleep
    monkeypatch.setattr(server.time, "sleep", lambda s: real_sleep(0.01))
    kick.set()                                            # as if Start was pressed
    t = threading.Thread(target=server.auto_login, daemon=True)
    t.start()
    real_sleep(seconds)
    return kick


def test_start_logs_in_right_away(monkeypatch):
    gs = FakeGs()
    run_loop(monkeypatch, gs, {"enabled": True, "user": "hero", "password": "pw"})
    assert gs.logins == 1


def test_a_login_screen_that_isnt_ready_is_explained(monkeypatch, caplog):
    gs = FakeGs(ok=False, why="not at an idle login screen (state 10)")
    with caplog.at_level(logging.WARNING, "login"):
        run_loop(monkeypatch, gs, {"enabled": True, "user": "hero", "password": "pw"})
    assert "waiting for the login screen" in caplog.text and "not at an idle" in caplog.text
    assert "not at an idle" in server.auto_login_problem()


def test_auto_login_off_or_without_password_is_named(monkeypatch):
    monkeypatch.setattr(server, "load_login", lambda: {"enabled": False, "user": "", "password": ""})
    assert "Auto login is off" in server.auto_login_problem()
    monkeypatch.setattr(server, "load_login", lambda: {"enabled": True, "user": "hero", "password": ""})
    assert "no username/password" in server.auto_login_problem()
    monkeypatch.setattr(server, "load_login", lambda: {"enabled": True, "user": "hero", "password": "pw"})
    monkeypatch.setattr(server, "_login_why", None)
    assert server.auto_login_problem() is None
