from flask import Flask, request, render_template_string, redirect, session
import os, secrets, urllib.request, urllib.error, json

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# Put the FIRST website URL in Render Environment Variables:
# KEY_MANAGER_URL=https://your-key-manager.onrender.com
KEY_MANAGER_URL = os.environ.get("KEY_MANAGER_URL", "").rstrip("/")

LOGIN_HTML = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cheto Access</title><style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;font-family:Arial,sans-serif;color:#e9eefb;background:radial-gradient(circle at 50% 0,#0b1a2c 0,#050811 42%,#03060c 100%);padding:22px}.card{width:min(430px,94vw);background:linear-gradient(145deg,#0c1320,#080d17);border:1px solid #202c40;border-radius:24px;padding:32px 24px 26px;box-shadow:0 24px 70px #000a,0 0 0 1px #ffffff05;animation:rise .55s cubic-bezier(.2,.8,.2,1)}@keyframes rise{from{opacity:0;transform:translateY(18px) scale(.98)}to{opacity:1;transform:none}}.logo{width:156px;height:64px;object-fit:contain;display:block;margin:0 auto 14px;filter:drop-shadow(0 10px 25px #0008)}h1{text-align:center;margin:6px 0 7px;font-size:28px}.sub{text-align:center;color:#8491a6;font-size:13px;margin-bottom:23px}.error{padding:11px;border-radius:11px;background:#2a0e18;border:1px solid #6a283b;color:#ff8297;font-size:12px;margin-bottom:13px;text-align:center}input{width:100%;padding:15px;background:#080e18;border:1px solid #2a3850;border-radius:12px;color:#fff;outline:none;font-size:14px;transition:.2s}input:focus{border-color:#2699e8;box-shadow:0 0 0 4px #2699e817}button{width:100%;margin-top:13px;padding:14px;border:0;border-radius:12px;background:linear-gradient(135deg,#168edb,#2aa8f2);color:#fff;font-size:14px;font-weight:800;box-shadow:0 12px 28px #168edb2b}.foot{text-align:center;color:#56647a;font-size:10px;margin-top:18px;letter-spacing:1.4px}
</style></head><body><div class="card"><img class="logo" src="/static/cheto.png" onerror="this.style.display='none'"><h1>Cheto Control</h1><div class="sub">Enter your activation key to access settings.</div>{% if error %}<div class="error">{{error}}</div>{% endif %}<form method="POST"><input name="key" placeholder="Activation Key" autocomplete="off" required><button>Continue</button></form><div class="foot">MIDNIGHT CONTROL PANEL</div></div></body></html>
"""

HOME_HTML = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cheto Control</title><style>
*{box-sizing:border-box}body{margin:0;background:#050811;color:#e9eefb;font-family:Arial,sans-serif;min-height:100vh}.top{height:62px;position:sticky;top:0;z-index:20;background:#090e19ee;backdrop-filter:blur(14px);border-bottom:1px solid #202a3c;display:flex;align-items:center;padding:0 20px;gap:15px}.menu{font-size:29px;color:#63b8ff;cursor:pointer;line-height:1}.brand{font-size:18px;font-weight:800}.wrap{width:min(820px,94vw);margin:22px auto 70px}.hero,.section{background:linear-gradient(145deg,#0c1320,#080d17);border:1px solid #202c40;border-radius:18px;padding:22px;margin-bottom:16px;box-shadow:0 18px 55px #0005}h1{font-size:29px;margin:0 0 7px}.muted,.section p{color:#8491a6}.section h2{font-size:20px;margin:0 0 5px}.section p{margin:0 0 18px;font-size:13px}.row{display:flex;align-items:center;justify-content:space-between;gap:15px;padding:13px 0;border-top:1px solid #172235}.row:first-of-type{border-top:0}.label{font-size:15px}.switch{position:relative;width:48px;height:27px;flex:0 0 auto}.switch input{display:none}.slider{position:absolute;inset:0;background:#293448;border-radius:99px;cursor:pointer;transition:.25s}.slider:before{content:"";position:absolute;width:21px;height:21px;left:3px;top:3px;border-radius:50%;background:#dfe8f5;transition:.25s}.switch input:checked+.slider{background:#2699e8}.switch input:checked+.slider:before{transform:translateX(21px);background:#fff}.btn{border:0;border-radius:10px;padding:12px 16px;background:#168edb;color:white;font-weight:700;font-size:14px}.selectBtn{display:flex;align-items:center;justify-content:space-between;width:min(240px,100%);padding:13px 15px;background:#0b1220;color:#e8eef9;border:1px solid #2a3850;border-radius:11px;font-size:14px;cursor:pointer}.chev{color:#63b8ff}.inline{display:flex;align-items:center;justify-content:space-between;gap:12px}.logout{display:block;text-align:center;color:#718097;text-decoration:none;font-size:12px;margin-top:22px}
/* custom site modal */.modal{position:fixed;inset:0;z-index:60;background:#0008;backdrop-filter:blur(5px);display:flex;align-items:flex-end;justify-content:center;opacity:0;pointer-events:none;transition:.25s}.modal.show{opacity:1;pointer-events:auto}.sheet{width:min(560px,100%);background:#0b111c;border:1px solid #26344a;border-radius:22px 22px 0 0;padding:10px 14px 22px;transform:translateY(100%);transition:.3s cubic-bezier(.2,.8,.2,1)}.modal.show .sheet{transform:translateY(0)}.grab{width:42px;height:4px;border-radius:9px;background:#34435a;margin:2px auto 10px}.opt{display:flex;align-items:center;justify-content:space-between;padding:17px 12px;border-bottom:1px solid #1c2839;font-size:16px;cursor:pointer}.opt:last-child{border-bottom:0}.radio{width:21px;height:21px;border:2px solid #71819a;border-radius:50%}.opt.active .radio{border:6px solid #2699e8}
/* drawer */.shade{position:fixed;inset:0;background:#0009;z-index:39;opacity:0;pointer-events:none;transition:.25s}.shade.show{opacity:1;pointer-events:auto}.drawer{position:fixed;z-index:40;left:0;top:0;bottom:0;width:min(76vw,300px);background:#080e18;border-right:1px solid #243249;transform:translateX(-102%);transition:.3s cubic-bezier(.2,.8,.2,1);padding:26px 18px}.drawer.show{transform:none}.profile{text-align:center;padding:14px 6px 20px;border-bottom:1px solid #1c2839}.pic{width:78px;height:78px;margin:auto;border-radius:50%;display:grid;place-items:center;overflow:hidden;background:linear-gradient(145deg,#132238,#0b1422);border:1px solid #2e4564;box-shadow:0 0 28px #168edb22}.pic img{width:100%;height:100%;object-fit:cover}.pname{font-weight:800;margin-top:10px}.keybox{margin-top:13px;display:flex;align-items:center;gap:8px;background:#050a12;border:1px solid #202e43;border-radius:10px;padding:10px}.keytxt{font-family:monospace;font-size:11px;color:#9ba9bc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1}.eye{border:0;background:none;color:#63b8ff;font-size:18px;padding:0;cursor:pointer}.nav{margin-top:18px}.navitem{display:flex;align-items:center;gap:11px;padding:13px;border-radius:11px;background:#101a29;border:1px solid #24354e;color:#eaf1fb;font-weight:700}.navicon{color:#63b8ff}
.systemLayer{position:fixed;inset:0;z-index:100;background:#02050ad9;backdrop-filter:blur(18px);display:grid;place-items:center;padding:24px;opacity:0;pointer-events:none;transition:.3s}.systemLayer.show{opacity:1;pointer-events:auto}.systemCard{width:min(430px,94vw);background:linear-gradient(145deg,#101a2a,#080d17);border:1px solid #2a3b55;border-radius:24px;padding:28px;text-align:center;box-shadow:0 30px 100px #000,0 0 50px #168edb18;transform:scale(.94) translateY(10px);transition:.35s}.systemLayer.show .systemCard{transform:none}.sysIcon{width:64px;height:64px;margin:0 auto 16px;border-radius:20px;display:grid;place-items:center;background:#10243a;border:1px solid #275077;font-size:28px}.systemCard h3{font-size:23px;margin:0 0 10px}.systemCard p{white-space:pre-line;color:#9aa8bb;line-height:1.65;margin:0}.offline .sysIcon{background:#28121a;border-color:#633041}.offline h3{color:#ff8da0}.pulse{width:8px;height:8px;border-radius:50%;background:#ff5f78;display:inline-block;margin-right:7px;box-shadow:0 0 0 0 #ff5f7866;animation:pulse 1.5s infinite}@keyframes pulse{70%{box-shadow:0 0 0 12px #ff5f7800}}.statusline{margin-top:18px;color:#64738a;font-size:11px;letter-spacing:1px;text-transform:uppercase}@media(max-width:560px){.wrap{margin-top:16px}.hero,.section{padding:18px}h1{font-size:25px}}
</style></head><body>
<div class="top"><div class="menu" onclick="drawer(true)">☰</div><div class="brand">Cheto Control</div></div>
<div class="shade" id="shade" onclick="drawer(false)"></div><aside class="drawer" id="drawer"><div class="profile"><div class="pic"><img src="/static/cheto.png" onerror="this.parentElement.innerHTML='C'"></div><div class="pname">Cheto Account</div><div class="keybox"><span class="keytxt" id="keytxt">••••••••••••••••</span><button class="eye" onclick="toggleKey()" id="eye">◉</button></div></div><div class="nav"><div class="navitem"><span class="navicon">⚙</span>Settings</div></div></aside>
<div class="wrap"><div class="hero"><h1>Overview</h1><p class="muted">Quickly enable or disable important features.</p></div><div class="section">
{% for x in ['Aim assist','No scope aimbot','Enemy ESP','Item ESP','Vehicle ESP','Tomb Box ESP','Grenade ESP','Airdrop ESP','Bunny Hop'] %}<div class="row"><span class="label">{{x}}</span><label class="switch"><input type="checkbox"><span class="slider"></span></label></div>{% endfor %}</div>
<div class="section"><h2>Open menu corner</h2><p>Choose where the control menu opens.</p><button class="selectBtn" onclick="openPick('corner')"><span id="cornerText">Top Left</span><span class="chev">⌄</span></button></div>
<div class="section"><h2>Aimbot profiles</h2><p>Manage your aimbot profiles.</p><button class="btn">New aimbot settings profile</button></div><div class="section"><h2>Item profiles</h2><p>Manage your item profiles.</p><button class="btn">New item settings profile</button></div><div class="section"><h2>Reset settings</h2><p>Restore the default configuration.</p><button class="btn">Load default settings</button></div>
<div class="section"><h2>Language</h2><button class="selectBtn" onclick="openPick('lang')"><span id="langText">English</span><span class="chev">⌄</span></button></div><div class="section"><h2>Theme</h2><div class="inline"><span class="muted">Midnight theme</span><label class="switch"><input type="checkbox" checked><span class="slider"></span></label></div></div><a class="logout" href="/logout">Logout</a></div>
<div class="modal" id="modal" onclick="if(event.target===this)closePick()"><div class="sheet"><div class="grab"></div><div id="options"></div></div></div>
<div class="systemLayer" id="updateLayer"><div class="systemCard"><div class="sysIcon">✦</div><h3 id="updateTitle">System Update</h3><p id="updateMessage"></p><div class="statusline">Cheto Control • Live notice</div></div></div>
<div class="systemLayer offline" id="offlineLayer"><div class="systemCard"><div class="sysIcon">!</div><h3>Connection suspended</h3><p>The control server is temporarily unavailable.
Your session is safe — access will return automatically when the server is online.</p><div class="statusline"><span class="pulse"></span>Waiting for server</div></div></div>
<script>
const KEY={{ access_key|tojson }};let showing=false,current='';const data={lang:['English','العربية'],corner:['Top Left','Top Right','Bottom Left','Bottom Right']};
function drawer(v){document.getElementById('drawer').classList.toggle('show',v);document.getElementById('shade').classList.toggle('show',v)}
function toggleKey(){showing=!showing;document.getElementById('keytxt').textContent=showing?KEY:'••••••••••••••••';document.getElementById('eye').textContent=showing?'◉':'◎'}
function openPick(type){current=type;let selected=document.getElementById(type+'Text').textContent;document.getElementById('options').innerHTML=data[type].map(v=>`<div class="opt ${v===selected?'active':''}" onclick="choose('${v.replace(/'/g,"\'")}')"><span>${v}</span><span class="radio"></span></div>`).join('');document.getElementById('modal').classList.add('show')}
function choose(v){document.getElementById(current+'Text').textContent=v;closePick()}
function closePick(){document.getElementById('modal').classList.remove('show')}
let lastNotice='';
async function syncServer(){try{const r=await fetch('/api/server-status',{cache:'no-store'}),d=await r.json();const off=(d.enabled===false)||(d.server_enabled===false);document.getElementById('offlineLayer').classList.toggle('show',off);if(off)return;const active=!!d.update_active;const title=d.title||'System Update';const msg=d.message||'';const sig=title+'|'+msg+'|'+active;if(active){document.getElementById('updateTitle').textContent=title;document.getElementById('updateMessage').textContent=msg;document.getElementById('updateLayer').classList.add('show');lastNotice=sig}else{document.getElementById('updateLayer').classList.remove('show')}}catch(e){}}
syncServer();setInterval(syncServer,4000);
</script></body></html>
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
    return render_template_string(HOME_HTML, access_key=session.get("key", ""))

@app.route("/api/server-status")
def server_status_proxy():
    if not session.get("access"):
        return {"enabled": False}, 401
    try:
        req = urllib.request.Request(KEY_MANAGER_URL + "/server/status", headers={"Cache-Control":"no-cache"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode())
        return data
    except Exception:
        return {"enabled": True, "update_active": False}

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
