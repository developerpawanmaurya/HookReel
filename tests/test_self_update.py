"""'Update now': the button leaves a request for the server's helper, reports its progress, and only for an admin."""
import json, os, sys, tempfile, types
os.environ["HOOKREEL_DATA"] = tempfile.mkdtemp(prefix="hr-upd-")
os.environ["DATABASE_URL"] = ""
host = tempfile.mkdtemp(prefix="hr-hostctl-")
os.environ["HOOKREEL_HOSTCTL"] = host
sys.path.insert(0, ".")
from pathlib import Path
from fastapi import HTTPException
from studio import ctx, server
ctx._uid.set("u_a")
fails = []
def check(n, ok, got=None):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

admin = types.SimpleNamespace(state=types.SimpleNamespace(user=types.SimpleNamespace(is_admin=True, disabled=False, id="u_a")))
other = types.SimpleNamespace(state=types.SimpleNamespace(user=types.SimpleNamespace(is_admin=False, disabled=False, id="u_b")))
check("progress answers before the helper is installed", server.update_get(admin)["state"] == "")
try:
    server.update_post(admin); check("without the helper, Update now is refused", False)
except HTTPException as e:
    check("without the helper, Update now is refused", e.status_code == 400, e.status_code)
Path(host, "updater").touch()
r = server.update_post(admin)
check("with the helper, it leaves a request", r["state"] == "requested" and Path(host, "update-requested").is_file(), r)
check("and shows as requested", server.update_get(admin)["state"] == "requested")
Path(host, "update-requested").unlink()
Path(host, "update-status").write_text(json.dumps({"state": "failed", "at": 1, "code": 1}))
Path(host, "update.log").write_text("git pull failed")
g = server.update_get(admin)
check("a failed update is reported with its log", g["state"] == "failed" and "git pull failed" in g["log"], g)
try:
    server.update_get(other); check("someone who is not an admin can't see it", False)
except HTTPException as e:
    check("someone who is not an admin can't see it", e.status_code == 404, e.status_code)
sys.exit(1 if fails else 0)
