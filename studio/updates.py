"""Is there a newer HookReel? Compares the version running here with the latest on GitHub, once a minute.

The version here is the git commit this folder was on when HookReel started (read straight from .git, no git
program needed). Each minute, in the background, HookReel asks GitHub which commit the project is on now: one small
request to the same address `git` itself uses, which has no hourly allowance to run out of. Only when that commit
changes does it ask GitHub's API what was added, to show the list. Nothing about this computer or its users is
sent. The owner sees a notice in the dashboard within a minute or two, with no restart.

    HOOKREEL_UPDATE_REPO     where to look (default: the project's own repository; a fork points at itself)
    HOOKREEL_UPDATE_BRANCH   which branch (default: main)
    HOOKREEL_UPDATE_CHECK=0  never look"""
import json
import re
import threading
import time
from pathlib import Path

import httpx

from . import config

REPO = (config.env("HOOKREEL_UPDATE_REPO") or "developerpawanmaurya/HookReel").strip().strip("/")
BRANCH = (config.env("HOOKREEL_UPDATE_BRANCH") or "main").strip()
ON = config.env("HOOKREEL_UPDATE_CHECK", "1") != "0" and bool(re.fullmatch(r"[\w.\-]+/[\w.\-]+", REPO))
EVERY = 60
UA = {"User-Agent": "HookReel-update-check"}
_state = {"checked": 0.0, "result": None, "seen": "", "notes": None}
_lock = threading.Lock()
_started = False


def current() -> str:
    """The commit this folder is on now, or "" when it was not installed with git (a downloaded zip, for example)."""
    g = config.ROOT / ".git"
    try:
        if g.is_file():                      # a worktree or submodule: .git points somewhere else
            g = (config.ROOT / g.read_text(encoding="utf-8").split(":", 1)[1].strip()).resolve()
        head = (g / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            return head if re.fullmatch(r"[0-9a-f]{40}", head) else ""
        ref = head.split(":", 1)[1].strip()
        f = g / ref
        if f.is_file():
            return f.read_text(encoding="utf-8").strip()
        packed = g / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0]
    except (OSError, IndexError):
        pass
    return ""


RUNNING = current()       # the code in memory: what HookReel is actually running until it is restarted


def newest() -> str:
    """The commit the project is on right now, from the address git itself asks. "" if it cannot be told."""
    r = httpx.get(f"https://github.com/{REPO}.git/info/refs", params={"service": "git-upload-pack"}, headers=UA, timeout=15)
    if r.status_code != 200:
        return ""                            # a private repository, or GitHub is having a moment
    m = re.search(rb"([0-9a-f]{40}) refs/heads/" + re.escape(BRANCH).encode() + rb"[\x00\n]", r.content)
    return m.group(1).decode() if m else ""


def _what_changed(here: str):
    """(how many commits newer, their first lines, newest first), or None if GitHub's API will not say right now."""
    r = httpx.get(f"https://api.github.com/repos/{REPO}/compare/{here}...{BRANCH}", timeout=20,
                  headers={"Accept": "application/vnd.github+json", **UA})
    if r.status_code != 200:
        return None
    d = r.json()
    notes = []
    for c in reversed(d.get("commits") or []):
        msg = str((c.get("commit") or {}).get("message") or "").strip().splitlines()
        notes.append({"sha": str(c.get("sha") or "")[:7], "title": (msg[0] if msg else "")[:140],
                      "date": str(((c.get("commit") or {}).get("committer") or {}).get("date") or "")[:10]})
    return int(d.get("ahead_by") or 0), notes[:20]


def check(force: bool = False):
    """Look once. Returns what the dashboard should say, or None when this copy is up to date (or it cannot be told)."""
    if not ON:
        return None
    with _lock:
        now = time.time()
        if not force and now - _state["checked"] < EVERY:
            return _state["result"]
        _state["checked"] = now
        here, on_disk = RUNNING, current()
        try:
            top = newest() if here else ""
        except Exception:  # noqa: BLE001 - offline: what was known stays, and it is asked again in a minute
            return _state["result"]
        if not top or top == here:
            _state.update(result=None, seen=top)
            return None
        if top != _state["seen"] or _state["notes"] is None:      # a commit not seen before: ask what it brought, once
            _state["seen"] = top
            try:
                _state["notes"] = _what_changed(here)
            except Exception:  # noqa: BLE001
                _state["notes"] = None
        got = _state["notes"]
        if got and got[0] == 0:
            _state["result"] = None          # this copy has its own newer commits: nothing to fetch
            return None
        _state["result"] = {"current": here[:7], "latest": top[:7], "behind": got[0] if got else None,
                            "notes": got[1] if got else [], "url": f"https://github.com/{REPO}/commits/{BRANCH}",
                            # the new files are already in the folder (git pull was run): only a restart is left
                            "restart": on_disk == top}
        return _state["result"]


def latest():
    """For the pages: what the last look found. Never waits on GitHub."""
    r = _state["result"] if ON else None
    return dict(r, self_update=can_self_update()) if r else None


# ---------------------------------------------------------------- one-click updates on a server
# deploy/oracle-update.sh installs a small helper on the server itself (a systemd path unit). It watches the folder
# mounted here at /hostctl: when HookReel drops a request file in it, the server pulls the newest version from GitHub
# and rebuilds, outside this container, so the update carries on while HookReel restarts. The request file holds
# nothing but a time: what runs is always deploy/self-update.sh from the project, never anything sent from here.
HOSTCTL = Path(config.env("HOOKREEL_HOSTCTL") or "/hostctl")


def can_self_update() -> bool:
    return (HOSTCTL / "updater").is_file()


def request_update() -> dict:
    if not can_self_update():
        raise ValueError("This server can't update itself yet. Run the update command on the server once to turn it on.")
    st = progress()
    if st.get("state") in ("requested", "running") and time.time() - float(st.get("at") or 0) < 1800:
        return st
    (HOSTCTL / "update-requested").write_text(str(int(time.time())), encoding="utf-8")
    return {"state": "requested", "at": time.time()}


def progress() -> dict:
    """What the server's updater last said: requested, running, done or failed, with the end of its log."""
    out = {"state": "", "at": 0, "running": RUNNING[:7]}
    try:
        out.update(json.loads((HOSTCTL / "update-status").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    if (HOSTCTL / "update-requested").is_file() and out.get("state") != "running":
        out["state"] = "requested"
    try:
        out["log"] = (HOSTCTL / "update.log").read_text(encoding="utf-8", errors="replace")[-1500:]
    except OSError:
        out["log"] = ""
    return out


def start():
    """Look every minute, in the background, for as long as HookReel runs."""
    global _started
    if not ON or _started:
        return
    _started = True

    def loop():
        while True:
            try:
                check()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(EVERY)
    threading.Thread(target=loop, daemon=True).start()
