from flask import Flask, request, jsonify, redirect, session, render_template_string
import os, sqlite3, hashlib, json, urllib.request, urllib.error
from datetime import datetime

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") == "1",
)

# Existing key-manager site. This settings site does NOT create keys; it only
# checks that the key exists/is active, then stores preferences for that key.
KEY_VERIFY_URL = os.environ.get(
    "KEY_VERIFY_URL",
    "https://key-manager-o3df.onrender.com/verify",
).strip()

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SQLITE_PATH = os.environ.get("SQLITE_PATH", "cheto_settings.db")
ALLOWED_LANGUAGES = {"en", "es", "ar"}


class DBConnection:
    def __init__(self, con, postgres=False):
        self._con = con
        self.postgres = postgres

    def execute(self, sql, params=()):
        if self.postgres:
            cur = self._con.cursor()
            cur.execute(sql.replace("?", "%s"), params)
            return cur
        return self._con.execute(sql, params)

    def commit(self):
        return self._con.commit()

    def close(self):
        return self._con.close()


def db():
    if DATABASE_URL:
        if psycopg is None:
            raise RuntimeError("Install psycopg[binary] when using DATABASE_URL")
        con = DBConnection(psycopg.connect(DATABASE_URL, row_factory=dict_row), True)
    else:
        raw = sqlite3.connect(SQLITE_PATH)
        raw.row_factory = sqlite3.Row
        con = DBConnection(raw, False)

    con.execute(
        """CREATE TABLE IF NOT EXISTS key_settings(
            key_hash TEXT PRIMARY KEY,
            language TEXT NOT NULL DEFAULT 'en',
            updated TEXT NOT NULL
        )"""
    )
    con.commit()
    return con


def normalize_key(value):
    return str(value or "").strip().upper()


def key_hash(key):
    return hashlib.sha256(normalize_key(key).encode("utf-8")).hexdigest()


def mask_key(key):
    key = normalize_key(key)
    if len(key) <= 6:
        return key[:1] + "••••" + key[-1:]
    return key[:3] + "••••••" + key[-3:]


