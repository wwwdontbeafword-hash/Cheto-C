from flask import Flask, request, jsonify, redirect, session, render_template_string
import os, sqlite3, hashlib, json, urllib.request, urllib.error, secrets
from datetime import datetime, timedelta

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
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

KEY_VERIFY_URL = os.environ.get(
    "KEY_VERIFY_URL",
    "https://key-manager-o3df.onrender.com/verify",
).strip()
PUBLIC_BASE_URL = os.environ.get(
    "PUBLIC_BASE_URL",
    "https://cheto-c.onrender.com",
).strip().rstrip("/")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SQLITE_PATH = os.environ.get("SQLITE_PATH", "cheto_settings.db")
ALLOWED_LANGUAGES = {"en", "es", "ar"}
LAUNCH_TOKEN_SECONDS = int(os.environ.get("LAUNCH_TOKEN_SECONDS", "90"))


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
    con.execute(
        """CREATE TABLE IF NOT EXISTS launch_tokens(
            token_hash TEXT PRIMARY KEY,
            key_hash TEXT NOT NULL,
            key_mask TEXT NOT NULL,
            key_value TEXT NOT NULL,
            device_id TEXT NOT NULL,
            expires TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            created TEXT NOT NULL
        )"""
    )
    con.commit()
    return con


def normalize_key(value):
    return str(value or "").strip().upper()


def clean_device_id(value):
    return str(value or "").strip()


def sha256(value):
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def key_hash(key):
    return sha256(normalize_key(key))


def mask_key(key):
    key = normalize_key(key)
    if len(key) <= 6:
        return key[:1] + "••••" + key[-1:]
    return key[:3] + "••••••" + key[-3:]


