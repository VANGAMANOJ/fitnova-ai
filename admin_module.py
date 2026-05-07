import sqlite3, functools, re, os, time
import bcrypt as _bcrypt
from flask import redirect, request, session, jsonify

_ADMIN_USER_HASH = _bcrypt.hashpw(b'FitnovaAi18',    _bcrypt.gensalt(12))
_ADMIN_PASS_HASH = _bcrypt.hashpw(b'VANGAMANOJ3182', _bcrypt.gensalt(12))
_ADMIN_SESSION_KEY = 'fn_admin_authenticated'
# Vercel uses /tmp for writable storage; fallback to local for dev
_DB_PATH = '/tmp/fitnova_data.db' if os.environ.get('VERCEL') else os.path.join(os.path.dirname(__file__), 'fitnova_data.db')
_rate_store = {}

def get_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS visitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT, ua TEXT, path TEXT,
                ts TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT, rating INTEGER, message TEXT,
                ts TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS admin_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT, ip TEXT,
                ts TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS site_settings (
                key TEXT PRIMARY KEY, value TEXT
            );
        """)
        db.commit()

def _rate_limit(ip, action, max_hits=10, window=60):
    key = f"{ip}:{action}"
    now = time.time()
    hits = [t for t in _rate_store.get(key, []) if now - t < window]
    hits.append(now)
    _rate_store[key] = hits
    return len(hits) > max_hits

def admin_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get(_ADMIN_SESSION_KEY):
            return redirect('/fn-admin-2026/login')
        return f(*args, **kwargs)
    return wrapper

def get_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()

def register(app):
    init_db()

    @app.after_request
    def security_headers(resp):
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['X-Frame-Options']         = 'DENY'
        resp.headers['X-XSS-Protection']        = '1; mode=block'
        resp.headers['Referrer-Policy']          = 'strict-origin-when-cross-origin'
        return resp

    @app.before_request
    def log_visit():
        p = request.path
        skip = ['/fn-admin', '/static', '/api/process_frame', '/api/submit_feedback', '/api/announcement']
        if any(p.startswith(s) for s in skip): return
        ip = get_ip()
        ua = request.headers.get('User-Agent', '')[:200]
        try:
            with get_db() as db:
                db.execute("INSERT INTO visitors (ip,ua,path) VALUES (?,?,?)", (ip, ua, p))
                db.commit()
        except Exception:
            pass

    @app.route('/fn-admin-2026/login', methods=['GET', 'POST'])
    def admin_login():
        ip = get_ip()
        if _rate_limit(ip, 'admin_login', max_hits=5, window=300):
            return '<div style="font-family:sans-serif;color:red;text-align:center;padding-top:30vh"><h2>Too many attempts.</h2><p>Wait 5 minutes.</p></div>', 429
        error = ''
        if request.method == 'POST':
            u = (request.form.get('username', '') or '').encode()
            p = (request.form.get('password', '') or '').encode()
            try:
                u_ok = _bcrypt.checkpw(u, _ADMIN_USER_HASH)
                p_ok = _bcrypt.checkpw(p, _ADMIN_PASS_HASH)
            except Exception:
                u_ok = p_ok = False
            if u_ok and p_ok:
                session[_ADMIN_SESSION_KEY] = True
                session.permanent = True
                with get_db() as db:
                    db.execute("INSERT INTO admin_log (event,ip) VALUES (?,?)", ('LOGIN_OK', ip))
                    db.commit()
                return redirect('/fn-admin-2026')
            else:
                with get_db() as db:
                    db.execute("INSERT INTO admin_log (event,ip) VALUES (?,?)", ('LOGIN_FAIL', ip))
                    db.commit()
                error = 'Invalid credentials.'

        err_html = f'<div class="err">{error}</div>' if error else ''
        return f'''<!DOCTYPE html><html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#000;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:"Segoe UI",sans-serif}}
.box{{background:#0a0a0a;border:1px solid #1f1f1f;border-radius:16px;padding:44px 32px;width:100%;max-width:360px;text-align:center}}
.icon{{font-size:40px;margin-bottom:10px}}h2{{color:#fff;font-size:20px;margin-bottom:6px}}
p{{color:#444;font-size:13px;margin-bottom:28px}}
input{{width:100%;padding:12px 16px;background:#111;border:1.5px solid #222;border-radius:10px;color:#fff;font-size:14px;margin-bottom:12px;outline:none;font-family:inherit}}
input:focus{{border-color:#4d8cff}}
button{{width:100%;padding:13px;background:linear-gradient(135deg,#4d8cff,#7b2ff7);border:none;border-radius:10px;color:#fff;font-size:15px;font-weight:700;cursor:pointer;font-family:inherit}}
.err{{color:#ff4d6d;font-size:13px;margin-bottom:12px;padding:8px;background:#ff4d6d11;border-radius:8px}}
.hint{{color:#222;font-size:11px;margin-top:18px}}
</style></head><body>
<div class="box"><div class="icon">⚡</div>
<h2>Fitnova AI Admin</h2><p>Restricted access only</p>
{err_html}
<form method="POST" autocomplete="off">
<input name="username" type="text" placeholder="Username" autocomplete="off" required/>
<input name="password" type="password" placeholder="Password" autocomplete="new-password" required/>
<button type="submit">Access Dashboard</button>
</form><div class="hint">Not publicly linked.</div></div></body></html>'''

    @app.route('/fn-admin-2026/logout')
    def admin_logout():
        session.pop(_ADMIN_SESSION_KEY, None)
        return redirect('/fn-admin-2026/login')

    @app.route('/fn-admin-2026')
    @app.route('/fn-admin-2026/')
    @admin_required
    def admin_dashboard():
        with get_db() as db:
            total  = db.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
            today  = db.execute("SELECT COUNT(*) FROM visitors WHERE date(ts)=date('now')").fetchone()[0]
            week   = db.execute("SELECT COUNT(*) FROM visitors WHERE ts >= datetime('now','-7 days')").fetchone()[0]
            uniq   = db.execute("SELECT COUNT(DISTINCT ip) FROM visitors").fetchone()[0]
            daily  = db.execute("SELECT date(ts) as day, COUNT(*) as cnt FROM visitors WHERE ts >= datetime('now','-14 days') GROUP BY date(ts) ORDER BY day").fetchall()
            fbs    = db.execute("SELECT * FROM feedback ORDER BY ts DESC LIMIT 50").fetchall()
            fbc    = db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
            avgr   = db.execute("SELECT AVG(rating) FROM feedback").fetchone()[0] or 0
            tips   = db.execute("SELECT ip, COUNT(*) as cnt FROM visitors GROUP BY ip ORDER BY cnt DESC LIMIT 5").fetchall()
            recvis = db.execute("SELECT * FROM visitors ORDER BY ts DESC LIMIT 15").fetchall()
            annr   = db.execute("SELECT value FROM site_settings WHERE key='announcement'").fetchone()
            ann    = annr['value'] if annr else ''

        dlabels = str([r['day'] for r in daily])
        dcounts = str([r['cnt'] for r in daily])

        fb_html = ''
        for r in fbs:
            stars = '&#9733;' * int(r['rating'] or 0) + '&#9734;' * (5 - int(r['rating'] or 0))
            fb_html += f'<div class="fbi"><div class="fbt"><span class="fbn">{r["name"] or "Anonymous"}</span><span class="fbs">{stars}</span></div><div class="fbm">{r["message"] or ""}</div><div class="fbts">{r["ts"]}</div></div>'
        if not fb_html:
            fb_html = '<div class="empty">No reviews yet.</div>'

        ip_rows  = ''.join(f'<tr><td>{r["ip"]}</td><td><b style="color:#4d8cff">{r["cnt"]}</b></td></tr>' for r in tips)
        vis_rows = ''.join(f'<tr><td>{r["path"]}</td><td>{r["ip"]}</td><td>{str(r["ts"])[-8:]}</td></tr>' for r in recvis)

        return f'''<!DOCTYPE html><html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fitnova Admin</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#000;color:#bbb;font-family:"Segoe UI",sans-serif}}
.tb{{background:#070707;border-bottom:1px solid #181818;padding:14px 24px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:10}}
.tb h1{{font-size:17px;color:#fff;font-weight:700}}
.lo{{color:#ff4d6d;font-size:13px;text-decoration:none;border:1px solid #ff4d6d44;padding:6px 14px;border-radius:8px}}
.lo:hover{{background:#ff4d6d11}}
.main{{padding:20px;max-width:1280px;margin:0 auto}}
.kr{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:18px}}
.k{{background:#0a0a0a;border:1px solid #181818;border-radius:12px;padding:16px 12px;text-align:center}}
.kv{{font-size:26px;font-weight:800;color:#4d8cff}}.kl{{font-size:10px;color:#444;text-transform:uppercase;letter-spacing:.5px;margin-top:3px}}
.g2{{display:grid;grid-template-columns:2fr 1fr;gap:12px;margin-bottom:14px}}
.g2b{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.pn{{background:#0a0a0a;border:1px solid #181818;border-radius:12px;padding:16px}}
.pn h3{{font-size:13px;color:#fff;font-weight:700;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #131313}}
canvas{{max-height:170px}}
.fbi{{padding:9px 0;border-bottom:1px solid #0e0e0e}}.fbi:last-child{{border-bottom:none}}
.fbt{{display:flex;justify-content:space-between;margin-bottom:3px}}
.fbn{{font-size:13px;color:#fff;font-weight:600}}.fbs{{color:#ffc107;font-size:12px}}
.fbm{{font-size:12px;color:#666;line-height:1.5}}.fbts{{font-size:10px;color:#333;margin-top:2px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{padding:6px 8px;color:#333;text-align:left;border-bottom:1px solid #0e0e0e;font-size:10px;text-transform:uppercase;letter-spacing:.4px}}
td{{padding:6px 8px;color:#777;border-bottom:1px solid #080808}}
.empty{{color:#333;font-size:13px;padding:16px 0}}
label{{display:block;font-size:10px;color:#444;margin-bottom:5px;text-transform:uppercase;letter-spacing:.4px}}
textarea{{width:100%;padding:9px 12px;background:#111;border:1.5px solid #1a1a1a;border-radius:8px;color:#fff;font-size:13px;outline:none;resize:vertical;font-family:inherit}}
textarea:focus{{border-color:#4d8cff}}
.btn{{padding:8px 16px;background:linear-gradient(135deg,#4d8cff,#7b2ff7);border:none;border-radius:8px;color:#fff;font-size:12px;font-weight:700;cursor:pointer;margin-top:7px}}
.ok{{color:#00c87a;font-size:12px;margin-top:5px;display:none}}
@media(max-width:900px){{.kr{{grid-template-columns:repeat(3,1fr)}}.g2,.g2b{{grid-template-columns:1fr}}}}
</style></head><body>
<div class="tb"><h1>⚡ Fitnova AI Admin</h1>
<div style="display:flex;gap:12px;align-items:center">
<span style="font-size:12px;color:#333">FitnovaAi18</span>
<a href="/fn-admin-2026/logout" class="lo">Sign Out</a></div></div>
<div class="main">
<div class="kr">
<div class="k"><div class="kv">{total}</div><div class="kl">Total Visits</div></div>
<div class="k"><div class="kv">{today}</div><div class="kl">Today</div></div>
<div class="k"><div class="kv">{week}</div><div class="kl">This Week</div></div>
<div class="k"><div class="kv">{uniq}</div><div class="kl">Unique IPs</div></div>
<div class="k"><div class="kv">{fbc}</div><div class="kl">Reviews</div></div>
<div class="k"><div class="kv" style="color:#ffc107">{avgr:.1f}★</div><div class="kl">Avg Rating</div></div>
</div>
<div class="g2">
<div class="pn"><h3>📈 Daily Traffic — Last 14 Days</h3><canvas id="vc"></canvas></div>
<div class="pn"><h3>🌐 Top Visitors</h3><table><tr><th>IP</th><th>Hits</th></tr>{ip_rows}</table></div>
</div>
<div class="g2b">
<div class="pn"><h3>💬 User Reviews</h3>{fb_html}</div>
<div class="pn">
<h3>⚙️ Site Settings</h3>
<div style="margin-bottom:20px">
<label>Announcement Banner</label>
<textarea id="ann" rows="3" placeholder="Leave empty to hide...">{ann}</textarea>
<button class="btn" onclick="saveAnn()">Save Banner</button>
<div class="ok" id="ok1">✅ Saved!</div>
</div>
<h3>🕐 Recent Visits</h3>
<table><tr><th>Path</th><th>IP</th><th>Time</th></tr>{vis_rows}</table>
</div>
</div>
</div>
<script>
new Chart(document.getElementById('vc').getContext('2d'),{{
type:'bar',data:{{labels:{dlabels},datasets:[{{label:'Visitors',data:{dcounts},
backgroundColor:'rgba(77,140,255,0.4)',borderColor:'#4d8cff',borderWidth:2,borderRadius:5}}]}},
options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},
scales:{{x:{{grid:{{color:'#0a0a0a'}},ticks:{{color:'#444',font:{{size:10}}}}}},
y:{{grid:{{color:'#0a0a0a'}},ticks:{{color:'#444',font:{{size:10}},stepSize:1}}}}}}}}
}});
async function saveAnn(){{
await fetch('/fn-admin-2026/api/setting',{{method:'POST',
headers:{{'Content-Type':'application/json'}},
body:JSON.stringify({{key:'announcement',value:document.getElementById('ann').value}})}});
const e=document.getElementById('ok1');e.style.display='block';
setTimeout(()=>e.style.display='none',2500);}}
</script></body></html>'''

    @app.route('/fn-admin-2026/api/setting', methods=['POST'])
    @admin_required
    def admin_save_setting():
        data = request.json or {}
        key, val = data.get('key', ''), data.get('value', '')
        if not key: return jsonify({'ok': False}), 400
        with get_db() as db:
            db.execute("INSERT OR REPLACE INTO site_settings (key,value) VALUES (?,?)", (key, val))
            db.commit()
        return jsonify({'ok': True})

    @app.route('/api/submit_feedback', methods=['POST'])
    def submit_feedback():
        ip = get_ip()
        if _rate_limit(ip, 'feedback', max_hits=3, window=600):
            return jsonify({'ok': False, 'error': 'Too many submissions. Try later.'}), 429
        data = request.json or {}
        name    = re.sub(r'[<>"\'&;]', '', str(data.get('name', 'Anonymous'))[:60])
        rating  = max(1, min(5, int(data.get('rating', 5) or 5)))
        message = re.sub(r'[<>"\'&]', '', str(data.get('message', ''))[:500])
        with get_db() as db:
            db.execute("INSERT INTO feedback (name,rating,message) VALUES (?,?,?)", (name, rating, message))
            db.commit()
        return jsonify({'ok': True})

    @app.route('/api/announcement')
    def get_announcement():
        with get_db() as db:
            row = db.execute("SELECT value FROM site_settings WHERE key='announcement'").fetchone()
        return jsonify({'announcement': row['value'] if row else ''})
    @app.route('/api/admin_stats', methods=['POST'])
    def admin_stats():
        data = request.json or {}
        u = (data.get('username') or '').encode()
        p = (data.get('password') or '').encode()
        try:
            u_ok = _bcrypt.checkpw(u, _ADMIN_USER_HASH)
            p_ok = _bcrypt.checkpw(p, _ADMIN_PASS_HASH)
        except Exception:
            u_ok = p_ok = False
        if not (u_ok and p_ok):
            return jsonify({'ok': False, 'error': 'Invalid credentials'}), 401
        with get_db() as db:
            total  = db.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
            today  = db.execute("SELECT COUNT(*) FROM visitors WHERE date(ts)=date('now')").fetchone()[0]
            week   = db.execute("SELECT COUNT(*) FROM visitors WHERE ts >= datetime('now','-7 days')").fetchone()[0]
            uniq   = db.execute("SELECT COUNT(DISTINCT ip) FROM visitors").fetchone()[0]
            daily  = db.execute("SELECT date(ts) as day, COUNT(*) as cnt FROM visitors WHERE ts >= datetime('now','-14 days') GROUP BY date(ts) ORDER BY day").fetchall()
            fbs    = db.execute("SELECT * FROM feedback ORDER BY ts DESC").fetchall()
            fbc    = db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
            avgr   = db.execute("SELECT ROUND(AVG(rating),1) FROM feedback").fetchone()[0] or 0
            annr   = db.execute("SELECT value FROM site_settings WHERE key='announcement'").fetchone()
            recvis = db.execute("SELECT path,ip,ts FROM visitors ORDER BY ts DESC LIMIT 20").fetchall()
        return jsonify({
            'ok': True,
            'total': total, 'today': today, 'week': week, 'unique': uniq,
            'fb_count': fbc, 'avg_rating': float(avgr),
            'daily_labels': [r['day'] for r in daily],
            'daily_counts': [r['cnt'] for r in daily],
            'reviews': [{'id': r['id'], 'name': r['name'], 'rating': r['rating'], 'message': r['message'], 'ts': r['ts']} for r in fbs],
            'announcement': annr['value'] if annr else '',
            'recent_visits': [{'path': r['path'], 'ip': r['ip'], 'ts': r['ts']} for r in recvis],
        })

    @app.route('/api/delete_review', methods=['POST'])
    def delete_review():
        data = request.json or {}
        u = (data.get('username') or '').encode()
        p = (data.get('password') or '').encode()
        rid = data.get('id')
        try:
            u_ok = _bcrypt.checkpw(u, _ADMIN_USER_HASH)
            p_ok = _bcrypt.checkpw(p, _ADMIN_PASS_HASH)
        except Exception:
            u_ok = p_ok = False
        if not (u_ok and p_ok):
            return jsonify({'ok': False}), 401
        if not rid:
            return jsonify({'ok': False}), 400
        with get_db() as db:
            db.execute("DELETE FROM feedback WHERE id=?", (rid,))
            db.commit()
        return jsonify({'ok': True})

    @app.route('/api/public_reviews')
    def public_reviews():
        with get_db() as db:
            rows = db.execute("SELECT name, rating, message, ts FROM feedback ORDER BY ts DESC LIMIT 30").fetchall()
        return jsonify({'reviews': [{'name': r['name'], 'rating': r['rating'], 'message': r['message'], 'ts': r['ts']} for r in rows]})

