from flask import Flask, request, render_template_string, redirect, session
import os, secrets, urllib.request, urllib.error, json

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# Put the FIRST website URL in Render Environment Variables:
# KEY_MANAGER_URL=https://your-key-manager.onrender.com
KEY_MANAGER_URL = os.environ.get("KEY_MANAGER_URL", "").rstrip("/")

LOGIN_HTML = r"""
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cheto Access</title>
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;overflow:hidden;
font-family:Arial,sans-serif;color:#fff;background:#03050b}
.bg{position:fixed;inset:-25%;background:
radial-gradient(circle at 20% 25%,#4b2cff35,transparent 25%),
radial-gradient(circle at 80% 75%,#b52cff25,transparent 25%);
filter:blur(35px);animation:bg 7s ease-in-out infinite alternate}
@keyframes bg{to{transform:scale(1.15) rotate(5deg)}}
.shell{position:relative;width:min(420px,92vw);padding:2px;border-radius:22px;
background:linear-gradient(90deg,#6747ff,#b73cff,#32d9ff,#6747ff);
background-size:260%;animation:border 4s linear infinite;box-shadow:0 0 65px #6d4cff38}
@keyframes border{to{background-position:260%}}
.card{position:relative;background:#080c14;border-radius:20px;padding:30px;
box-shadow:inset 0 0 45px #7654ff08}
.logo{width:72px;height:72px;margin:0 auto 20px;border-radius:21px;display:grid;
place-items:center;font-size:30px;font-weight:900;background:linear-gradient(135deg,#5b3cff,#b63af0);
box-shadow:0 0 35px #7954ff55;animation:float 2.8s ease-in-out infinite}
@keyframes float{50%{transform:translateY(-6px) rotate(2deg)}}
h1{text-align:center;margin:0;font-size:27px}.sub{text-align:center;color:#858fa5;
font-size:12px;margin:9px 0 23px}
.field{position:relative}input{width:100%;padding:15px 15px;background:#04070e;
border:1px solid #283249;border-radius:11px;color:white;outline:none;font-size:14px;
transition:.25s}input:focus{border-color:#7558ff;box-shadow:0 0 0 4px #7558ff17}
button{width:100%;margin-top:12px;padding:14px;border:0;border-radius:11px;color:#fff;
font-weight:900;cursor:pointer;background:linear-gradient(90deg,#613cff,#b238ef);
background-size:180%;box-shadow:0 12px 35px #754cff28;animation:glow 3s linear infinite;
transition:.2s}@keyframes glow{50%{background-position:100%;box-shadow:0 12px 42px #9c45ff42}}
button:active{transform:scale(.98)}
.error{margin:0 0 13px;padding:11px;border:1px solid #69233a;border-radius:10px;
background:#260a14;color:#ff718a;font-size:12px;text-align:center;animation:shake .35s}
@keyframes shake{25%{transform:translateX(-5px)}75%{transform:translateX(5px)}}
.footer{text-align:center;color:#50596b;font-size:10px;margin-top:17px;letter-spacing:1.5px}
</style>
</head>
<body>
<div class="bg"></div>
<div class="shell"><div class="card">
<div class="logo">C</div>
<h1>Welcome Back</h1>
<div class="sub">Enter your Cheto access key to continue</div>
{% if error %}<div class="error">{{error}}</div>{% endif %}
<form method="POST">
<div class="field"><input name="key" placeholder="Activation Key" autocomplete="off" required></div>
<button>VERIFY & CONTINUE</button>
</form>
<div class="footer">CHETO • SECURE ACCESS</div>
</div></div>
</body>
</html>
"""