def verify_key_remote(key, device_id):
    key = normalize_key(key)
    device_id = clean_device_id(device_id)
    if not key or not device_id:
        return False, "missing_credentials"

    payload = json.dumps({"key": key, "device_id": device_id}).encode("utf-8")
    req = urllib.request.Request(
        KEY_VERIFY_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Cheto-Settings/2.0",
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


def create_launch_token(key, device_id):
    raw_token = secrets.token_urlsafe(32)
    token_hash = sha256(raw_token)
    now = datetime.utcnow()
    expires = now + timedelta(seconds=max(30, LAUNCH_TOKEN_SECONDS))

    con = db()
    # Keep the table small.
    con.execute("DELETE FROM launch_tokens WHERE expires<? OR used=1", (now.isoformat(),))
    con.execute(
        """INSERT INTO launch_tokens(
            token_hash,key_hash,key_mask,key_value,device_id,expires,used,created
        ) VALUES(?,?,?,?,?,?,0,?)""",
        (
            token_hash,
            key_hash(key),
            mask_key(key),
            normalize_key(key),
            clean_device_id(device_id),
            expires.isoformat(),
            now.isoformat(),
        ),
    )
    con.commit()
    con.close()
    return raw_token


def consume_launch_token(raw_token):
    raw_token = str(raw_token or "").strip()
    if not raw_token:
        return None

    now = datetime.utcnow()
    con = db()
    row = con.execute(
        "SELECT * FROM launch_tokens WHERE token_hash=? AND used=0",
        (sha256(raw_token),),
    ).fetchone()
    if not row:
        con.close()
        return None

    try:
        expires = datetime.fromisoformat(row["expires"])
    except Exception:
        expires = now - timedelta(seconds=1)

    if now > expires:
        con.execute("DELETE FROM launch_tokens WHERE token_hash=?", (sha256(raw_token),))
        con.commit()
        con.close()
        return None

    con.execute("UPDATE launch_tokens SET used=1 WHERE token_hash=?", (sha256(raw_token),))
    con.commit()
    data = dict(row)
    con.close()
    return data


ACCESS_DENIED_HTML = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Access Denied</title><style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#03050a;color:#f7f8fc;font-family:Arial,sans-serif;background-image:radial-gradient(circle at 50% 20%,#7d244522,transparent 34%)}
.card{width:min(460px,92vw);padding:30px;border:1px solid #4d1f2b;border-radius:24px;background:#09080ded;box-shadow:0 28px 90px #000c;text-align:center}.icon{width:60px;height:60px;margin:auto;border-radius:18px;display:grid;place-items:center;border:1px solid #6b2636;background:#260b12;color:#ff627b;font-size:28px;box-shadow:0 0 28px #ff36552b}h1{font-size:28px;margin:18px 0 8px}.sub{color:#8a8794;font-size:13px;line-height:1.6;margin:0}.hint{margin-top:18px;color:#5f6572;font-size:10px}
</style></head><body><main class="card"><div class="icon">×</div><h1>Access Denied</h1><p class="sub">Open Settings Browser from inside the game menu to authorize this browser.</p><div class="hint">Cheto-C • Secure browser handoff</div></main></body></html>
"""


HOME_HTML = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cheto Settings</title><style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:#03050a;color:#f7f8fc;font-family:Arial,sans-serif;background-image:radial-gradient(circle at 12% 5%,#6546ff22,transparent 28%),radial-gradient(circle at 90% 90%,#168cff18,transparent 28%)}
.wrap{width:min(760px,94vw);margin:45px auto}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.eyebrow{color:#7d879b;font-size:10px;letter-spacing:2px}.title{font-size:28px;font-weight:900;margin-top:5px}.key{font:800 11px monospace;color:#b5bfd2;border:1px solid #273149;background:#070b13;border-radius:999px;padding:8px 11px}
.card{border:1px solid #20283a;border-radius:24px;background:#080b12ed;box-shadow:0 28px 90px #0009;overflow:hidden}.head{padding:24px 25px;border-bottom:1px solid #182132}.head h2{margin:0 0 6px}.head p{margin:0;color:#78859b;font-size:12px}.body{padding:25px}
.langs{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.choice{position:relative}.choice input{position:absolute;opacity:0}.choice label{display:block;padding:18px;border:1px solid #283249;border-radius:15px;background:#060a11;cursor:pointer;transition:.2s}.choice label b{display:block;font-size:15px}.choice label span{display:block;color:#79869d;font-size:10px;margin-top:5px}.choice input:checked+label{border-color:#765cff;background:#171333;box-shadow:0 0 25px #765cff23;transform:translateY(-2px)}
.save{width:100%;height:55px;margin-top:18px;border:0;border-radius:14px;color:white;font-weight:900;cursor:pointer;background:linear-gradient(90deg,#603fff,#a638f1,#347fff)}.ok{margin-bottom:15px;padding:11px 12px;border:1px solid #1d5d42;border-radius:12px;background:#071d15;color:#66edab;font-size:12px}.note{margin-top:15px;color:#6e7b90;font-size:11px;line-height:1.55}.logout{color:#8e99ad;text-decoration:none;font-size:12px}@media(max-width:600px){.langs{grid-template-columns:1fr}.wrap{margin:24px auto}}
</style></head><body><div class="wrap"><div class="top"><div><div class="eyebrow">CHETO // REMOTE SETTINGS</div><div class="title">Settings Browser</div></div><div><span class="key">{{mask}}</span> &nbsp; <a class="logout" href="/logout">Logout</a></div></div><main class="card"><section class="head"><h2>Language</h2><p>Choose a language, press Save, then return to the game and press “Download settings”.</p></section><section class="body">{% if saved %}<div class="ok">✓ Settings saved for this key.</div>{% endif %}<form method="post"><div class="langs"><div class="choice"><input id="en" type="radio" name="language" value="en" {% if language=='en' %}checked{% endif %}><label for="en"><b>English</b><span>Default interface language</span></label></div><div class="choice"><input id="es" type="radio" name="language" value="es" {% if language=='es' %}checked{% endif %}><label for="es"><b>Español</b><span>Spanish interface</span></label></div><div class="choice"><input id="ar" type="radio" name="language" value="ar" {% if language=='ar' %}checked{% endif %}><label for="ar"><b>العربية</b><span>Arabic interface</span></label></div></div><button class="save">SAVE SETTINGS</button></form><div class="note">Saving here does not immediately change Lua. The change is applied only when you press <b>Download settings</b> inside the menu.</div></section></main></div></body></html>
"""


def denied():
    return render_template_string(ACCESS_DENIED_HTML), 403


@app.route("/", methods=["GET"])
def root():
    if session.get("authorized") and session.get("key") and session.get("device_id"):
        return redirect("/home")
    return denied()


@app.route("/api/launch", methods=["POST"])
def api_launch():
    data = request.get_json(silent=True) or {}
    key = normalize_key(data.get("key", ""))
    device_id = clean_device_id(data.get("device_id", ""))
    if not key or not device_id:
        return jsonify(ok=False, reason="missing_credentials"), 400

    valid, reason = verify_key_remote(key, device_id)
    if not valid:
        return jsonify(ok=False, reason=reason or "invalid_key"), 403

    token = create_launch_token(key, device_id)
    return jsonify(ok=True, open_url=f"{PUBLIC_BASE_URL}/open?t={token}")


@app.route("/open", methods=["GET"])
def open_from_game():
    row = consume_launch_token(request.args.get("t", ""))
    if not row:
        return denied()

    # Re-check at consumption time so a stopped/expired key cannot use an old token.
    valid, _ = verify_key_remote(row["key_value"], row["device_id"])
    if not valid:
        return denied()

    session.clear()
    session.permanent = True
    session["authorized"] = True
    session["key"] = row["key_value"]
    session["key_hash"] = row["key_hash"]
    session["key_mask"] = row["key_mask"]
    session["device_id"] = row["device_id"]
    return redirect("/home")


@app.route("/home", methods=["GET", "POST"])
def home():
    if not session.get("authorized"):
        return denied()

    key = normalize_key(session.get("key", ""))
    device_id = clean_device_id(session.get("device_id", ""))
    if not key or not device_id:
        session.clear()
        return denied()

    # Keep the browser session tied to the same still-valid game key/device.
    valid, _ = verify_key_remote(key, device_id)
    if not valid:
        session.clear()
        return denied()

    kh = key_hash(key)
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
        mask=session.get("key_mask", mask_key(key)),
        saved=saved,
    )


@app.route("/api/settings", methods=["POST"])
def api_settings():
    data = request.get_json(silent=True) or {}
    key = normalize_key(data.get("key", ""))
    device_id = clean_device_id(data.get("device_id", ""))
    if not key or not device_id:
        return jsonify(ok=False, reason="missing_credentials"), 400

    valid, reason = verify_key_remote(key, device_id)
    if not valid:
        return jsonify(ok=False, reason=reason or "invalid_key"), 403

    settings = get_settings_by_hash(key_hash(key))
    return jsonify(ok=True, language=settings["language"], updated=settings["updated"])


@app.route("/logout")
def logout():
    session.clear()
    return denied()


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
