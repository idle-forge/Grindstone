"""Phone notifications through ntfy (https://ntfy.sh): free, no account - install the ntfy app,
subscribe to your topic, and Grindstone pushes a message when something needs you.

Only status text is sent (what stopped and why, levels, run totals) - never the game login or
anything from configs/. The topic name works like a password: anyone who knows it can read the
messages, so keep the random one the panel makes up.

Settings live in configs/notify.json (this PC only)."""
import json
import logging
import re
import secrets
import threading
import time
import urllib.request
from pathlib import Path

FILE = Path(__file__).resolve().parent / "configs" / "notify.json"
DEFAULT_SERVER = "https://ntfy.sh"
SEND_TIMEOUT_S = 10
COOLDOWN_S = 30 * 60               # the same kind of problem at most this often
WATCH_S = 5

DEFAULTS = {
    "enabled": False,
    "server": DEFAULT_SERVER,
    "topic": "",                   # made up on first load: grindstone-<random>
    "click": "",                   # opened when the notification is tapped (the panel's Tailscale address)
    "stopped": True,               # the bot / plan stopped on its own (not when you press Stop)
    "problems": True,              # gave up recovering, game frozen, auto login paused, window minimized
    "levels": True,                # a skill levelled up
    "summary_hours": 0,            # a progress summary every N hours while running (0 = off)
}

# log lines worth a ping: (regex, title, priority) - priority 1..5 as ntfy has them
PROBLEMS = [
    (r"Giving up after", "Grindstone gave up on a step", 4),
    (r"frozen for", "The game froze - restarting it", 4),
    (r"Auto login paused", "Auto login paused", 4),
    (r"Waiting for the game to be up and logged in - ", "Logged out - the bot is waiting to log in", 4),
    (r"Auto login is waiting for the login screen", "Auto login can't log in yet", 3),
    (r"Login didn't go through", "Login problem", 3),
    (r"window is minimized", "The game window is minimized - the bot is waiting", 3),
    (r"Died \d+ times", "Your character keeps dying", 4),
    (r"Couldn't resume", "Couldn't resume after a restart", 4),
    (r"The game didn't answer", "The game isn't answering", 4),
]
# ended on purpose - you already know
USER_STOPS = ("stopped from control panel", "stopped from the control panel", "F12 pressed")


def load():
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    cfg = {**DEFAULTS, **{k: v for k, v in d.items() if k in DEFAULTS}}
    if not cfg["topic"]:
        cfg["topic"] = "grindstone-" + secrets.token_hex(6)
        save(cfg)
    return cfg


def save(cfg):
    cfg = {**DEFAULTS, **{k: v for k, v in cfg.items() if k in DEFAULTS}}
    cfg["server"] = (cfg["server"] or DEFAULT_SERVER).strip().rstrip("/")
    cfg["topic"] = re.sub(r"[^A-Za-z0-9_-]", "", cfg["topic"] or "")[:64]
    cfg["click"] = (cfg["click"] or "").strip()
    try:
        cfg["summary_hours"] = max(0.0, float(cfg["summary_hours"] or 0))
    except (TypeError, ValueError):
        cfg["summary_hours"] = 0
    try:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except OSError:
        pass
    return cfg


def _ascii(s):
    """HTTP headers must be plain text: drop what isn't."""
    return s.encode("ascii", "ignore").decode().strip()


def send(title, message, priority=3, tags=(), cfg=None, wait=False):
    """Push one notification. Never raises; returns an error text or None (wait=True)."""
    cfg = cfg or load()
    if not cfg["topic"]:
        return "no topic set"
    url = f"{cfg['server']}/{cfg['topic']}"
    headers = {"Title": _ascii(title) or "Grindstone", "Priority": str(priority)}
    if tags:
        headers["Tags"] = ",".join(tags)
    if cfg["click"]:
        headers["Click"] = _ascii(cfg["click"])
    req = urllib.request.Request(url, data=message.encode("utf-8"), headers=headers, method="POST")

    def go():
        try:
            urllib.request.urlopen(req, timeout=SEND_TIMEOUT_S).close()
            return None
        except Exception as e:                     # no internet, ntfy down: never hurt the bot
            logging.getLogger("notify").debug("send failed: %s", e)
            return str(e)

    if wait:
        return go()
    threading.Thread(target=go, name="notify-send", daemon=True).start()
    return None


