"""A private server: HOOKREEL_ALLOWED_EMAILS closes sign-up to everyone except the listed addresses, for both
email and Google sign-up. Runs against the code directly, with its own empty data folder."""
import os, sys, tempfile
os.environ["HOOKREEL_DATA"] = tempfile.mkdtemp(prefix="hr-allow-")
os.environ.update(DATABASE_URL="", HOOKREEL_ALLOWED_EMAILS=" Owner@Example.com , second@example.com")
sys.path.insert(0, ".")
from studio import auth, config, db
db.init()
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

check("the list is read without spaces or capitals", config.ALLOWED_EMAILS, {"owner@example.com", "second@example.com"})
u, _ = auth.signup("OWNER@example.com", "a-long-enough-password-1")
check("a listed address can sign up, whatever its capitals", u.email, "owner@example.com")
for who, how in (("stranger@example.com", lambda e: auth.signup(e, "a-long-enough-password-1")),
                 ("google-stranger@example.com", lambda e: auth._create(e, "G", google_sub="123"))):
    try:
        how(who); check(f"{who} is refused", False)
    except auth.AuthError as e:
        check(f"{who} is refused, with a plain message", "closed" in str(e))
sys.exit(1 if fails else 0)