def verify_key_remote(key):
    """Validate against the existing key-manager without binding a new device."""
    payload = json.dumps({"key": normalize_key(key)}).encode("utf-8")
    req = urllib.request.Request(
        KEY_VERIFY_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Cheto-Settings/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8", "replace")
            data = json.loads(body or "{}")
            return bool(data.get("valid")), str(data.get("reason", ""))
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8", "replace") or "{}")
            return bool(data.get("valid")), str(data.get("reason", "http_error"))
        except Exception:
            return False, "http_error"
    except Exception:
        return False, "connection_error"


def get_settings_by_hash(kh):
    con = db()
    row = con.execute(
        "SELECT language, updated FROM key_settings WHERE key_hash=?",
        (kh,),
    ).fetchone()
    con.close()
    if not row:
        return {"language": "en", "updated": ""}
    return {"language": row["language"], "updated": row["updated"]}


def save_settings_by_hash(kh, language):
    language = language if language in ALLOWED_LANGUAGES else "en"
    now = datetime.utcnow().isoformat()
    con = db()
    if con.postgres:
        con.execute(
            """INSERT INTO key_settings(key_hash,language,updated)
               VALUES(?,?,?)
               ON CONFLICT(key_hash) DO UPDATE SET language=EXCLUDED.language, updated=EXCLUDED.updated""",
            (kh, language, now),
        )
    else:
        con.execute(
            """INSERT INTO key_settings(key_hash,language,updated)
               VALUES(?,?,?)
               ON CONFLICT(key_hash) DO UPDATE SET language=excluded.language, updated=excluded.updated""",
            (kh, language, now),
        )
    con.commit()
    con.close()
    return now


LOGIN_HTML = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cheto Settings</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#03050a;color:#f7f8fc;font-family:Arial,sans-serif;background-image:radial-gradient(circle at 20% 10%,#5f3dff22,transparent 30%),radial-gradient(circle at 85% 85%,#1a8bff17,transparent 30%)}
.card{width:min(480px,92vw);padding:30px;border:1px solid #20283a;border-radius:24px;background:#080b12eF;box-shadow:0 26px 80px #000b,0 0 60px #684dff14;backdrop-filter:blur(18px)}
.badge{display:inline-flex;gap:7px;align-items:center;padding:7px 10px;border:1px solid #27513f;border-radius:999px;color:#64e9a8;background:#071a13;font-size:10px;font-weight:900}.dot{width:6px;height:6px;border-radius:50%;background:#59eaa2;box-shadow:0 0 12px #59eaa2}
h1{font-size:31px;margin:18px 0 8px}.sub{color:#7e899e;font-size:13px;line-height:1.6;margin:0 0 20px}.err{padding:11px 12px;margin-bottom:12px;border:1px solid #642033;border-radius:12px;background:#280b13;color:#ff8194;font-size:12px}
input,button{width:100%;height:54px;border-radius:14px;font-size:14px}input{border:1px solid #293248;background:#04070d;color:#fff;padding:0 16px;outline:none}input:focus{border-color:#735cff;box-shadow:0 0 0 4px #735cff16}button{margin-top:12px;border:0;color:white;font-weight:900;cursor:pointer;background:linear-gradient(90deg,#5f46ff,#a83bf3,#3282ff);box-shadow:0 12px 30px #6a4cff30}.foot{margin-top:15px;color:#58657b;font-size:10px}
</style></head><body><main class="card"><span class="badge"><i class="dot"></i>KEY SETTINGS ONLINE</span><h1>Settings Browser</h1><p class="sub">Enter the same activation key you used inside Lua. Your settings are stored only for that key.</p>{% if error %}<div class="err">{{error}}</div>{% endif %}<form method="post"><input name="key" placeholder="Activation Key" autocomplete="off" required autofocus><button>CONTINUE</button></form><div class="foot">Cheto-C • Per-key settings</div></main></body></html>
"""


HOME_HTML = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cheto Settings</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:#03050a;color:#f7f8fc;font-family:Arial,sans-serif;background-image:radial-gradient(circle at 12% 5%,#6546ff22,transparent 28%),radial-gradient(circle at 90% 90%,#168cff18,transparent 28%)}
.wrap{width:min(760px,94vw);margin:45px auto}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.eyebrow{color:#7d879b;font-size:10px;letter-spacing:2px}.title{font-size:28px;font-weight:900;margin-top:5px}.key{font:800 11px monospace;color:#b5bfd2;border:1px solid #273149;background:#070b13;border-radius:999px;padding:8px 11px}
.card{border:1px solid #20283a;border-radius:24px;background:#080b12ed;box-shadow:0 28px 90px #0009;overflow:hidden}.head{padding:24px 25px;border-bottom:1px solid #182132}.head h2{margin:0 0 6px}.head p{margin:0;color:#78859b;font-size:12px}.body{padding:25px}
.langs{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.choice{position:relative}.choice input{position:absolute;opacity:0}.choice label{display:block;padding:18px;border:1px solid #283249;border-radius:15px;background:#060a11;cursor:pointer;transition:.2s}.choice label b{display:block;font-size:15px}.choice label span{display:block;color:#79869d;font-size:10px;margin-top:5px}.choice input:checked+label{border-color:#765cff;background:#171333;box-shadow:0 0 25px #765cff23;transform:translateY(-2px)}
.save{width:100%;height:55px;margin-top:18px;border:0;border-radius:14px;color:white;font-weight:900;cursor:pointer;background:linear-gradient(90deg,#603fff,#a638f1,#347fff)}.ok{margin-bottom:15px;padding:11px 12px;border:1px solid #1d5d42;border-radius:12px;background:#071d15;color:#66edab;font-size:12px}.note{margin-top:15px;color:#6e7b90;font-size:11px;line-height:1.55}.logout{color:#8e99ad;text-decoration:none;font-size:12px}@media(max-width:600px){.langs{grid-template-columns:1fr}.wrap{margin:24px auto}}
</style></head><body><div class="wrap"><div class="top"><div><div class="eyebrow">CHETO // REMOTE SETTINGS</div><div class="title">Settings Browser</div></div><div><span class="key">{{mask}}</span> &nbsp; <a class="logout" href="/logout">Logout</a></div></div><main class="card"><section class="head"><h2>Language</h2><p>Choose a language, press Save, then return to the game and press “Download settings”.</p></section><section class="body">{% if saved %}<div class="ok">✓ Settings saved for this key.</div>{% endif %}<form method="post"><div class="langs"><div class="choice"><input id="en" type="radio" name="language" value="en" {% if language=='en' %}checked{% endif %}><label for="en"><b>English</b><span>Default interface language</span></label></div><div class="choice"><input id="es" type="radio" name="language" value="es" {% if language=='es' %}checked{% endif %}><label for="es"><b>Español</b><span>Spanish interface</span></label></div><div class="choice"><input id="ar" type="radio" name="language" value="ar" {% if language=='ar' %}checked{% endif %}><label for="ar"><b>العربية</b><span>Arabic interface</span></label></div></div><button class="save">SAVE SETTINGS</button></form><div class="note">Saving here does not immediately change Lua. The change is applied only when you press <b>Download settings</b> inside the menu.</div></section></main></div></body></html>
"""


def login_error(reason):
    reason = str(reason or "")
    if reason in {"inactive", "expired", "disabled"}:
        return "Key expired or stopped."
    if reason == "server_offline":
        return "Key server is currently off."
    if reason == "rate_limited":
        return "Too many attempts. Try again shortly."
    if reason == "connection_error":
        return "Could not reach the key server."
    return "Invalid activation key."


@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        key = normalize_key(request.form.get("key", ""))
        if not key:
            error = "Enter your activation key."
        else:
            valid, reason = verify_key_remote(key)
            if valid:
                session.clear()
                session["key_hash"] = key_hash(key)
                session["key_mask"] = mask_key(key)
                return redirect("/home")
            error = login_error(reason)
    return render_template_string(LOGIN_HTML, error=error)


@app.route("/home", methods=["GET", "POST"])
def home():
    kh = session.get("key_hash")
    if not kh:
        return redirect("/")

    saved = False
    if request.method == "POST":
        language = str(request.form.get("language", "en")).lower()
        if language not in ALLOWED_LANGUAGES:
            language = "en"
        save_settings_by_hash(kh, language)
        saved = True

    settings = get_settings_by_hash(kh)
    return render_template_string(
        HOME_HTML,
        language=settings["language"],
        mask=session.get("key_mask", "KEY"),
        saved=saved,
    )


@app.route("/api/settings", methods=["POST"])
def api_settings():
    data = request.get_json(silent=True) or {}
    key = normalize_key(data.get("key", ""))
    if not key:
        return jsonify(ok=False, reason="invalid_key"), 400

    valid, reason = verify_key_remote(key)
    if not valid:
        return jsonify(ok=False, reason=reason or "invalid_key"), 403

    settings = get_settings_by_hash(key_hash(key))
    return jsonify(
        ok=True,
        language=settings["language"],
        updated=settings["updated"],
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/health")
def health():
    try:
        con = db()
        con.execute("SELECT 1").fetchone()
        con.close()
        return jsonify(ok=True, database=True), 200
    except Exception as exc:
        return jsonify(ok=False, database=False, error=str(exc)[:120]), 503


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    return resp


if __name__ == "__main__":
    db().close()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
