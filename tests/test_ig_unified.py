"""Instagram with Meta's Unified login (newer Meta apps): the Facebook dialog with the configuration, the token
exchange at graph.facebook.com, the account found from the grant, and posts going to graph.facebook.com."""
import os, sys, tempfile
from urllib.parse import urlparse, parse_qs
os.environ["HOOKREEL_DATA"] = tempfile.mkdtemp(prefix="hr-igu-")
os.environ.update(DATABASE_URL="", HOOKREEL_PUBLIC_URL="https://hr.example.com")
sys.path.insert(0, ".")
from studio import accounts, auth, ctx, db
db.init()
fails = []
def check(n, ok, got=None):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

tok = ctx._uid.set(auth.local_user().id)
accounts.save_app("instagram", "1451739650425751", "s3cret", "987654321")
check("the configuration id is saved with the app", accounts.ig_config_id() == "987654321")
check("and shown to the setup panel, never the secret", accounts.apps_public()["instagram"]["config_hint"] == "987654321"
      and "s3cret" not in str(accounts.apps_public()))
q = parse_qs(urlparse(accounts.connect_url("instagram")).query)
check("Connect opens Facebook's dialog with the configuration", accounts.connect_url("instagram").startswith(
      "https://www.facebook.com/") and q.get("config_id") == ["987654321"] and "scope" not in q, q)

class R:
    def __init__(s, data, code=200): s._d, s.status_code, s.text = data, code, str(data)
    def json(s): return s._d
calls = []
def fake_get(url, params=None, **k):
    calls.append(url)
    if url.endswith("/oauth/access_token"): return R({"access_token": "SYS"})
    if url.endswith("/me/assigned_instagram_accounts"): return R({"data": []})
    if url.endswith("/debug_token"):
        return R({"data": {"granular_scopes": [{"scope": "instagram_basic", "target_ids": ["111", "17841400000000001"]},
                                               {"scope": "instagram_content_publish", "target_ids": ["17841400000000001"]}]}})
    if url.endswith("/17841400000000001"): return R({"id": "17841400000000001", "username": "gamingclipsindia"})
    return R({"error": {"message": "unsupported"}}, 400)
accounts.httpx.get = fake_get
acc = accounts._instagram_finish("CODE")
check("the Instagram account is found from the grant", acc["name"] == "@gamingclipsindia" and acc["user_id"] == "17841400000000001", acc)
check("it posts through graph.facebook.com", acc["graph"] == accounts.FB)
check("the code is exchanged at graph.facebook.com", any("graph.facebook.com" in c and "oauth/access_token" in c for c in calls))
check("its token is kept as it is (system-user tokens do not run out)", accounts._ig_token(acc) == "SYS")
accounts.save_app("instagram", "1451739650425751", "", "")
check("emptying the configuration goes back to Instagram login", accounts.ig_config_id() == "" and
      accounts.connect_url("instagram").startswith("https://www.instagram.com/"))
ctx._uid.reset(tok)
sys.exit(1 if fails else 0)
