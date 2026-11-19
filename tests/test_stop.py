"""Stop: a waiting video stops at once, a running one at its next step, and either can then be deleted."""
import os, sys, tempfile, threading, time
os.environ["HOOKREEL_DATA"] = tempfile.mkdtemp(prefix="hr-stop-")
os.environ["DATABASE_URL"] = ""
sys.path.insert(0, ".")
from studio import auth, ctx, db, jobs
db.init()
fails = []
def check(n, ok, got=None):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

uid = auth.local_user().id if hasattr(auth.local_user(), "id") else auth.local_user()["id"]
tok = ctx._uid.set(uid)
src = {"type": "url", "url": "https://www.youtube.com/watch?v=x", "name": "x"}
a = jobs.create(src, {}, enqueue=False)
jobs.request_stop(a["id"])
check("a waiting video stops at once", a["status"] == "error" and a["error"] == jobs.STOPPED, a["status"])
try:
    jobs.request_stop(a["id"]); check("stopping it twice is refused", False)
except ValueError:
    check("stopping it twice is refused", True)

# a running video: its next progress update ends the work
b = jobs.create(src, {}, enqueue=False)
jobs._set(b, status="running", stage="Writing the transcript")
jobs.request_stop(b["id"])
try:
    jobs._set(b, stage="next step"); check("the next step of a stopped video raises Stopped", False)
except jobs.Stopped:
    check("the next step of a stopped video raises Stopped", True)
jobs._mark_stopped(b)
check("then it shows as stopped, not running", b["status"] == "error" and "stopped" in b["error"].lower(), b["status"])
check("and the stop flag is cleared", "stop" not in b)
ctx._uid.reset(tok)
sys.exit(1 if fails else 0)