class ProblemHandler(logging.Handler):
    """Watches the log for lines that need you (PROBLEMS) and pushes them, at most once per
    COOLDOWN_S for each kind."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.last = {}
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record):
        try:
            if record.name in ("notify", "uvicorn", "uvicorn.error", "uvicorn.access"):
                return
            msg = self.format(record)
            for pat, title, prio in PROBLEMS:
                if re.search(pat, msg):
                    cfg = load()
                    now = time.monotonic()
                    if not (cfg["enabled"] and cfg["problems"]) or now - self.last.get(pat, -1e9) < COOLDOWN_S:
                        return
                    self.last[pat] = now
                    send(title, msg, prio, ("warning",), cfg)
                    return
        except Exception:
            pass


def _dur(s):
    s = int(s)
    return f"{s // 3600}h {s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60} min"


def summary_text(st):
    """'1,244 fish (242/hr) · 1,154 cooked · 72 burnt · 5h 08m' + XP lines, from ctl.status()."""
    bits = []
    if st.get("logs"):
        bits.append(f"{st['logs']:,} done" + (f" ({st['per_hour']:,}/hr)" if st.get("per_hour") else ""))
    for k, label in (("cooked", "cooked"), ("burnt", "burnt"), ("banked", "bank trips"), ("eaten", "eaten")):
        if st.get(k):
            bits.append(f"{st[k]:,} {label}")
    if st.get("elapsed"):
        bits.append(_dur(st["elapsed"]))
    lines = [" · ".join(bits)] if bits else []
    for sk, v in (st.get("xp") or {}).items():
        if v.get("gained"):
            up = f" (+{v['levels_gained']})" if v.get("levels_gained") else ""
            lines.append(f"{sk.capitalize()} {v['level']}{up}: +{v['gained']:,} xp")
    ss = st.get("session") or {}
    if ss.get("recoveries"):
        lines.append(f"Recovered {ss['recoveries']}x" + (f" - last: {ss['last_problem']}" if ss.get("last_problem") else ""))
    return "\n".join(lines) or "No progress yet"


class Watcher:
    """Polls the controller's status: the bot stopping, level-ups and the periodic summary."""

    def __init__(self, status, running):
        self.status, self.running = status, running      # callables (ctl.status, lambda: ctl.running)
        self.was_running = False
        self.levels = {}
        self.next_summary = None

    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        cfg = load()
        running = self.running()
        if not cfg["enabled"]:
            self.was_running, self.levels, self.next_summary = running, {}, None
            return
        st = self.status()
        task = (st.get("task") or "the bot").capitalize()
        if self.was_running and not running and cfg["stopped"]:
            why = st.get("stop_reason") or st.get("error") or "it ended"
            if not any(why.startswith(u) for u in USER_STOPS) and not st.get("updating"):
                good = bool(re.search(r"finished|time limit|reached|\bdone\b", why, re.I))
                send(f"{task} stopped: {why}"[:120], summary_text(st), 3 if good else 4,
                     ("checkered_flag",) if good else ("rotating_light",), cfg)
        if running and cfg["levels"]:
            for sk, v in (st.get("xp") or {}).items():
                lv = v.get("level")
                old = self.levels.get(sk)
                if old is not None and lv and lv > old:
                    send(f"{sk.capitalize()} level {lv}!", summary_text(st), 2, ("tada",), cfg)
                if lv:
                    self.levels[sk] = lv
        elif not running:
            self.levels = {}
        hours = cfg["summary_hours"]
        if running and hours:
            if self.next_summary is None:
                self.next_summary = now + hours * 3600
            elif now >= self.next_summary:
                self.next_summary = now + hours * 3600
                send(f"{task}: still going", summary_text(st), 2, ("fishing_pole_and_fish",)
                     if st.get("task") == "fishing" else ("hourglass",), cfg)
        else:
            self.next_summary = None
        self.was_running = running

    def loop(self):
        while True:
            time.sleep(WATCH_S)
            try:
                self.tick()
            except Exception:
                logging.getLogger("notify").debug("watcher failed", exc_info=True)


def start(status, running):
    """Hook up the log watcher and the status watcher (call once, from the panel)."""
    logging.getLogger().addHandler(ProblemHandler())
    w = Watcher(status, running)
    threading.Thread(target=w.loop, name="notify", daemon=True).start()
    return w