HOME_HTML = r"""
<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cheto Control</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#050811;color:#e9eefb;font-family:Arial,sans-serif;min-height:100vh}
.top{height:62px;position:sticky;top:0;z-index:5;background:#090e19dd;backdrop-filter:blur(14px);border-bottom:1px solid #202a3c;display:flex;align-items:center;padding:0 18px;gap:14px}
.menu{font-size:26px;color:#63b8ff}.brand{font-size:17px;font-weight:800;letter-spacing:.6px}.wrap{width:min(820px,94vw);margin:28px auto 70px}
.hero,.section{background:linear-gradient(145deg,#0c1320,#080d17);border:1px solid #202c40;border-radius:18px;padding:22px;margin-bottom:16px;box-shadow:0 18px 55px #0005}
h1{font-size:29px;margin:0 0 7px}.muted{color:#8592a8;margin:0;font-size:14px}.section h2{font-size:20px;margin:0 0 5px}.section p{color:#8491a6;margin:0 0 18px;font-size:13px}
.row{display:flex;align-items:center;justify-content:space-between;gap:15px;padding:13px 0;border-top:1px solid #172235}.row:first-of-type{border-top:0}.label{font-size:15px}.switch{position:relative;width:48px;height:27px;flex:0 0 auto}.switch input{display:none}.slider{position:absolute;inset:0;background:#293448;border-radius:99px;cursor:pointer;transition:.2s}.slider:before{content:"";position:absolute;width:21px;height:21px;left:3px;top:3px;border-radius:50%;background:#dfe8f5;transition:.2s}.switch input:checked+.slider{background:#2699e8;box-shadow:0 0 18px #2699e833}.switch input:checked+.slider:before{transform:translateX(21px);background:#fff}
.btn{border:0;border-radius:10px;padding:12px 16px;background:#168edb;color:white;font-weight:700;font-size:14px;cursor:pointer}.btn:active{transform:scale(.98)}select{background:#0b1220;color:#e8eef9;border:1px solid #2a3850;border-radius:10px;padding:11px 38px 11px 12px;font-size:14px}.inline{display:flex;align-items:center;justify-content:space-between;gap:12px}.theme{margin-top:8px}.logout{display:block;text-align:center;color:#718097;text-decoration:none;font-size:12px;margin-top:22px}@media(max-width:560px){.wrap{margin-top:16px}.hero,.section{padding:18px}h1{font-size:25px}.row{padding:12px 0}}
</style></head><body>
<div class="top"><div class="menu">☰</div><div class="brand">Cheto Control</div></div>
<div class="wrap">
 <div class="hero"><h1>Overview</h1><p class="muted">Quickly enable or disable important features.</p></div>
 <div class="section" id="overview">
  <div class="row"><span class="label">Aim assist</span><label class="switch"><input type="checkbox"><span class="slider"></span></label></div>
  <div class="row"><span class="label">No scope aimbot</span><label class="switch"><input type="checkbox"><span class="slider"></span></label></div>
  <div class="row"><span class="label">Enemy ESP</span><label class="switch"><input type="checkbox"><span class="slider"></span></label></div>
  <div class="row"><span class="label">Item ESP</span><label class="switch"><input type="checkbox"><span class="slider"></span></label></div>
  <div class="row"><span class="label">Vehicle ESP</span><label class="switch"><input type="checkbox"><span class="slider"></span></label></div>
  <div class="row"><span class="label">Tomb Box ESP</span><label class="switch"><input type="checkbox"><span class="slider"></span></label></div>
  <div class="row"><span class="label">Grenade ESP</span><label class="switch"><input type="checkbox"><span class="slider"></span></label></div>
  <div class="row"><span class="label">Airdrop ESP</span><label class="switch"><input type="checkbox"><span class="slider"></span></label></div>
  <div class="row"><span class="label">Bunny Hop</span><label class="switch"><input type="checkbox"><span class="slider"></span></label></div>
 </div>
 <div class="section"><h2>Open menu corner</h2><p>Choose where the control menu opens.</p><select><option>Top Left</option><option>Top Right</option><option>Bottom Left</option><option>Bottom Right</option></select></div>
 <div class="section"><h2>Aimbot profiles</h2><p>Manage your aimbot profiles.</p><button class="btn">New aimbot settings profile</button></div>
 <div class="section"><h2>Item profiles</h2><p>Manage your item profiles.</p><button class="btn">New item settings profile</button></div>
 <div class="section"><h2>Reset settings</h2><p>Restore the default configuration.</p><button class="btn">Load default settings</button></div>
 <div class="section"><h2>Language</h2><select><option>English</option><option>العربية</option></select></div>
 <div class="section"><h2>Theme</h2><div class="inline theme"><span class="muted">Midnight theme</span><label class="switch"><input type="checkbox" checked><span class="slider"></span></label></div></div>
 <a class="logout" href="/logout">Logout</a>
</div></body></html>
"""

def verify_key(key):
    if not KEY_MANAGER_URL:
        return False, "Server connection is not configured."
    payload = json.dumps({"key": key}).encode()
    req = urllib.request.Request(
        KEY_MANAGER_URL + "/verify",
        data=payload,
        headers={"Content-Type":"application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        if data.get("valid"):
            return True, ""
        reasons = {
            "invalid_key":"Invalid activation key.",
            "inactive":"This key is stopped or expired.",
            "device_limit":"Device limit reached.",
            "server_offline":"The server is currently offline."
        }
        return False, reasons.get(data.get("reason"), "Access denied.")
    except Exception:
        return False, "Could not connect to Key Manager."

@app.route("/", methods=["GET","POST"])
def login():
    if session.get("access"):
        return redirect("/home")
    error = None
    if request.method == "POST":
        key = request.form.get("key","").strip()
        valid, error = verify_key(key)
        if valid:
            session["access"] = True
            session["key"] = key
            return redirect("/home")
    return render_template_string(LOGIN_HTML, error=error)

@app.route("/home")
def home():
    if not session.get("access"):
        return redirect("/")
    # Re-check the key whenever this page is opened.
    valid, _ = verify_key(session.get("key",""))
    if not valid:
        session.clear()
        return redirect("/")
    return render_template_string(HOME_HTML)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
