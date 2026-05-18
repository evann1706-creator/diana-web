"""
DIANA-WEB v4.0 — Flask App dengan DIANA Engine Nyata
Tim DIANA | PKTJ Tegal | LKTI 2026

Fix utama:
  ✅ Path ABSOLUT untuk semua file (upload/results/excel/video)
  ✅ process_bg memanggil DianaEngine nyata
  ✅ Download Excel & Video langsung dari path absolut
  ✅ Dashboard per-user (kosong untuk user baru)
  ✅ Tracking YOLO + ByteTrack nyata
"""

import os, io, sys, json, uuid, threading, hashlib, random
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect,
                   url_for, jsonify, send_file, flash, session)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# ─── PATH SETUP (ABSOLUT — tidak bergantung dari mana python dijalankan) ──
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR  = os.path.join(BASE_DIR, 'uploads')
RESULTS_DIR = os.path.join(BASE_DIR, 'results')
os.makedirs(UPLOAD_DIR,  exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))
app.config.update(
    SECRET_KEY='diana-pktj-2026-lkti-secret',
    SQLALCHEMY_DATABASE_URI=f'sqlite:///{os.path.join(BASE_DIR, "instance", "diana.db")}',
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=500 * 1024 * 1024,
)
os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
db = SQLAlchemy(app)

# ══════════════════════════════════════════════════════════════════
#  MODELS
# ══════════════════════════════════════════════════════════════════

class User(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(80), unique=True, nullable=False)
    email      = db.Column(db.String(120), unique=True, nullable=False)
    password   = db.Column(db.String(256), nullable=False)
    role       = db.Column(db.String(20), default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active  = db.Column(db.Boolean, default=True)

class VideoSession(db.Model):
    id             = db.Column(db.String(36), primary_key=True,
                               default=lambda: str(uuid.uuid4()))
    user_id        = db.Column(db.Integer, db.ForeignKey('user.id'))
    filename       = db.Column(db.String(255))
    orig_name      = db.Column(db.String(255))
    road_name      = db.Column(db.String(200))
    cctv_date      = db.Column(db.String(20))
    cctv_time      = db.Column(db.String(20))
    n_lanes        = db.Column(db.Integer, default=4)
    status         = db.Column(db.String(20), default='pending')
    progress       = db.Column(db.Integer, default=0)
    progress_msg   = db.Column(db.String(200), default='')
    upload_date    = db.Column(db.DateTime, default=datetime.utcnow)
    # Results
    total_veh      = db.Column(db.Integer, default=0)
    total_kr       = db.Column(db.Integer, default=0)
    total_kb       = db.Column(db.Integer, default=0)
    total_sm       = db.Column(db.Integer, default=0)
    avg_speed      = db.Column(db.Float, default=0)
    max_speed      = db.Column(db.Float, default=0)
    danger_ev      = db.Column(db.Integer, default=0)
    warning_ev     = db.Column(db.Integer, default=0)
    q_smp          = db.Column(db.Float, default=0)
    dj             = db.Column(db.Float, default=0)
    tp             = db.Column(db.String(2), default='B')
    # File paths (ABSOLUT)
    video_out_path = db.Column(db.String(500))
    excel_path     = db.Column(db.String(500))
    has_video      = db.Column(db.Boolean, default=False)
    has_excel      = db.Column(db.Boolean, default=False)
    user           = db.relationship('User', backref='sessions')

class DangerEvent(db.Model):
    id               = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id       = db.Column(db.String(36), db.ForeignKey('video_session.id'))
    timestamp_s      = db.Column(db.Float)
    frame_no         = db.Column(db.Integer)
    ttc_value        = db.Column(db.Float)
    category         = db.Column(db.String(20))
    v_back           = db.Column(db.Float)
    v_front          = db.Column(db.Float)
    distance_m       = db.Column(db.Float)
    lane             = db.Column(db.String(20))
    vehicle_id_back  = db.Column(db.String(20))
    vehicle_id_front = db.Column(db.String(20))

class NewsItem(db.Model):
    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title      = db.Column(db.String(300))
    content    = db.Column(db.Text)
    category   = db.Column(db.String(50), default='berita')
    video_url  = db.Column(db.String(500))
    image_url  = db.Column(db.String(500))
    author     = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active  = db.Column(db.Boolean, default=True)

class MapSpot(db.Model):
    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nama        = db.Column(db.String(200))
    jalan       = db.Column(db.String(300))
    lat         = db.Column(db.Float)
    lng         = db.Column(db.Float)
    tingkat     = db.Column(db.String(20))
    kejadian    = db.Column(db.Integer, default=0)
    keterangan  = db.Column(db.Text)
    sumber      = db.Column(db.String(100), default='Penelitian')
    session_id  = db.Column(db.String(36))
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

class SiteConfig(db.Model):
    key   = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)
    @classmethod
    def get(cls, k, default=''):
        r = cls.query.get(k); return r.value if r else default
    @classmethod
    def set(cls, k, v):
        r = cls.query.get(k)
        if r: r.value = str(v)
        else: db.session.add(cls(key=k, value=str(v)))
        db.session.commit()

# ══════════════════════════════════════════════════════════════════
#  AUTH HELPERS
# ══════════════════════════════════════════════════════════════════

def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('login'))
        return f(*a, **kw)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a, **kw):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        u = User.query.get(session['user_id'])
        if not u or u.role != 'admin':
            flash('Akses ditolak.', 'danger')
            return redirect(url_for('home'))
        return f(*a, **kw)
    return d

def current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

app.jinja_env.globals['current_user'] = current_user

def get_yt_id(embed_url):
    if not embed_url: return None
    if '/embed/' in embed_url:
        return embed_url.split('/embed/')[-1].split('?')[0]
    return None

app.jinja_env.globals['get_yt_id'] = get_yt_id

def convert_yt(url):
    if not url: return ''
    if '/embed/' in url: return url
    vid = None
    for p in ['v=', 'youtu.be/', 'shorts/']:
        if p in url:
            vid = url.split(p)[-1].split('&')[0].split('?')[0].split('/')[0]
            break
    return f'https://www.youtube.com/embed/{vid}' if vid else url

def calc_pkji(kr, kb, sm, cap=1000):
    q = kr*1.0 + kb*1.3 + sm*0.5
    qhr = round(q*4, 1)
    dj  = round(qhr/cap, 3) if cap > 0 else 0
    tp  = ('A' if dj<=0.35 else 'B' if dj<=0.54 else
           'C' if dj<=0.77 else 'D' if dj<=0.93 else
           'E' if dj<=1 else 'F')
    return qhr, dj, tp

# ══════════════════════════════════════════════════════════════════
#  BACKGROUND PROCESSING — memanggil DianaEngine nyata
# ══════════════════════════════════════════════════════════════════

def _safe_update(session_id, **kwargs):
    """Update VideoSession dengan aman dari thread background."""
    try:
        with app.app_context():
            VideoSession.query.filter_by(id=session_id).update(kwargs)
            db.session.commit()
    except Exception as e:
        print(f'[DIANA] _safe_update error: {e}')

def process_bg(session_id, video_path, road_name, cctv_date, cctv_time, n_lanes=4):
    """
    Background thread — memanggil DianaEngine (YOLO nyata atau demo).
    Semua path ABSOLUT sehingga tidak ada FileNotFoundError.
    """
    with app.app_context():
        try:
            _safe_update(session_id, status='processing', progress=2,
                         progress_msg='Memulai engine...')

            # Path output ABSOLUT
            out_video = os.path.join(RESULTS_DIR, f'{session_id}_out.mp4')
            out_excel = os.path.join(RESULTS_DIR, f'{session_id}.xlsx')

            print(f'[DIANA] Session: {session_id}')
            print(f'[DIANA] Input : {video_path}')
            print(f'[DIANA] Video : {out_video}')
            print(f'[DIANA] Excel : {out_excel}')

            # Validasi file input ada
            if not os.path.exists(video_path):
                raise FileNotFoundError(f'File video tidak ditemukan: {video_path}')

            # Parse CCTV datetime
            try:
                cctv_dt = datetime.strptime(f'{cctv_date} {cctv_time}', '%Y-%m-%d %H:%M')
            except Exception:
                cctv_dt = datetime.now()

            # Load engine
            sys.path.insert(0, BASE_DIR)
            from diana_engine import DianaEngine

            model_path = SiteConfig.get('model_path', 'yolov8n.pt')
            # Cari model di BASE_DIR juga
            model_full = os.path.join(BASE_DIR, model_path)
            if os.path.exists(model_full):
                model_path = model_full

            engine = DianaEngine(
                model_path   = model_path,
                conf         = float(SiteConfig.get('conf_threshold', '0.28')),
                n_lanes      = int(n_lanes),
                ppm_override = None,
                road_name    = road_name,
                cctv_dt      = cctv_dt,
                capacity     = int(SiteConfig.get('capacity_default', '1000')),
            )

            # Progress callback
            def progress_cb(pct, msg=''):
                _safe_update(session_id,
                             progress=min(int(pct), 99),
                             status='processing',
                             progress_msg=str(msg)[:200])

            # Jalankan engine
            result = engine.process(
                video_in    = video_path,
                video_out   = out_video,
                excel_out   = out_excel,
                progress_cb = progress_cb,
                stop_ev     = None,
            )

            # Update session hasil
            vs = VideoSession.query.get(session_id)
            vs.total_veh  = result.get('total_veh', 0)
            vs.total_kr   = result.get('total_kr',  0)
            vs.total_kb   = result.get('total_kb',  0)
            vs.total_sm   = result.get('total_sm',  0)
            vs.avg_speed  = result.get('avg_speed', 0)
            vs.max_speed  = result.get('max_speed', 0)
            vs.danger_ev  = result.get('danger_ev', 0)
            vs.warning_ev = result.get('warning_ev',0)
            vs.q_smp      = result.get('q_smp',     0)
            vs.dj         = result.get('dj',        0)
            vs.tp         = result.get('tp',       'B')
            vs.status     = 'done'
            vs.progress   = 100
            vs.progress_msg = 'Selesai!'

            # Simpan path file jika ada
            if os.path.exists(out_video):
                vs.video_out_path = out_video
                vs.has_video      = True
                print(f'[DIANA] Video output: {os.path.getsize(out_video)//1024} KB')
            else:
                print(f'[DIANA] WARNING: video output tidak ditemukan: {out_video}')

            if os.path.exists(out_excel):
                vs.excel_path = out_excel
                vs.has_excel  = True
                print(f'[DIANA] Excel output: {os.path.getsize(out_excel)//1024} KB')
            else:
                print(f'[DIANA] WARNING: excel tidak ditemukan: {out_excel}')

            db.session.commit()

            # Simpan DangerEvents ke DB
            for e in result.get('events', []):
                db.session.add(DangerEvent(
                    session_id       = session_id,
                    timestamp_s      = e.get('ts', 0),
                    frame_no         = e.get('frame', 0),
                    ttc_value        = e.get('ttc', 0),
                    category         = e.get('category', ''),
                    v_back           = e.get('v_back', 0),
                    v_front          = e.get('v_front', 0),
                    distance_m       = e.get('dist_m', 0),
                    lane             = e.get('lane', ''),
                    vehicle_id_back  = e.get('vid_b', ''),
                    vehicle_id_front = e.get('vid_f', ''),
                ))
            db.session.commit()

            print(f'[DIANA] SELESAI: {vs.total_veh} kendaraan, '
                  f'{vs.danger_ev} bahaya, TP={vs.tp}')

            # Tambah titik peta baru jika belum ada
            existing = [s.jalan for s in MapSpot.query.all()]
            if road_name and road_name not in existing:
                rng2 = random.Random(hash(session_id) % 9999)
                db.session.add(MapSpot(
                    nama       = f'Lokasi: {road_name}',
                    jalan      = road_name,
                    lat        = -7.4214 + rng2.uniform(-0.04, 0.04),
                    lng        = 109.2403 + rng2.uniform(-0.04, 0.04),
                    tingkat    = 'Perlu Validasi',
                    kejadian   = vs.danger_ev,
                    keterangan = (f'Dianalisis DIANA. '
                                  f'Bahaya:{vs.danger_ev} Waspada:{vs.warning_ev} TP={vs.tp}'),
                    sumber     = 'User Upload',
                    session_id = session_id,
                ))
                db.session.commit()

        except Exception as exc:
            import traceback
            print(f'[DIANA ERROR] {session_id}: {exc}')
            traceback.print_exc()
            _safe_update(session_id, status='error', progress=0,
                         progress_msg=str(exc)[:200])

# ══════════════════════════════════════════════════════════════════
#  PUBLIC ROUTES
# ══════════════════════════════════════════════════════════════════

@app.route('/')
def home():
    u = current_user()
    if u:
        my = VideoSession.query.filter_by(user_id=u.id, status='done').all()
        stats = {
            'total_sessions': len(my),
            'total_danger':   sum(s.danger_ev for s in my),
            'total_vehicles': sum(s.total_veh for s in my),
            'total_users':    User.query.count(),
        }
    else:
        stats = {'total_sessions':0,'total_danger':0,'total_vehicles':0,'total_users':0}
    news = NewsItem.query.filter_by(is_active=True)\
                         .order_by(NewsItem.created_at.desc()).limit(3).all()
    return render_template('index.html', stats=stats, news=news)

@app.route('/dashboard')
def dashboard():
    u = current_user()
    if u and u.role == 'admin':
        sessions = VideoSession.query.filter_by(status='done')\
                               .order_by(VideoSession.upload_date.desc()).all()
    elif u:
        sessions = VideoSession.query.filter_by(user_id=u.id, status='done')\
                               .order_by(VideoSession.upload_date.desc()).all()
    else:
        sessions = []

    total_dg  = sum(s.danger_ev  for s in sessions)
    total_veh = sum(s.total_veh  for s in sessions)
    total_kr  = sum(s.total_kr   for s in sessions)
    total_kb  = sum(s.total_kb   for s in sessions)
    total_sm  = sum(s.total_sm   for s in sessions)
    avg_spd   = round(sum(s.avg_speed for s in sessions)/max(1,len(sessions)),1) if sessions else 0
    avg_dj    = round(sum(s.dj for s in sessions)/max(1,len(sessions)),3) if sessions else 0

    hours = [f'{h:02d}:00' for h in range(6,22)]
    hc = {h:0 for h in hours}
    for s in sessions:
        if s.cctv_time:
            hr = s.cctv_time.split(':')[0]+':00'
            if hr in hc: hc[hr] += s.danger_ev

    return render_template('dashboard.html',
        sessions=sessions, total_dg=total_dg, total_wn=sum(s.warning_ev for s in sessions),
        total_veh=total_veh, total_kr=total_kr, total_kb=total_kb, total_sm=total_sm,
        avg_spd=avg_spd, avg_dj=avg_dj, is_empty=len(sessions)==0,
        hours=json.dumps(hours),
        hdanger=json.dumps([hc[h] for h in hours]),
        pie_data=json.dumps([total_kr, total_kb, total_sm]))

@app.route('/peta')
def peta():
    spots = MapSpot.query.order_by(MapSpot.kejadian.desc()).all()
    spots_json = json.dumps([{
        'lat':s.lat,'lng':s.lng,'nama':s.nama,'jalan':s.jalan,
        'tingkat':s.tingkat,'kejadian':s.kejadian,
        'ket':s.keterangan,'sumber':s.sumber
    } for s in spots])
    stats = {
        'tinggi':  sum(1 for s in spots if s.tingkat=='Tinggi'),
        'sedang':  sum(1 for s in spots if s.tingkat=='Sedang'),
        'rendah':  sum(1 for s in spots if s.tingkat=='Rendah'),
        'baru':    sum(1 for s in spots if s.sumber=='User Upload'),
        'total_kejadian': sum(s.kejadian for s in spots),
    }
    return render_template('peta.html', spots=spots_json, stats=stats)

@app.route('/edukasi')
def edukasi():
    news = NewsItem.query.filter_by(is_active=True)\
                         .order_by(NewsItem.created_at.desc()).limit(9).all()
    return render_template('edukasi.html', news=news)

# ══════════════════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════════════════

@app.route('/login', methods=['GET','POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('home'))
    if request.method == 'POST':
        ident = request.form.get('identifier','').strip()
        pw    = request.form.get('password','')
        u = User.query.filter(
            (User.username==ident)|(User.email==ident)).first()
        if u and u.is_active and check_password_hash(u.password, pw):
            session.update({'user_id':u.id,'username':u.username,'role':u.role})
            flash(f'Selamat datang, {u.username}!','success')
            return redirect(url_for('admin_dash') if u.role=='admin' else url_for('home'))
        flash('Username/email atau password salah.','danger')
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        un = request.form.get('username','').strip()
        em = request.form.get('email','').strip()
        pw = request.form.get('password','')
        cf = request.form.get('confirm','')
        if len(un) < 3:
            flash('Username minimal 3 karakter.','danger')
        elif User.query.filter_by(username=un).first():
            flash('Username sudah terdaftar.','danger')
        elif User.query.filter_by(email=em).first():
            flash('Email sudah terdaftar.','danger')
        elif pw != cf:
            flash('Password tidak cocok.','danger')
        elif len(pw) < 6:
            flash('Password minimal 6 karakter.','danger')
        else:
            db.session.add(User(username=un, email=em,
                                password=generate_password_hash(pw)))
            db.session.commit()
            flash('Registrasi berhasil! Silakan login.','success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Berhasil logout.','info')
    return redirect(url_for('login'))

# ══════════════════════════════════════════════════════════════════
#  USER ROUTES
# ══════════════════════════════════════════════════════════════════

@app.route('/upload', methods=['GET','POST'])
@login_required
def upload():
    if request.method == 'POST':
        f = request.files.get('video')
        if not f or not f.filename.lower().endswith('.mp4'):
            flash('Pilih file video format MP4.','danger')
            return redirect(request.url)

        sid   = str(uuid.uuid4())
        fname = f'{sid}.mp4'
        # Simpan ke path ABSOLUT
        fpath = os.path.join(UPLOAD_DIR, fname)
        f.save(fpath)
        print(f'[DIANA] Upload saved: {fpath} ({os.path.getsize(fpath)//1024} KB)')

        road    = request.form.get('road_name','Simpang Purwokerto').strip()
        cctv_d  = request.form.get('cctv_date', datetime.now().strftime('%Y-%m-%d'))
        cctv_t  = request.form.get('cctv_time', '08:00')
        n_lns   = int(request.form.get('n_lanes', '4'))

        vs = VideoSession(
            id=sid, user_id=session['user_id'],
            filename=fname, orig_name=f.filename,
            road_name=road, cctv_date=cctv_d,
            cctv_time=cctv_t, n_lanes=n_lns,
            status='pending', progress=0,
        )
        db.session.add(vs); db.session.commit()

        threading.Thread(
            target=process_bg,
            args=(sid, fpath, road, cctv_d, cctv_t, n_lns),
            daemon=True
        ).start()

        flash('Video berhasil diunggah! Analisis dimulai.','success')
        return redirect(url_for('riwayat'))

    return render_template('upload.html',
                           now_date=datetime.now().strftime('%Y-%m-%d'))

@app.route('/riwayat')
@login_required
def riwayat():
    u = current_user()
    if u.role == 'admin':
        sessions = VideoSession.query.order_by(VideoSession.upload_date.desc()).all()
    else:
        sessions = VideoSession.query.filter_by(user_id=u.id)\
                               .order_by(VideoSession.upload_date.desc()).all()
    pending = sum(1 for s in sessions if s.status in ('pending','processing'))
    return render_template('riwayat.html', sessions=sessions, pending=pending)

@app.route('/hasil/<sid>')
@login_required
def hasil(sid):
    vs = VideoSession.query.get_or_404(sid)
    u  = current_user()
    if u.role != 'admin' and vs.user_id != u.id:
        flash('Akses ditolak.','danger'); return redirect(url_for('riwayat'))
    events  = DangerEvent.query.filter_by(session_id=sid)\
                               .order_by(DangerEvent.timestamp_s).all()
    danger  = [e for e in events if e.category=='BAHAYA']
    warning = [e for e in events if e.category=='WASPADA']
    return render_template('hasil.html',
        vs=vs, events=events, danger=danger, warning=warning,
        ttc_t=json.dumps([round(e.timestamp_s,1) for e in events]),
        ttc_v=json.dumps([e.ttc_value for e in events]))

# ══════════════════════════════════════════════════════════════════
#  DOWNLOAD ROUTES — path ABSOLUT, tidak akan FileNotFoundError
# ══════════════════════════════════════════════════════════════════

@app.route('/download/excel/<sid>')
@login_required
def download_excel(sid):
    vs = VideoSession.query.get_or_404(sid)
    u  = current_user()
    if u.role != 'admin' and vs.user_id != u.id:
        flash('Akses ditolak.','danger'); return redirect(url_for('riwayat'))

    # Cek path yang tersimpan di DB
    xl_path = vs.excel_path
    if xl_path and os.path.exists(xl_path):
        return send_file(
            xl_path, as_attachment=True,
            download_name=f'DIANA_{vs.road_name.replace(" ","_")}_{vs.cctv_date}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    # Fallback: coba path default
    xl_default = os.path.join(RESULTS_DIR, f'{sid}.xlsx')
    if os.path.exists(xl_default):
        return send_file(
            xl_default, as_attachment=True,
            download_name=f'DIANA_{vs.road_name.replace(" ","_")}_{vs.cctv_date}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    # Tidak ditemukan
    flash(f'File Excel belum tersedia. Status: {vs.status}. '
          f'Pastikan proses selesai (100%) sebelum download.', 'warning')
    return redirect(url_for('hasil', sid=sid))

@app.route('/download/video/<sid>')
@login_required
def download_video(sid):
    vs = VideoSession.query.get_or_404(sid)
    u  = current_user()
    if u.role != 'admin' and vs.user_id != u.id:
        flash('Akses ditolak.','danger'); return redirect(url_for('riwayat'))

    # Cek path tersimpan di DB
    vid_path = vs.video_out_path
    if vid_path and os.path.exists(vid_path):
        return send_file(
            vid_path, as_attachment=True,
            download_name=f'DIANA_annotated_{vs.road_name.replace(" ","_")}_{vs.cctv_date}.mp4',
            mimetype='video/mp4')

    # Fallback: path default
    vid_default = os.path.join(RESULTS_DIR, f'{sid}_out.mp4')
    if os.path.exists(vid_default):
        return send_file(
            vid_default, as_attachment=True,
            download_name=f'DIANA_annotated_{vs.road_name.replace(" ","_")}_{vs.cctv_date}.mp4',
            mimetype='video/mp4')

    # Coba video original sebagai fallback terakhir
    vid_orig = os.path.join(UPLOAD_DIR, vs.filename or '')
    if vs.filename and os.path.exists(vid_orig):
        flash('Video anotasi belum tersedia, mengunduh video original.', 'info')
        return send_file(
            vid_orig, as_attachment=True,
            download_name=f'DIANA_original_{vs.orig_name}',
            mimetype='video/mp4')

    flash('File video tidak ditemukan. Pastikan proses selesai dulu.', 'warning')
    return redirect(url_for('hasil', sid=sid))

# ══════════════════════════════════════════════════════════════════
#  API
# ══════════════════════════════════════════════════════════════════

@app.route('/api/progress/<sid>')
def api_progress(sid):
    vs = VideoSession.query.get_or_404(sid)
    return jsonify({
        'status':    vs.status,
        'progress':  vs.progress,
        'msg':       vs.progress_msg or '',
        'danger_ev': vs.danger_ev,
        'total_veh': vs.total_veh,
        'has_excel': vs.has_excel,
        'has_video': vs.has_video,
    })

@app.route('/api/pending-count')
@login_required
def api_pending():
    u = current_user()
    q = VideoSession.query
    if u.role != 'admin':
        q = q.filter_by(user_id=u.id)
    n = q.filter(VideoSession.status.in_(['pending','processing'])).count()
    return jsonify({'count': n})

# ══════════════════════════════════════════════════════════════════
#  ADMIN
# ══════════════════════════════════════════════════════════════════

@app.route('/admin')
@admin_required
def admin_dash():
    total_users    = User.query.count()
    total_sessions = VideoSession.query.count()
    total_done     = VideoSession.query.filter_by(status='done').count()
    total_danger   = db.session.query(db.func.sum(VideoSession.danger_ev)).scalar() or 0
    recent         = VideoSession.query.order_by(VideoSession.upload_date.desc()).limit(10).all()
    from sqlalchemy import func
    users_stats = db.session.query(
        User.username,
        func.count(VideoSession.id).label('cnt'),
        func.sum(VideoSession.danger_ev).label('dg')
    ).outerjoin(VideoSession, User.id==VideoSession.user_id)\
     .group_by(User.id).all()
    return render_template('admin/index.html',
        total_users=total_users, total_sessions=total_sessions,
        total_done=total_done, total_danger=total_danger,
        recent_sessions=recent, users_stats=users_stats)

@app.route('/admin/users')
@admin_required
def admin_users():
    return render_template('admin/users.html',
                           users=User.query.order_by(User.created_at.desc()).all())

@app.route('/admin/users/toggle/<int:uid>', methods=['POST'])
@admin_required
def admin_toggle_user(uid):
    u = User.query.get_or_404(uid)
    u.is_active = not u.is_active
    db.session.commit()
    return jsonify({'ok':True,'active':u.is_active})

@app.route('/admin/berita')
@admin_required
def admin_berita():
    return render_template('admin/berita.html',
                           news=NewsItem.query.order_by(NewsItem.created_at.desc()).all())

@app.route('/admin/berita/tambah', methods=['GET','POST'])
@admin_required
def admin_berita_tambah():
    if request.method == 'POST':
        db.session.add(NewsItem(
            title    = request.form.get('title','').strip(),
            content  = request.form.get('content','').strip(),
            category = request.form.get('category','berita'),
            video_url= convert_yt(request.form.get('video_url','')),
            image_url= request.form.get('image_url','').strip(),
            author   = current_user().username,
        ))
        db.session.commit()
        flash('Berita ditambahkan.','success')
        return redirect(url_for('admin_berita'))
    return render_template('admin/berita_form.html', item=None)

@app.route('/admin/berita/edit/<int:nid>', methods=['GET','POST'])
@admin_required
def admin_berita_edit(nid):
    n = NewsItem.query.get_or_404(nid)
    if request.method == 'POST':
        n.title     = request.form.get('title','').strip()
        n.content   = request.form.get('content','').strip()
        n.category  = request.form.get('category','berita')
        n.video_url = convert_yt(request.form.get('video_url',''))
        n.image_url = request.form.get('image_url','').strip()
        n.is_active = 'is_active' in request.form
        db.session.commit()
        flash('Berita diperbarui.','success')
        return redirect(url_for('admin_berita'))
    return render_template('admin/berita_form.html', item=n)

@app.route('/admin/berita/hapus/<int:nid>', methods=['POST'])
@admin_required
def admin_berita_hapus(nid):
    n = NewsItem.query.get_or_404(nid)
    db.session.delete(n); db.session.commit()
    flash('Berita dihapus.','success')
    return redirect(url_for('admin_berita'))

@app.route('/admin/config', methods=['GET','POST'])
@admin_required
def admin_config():
    if request.method == 'POST':
        for k in ['ppm_default','capacity_default','telegram_token',
                  'telegram_chat','model_path','conf_threshold']:
            v = request.form.get(k,'')
            if v: SiteConfig.set(k, v)
        flash('Konfigurasi disimpan.','success')
    cfg = {k: SiteConfig.get(k, d) for k, d in [
        ('ppm_default','20'),('capacity_default','1000'),
        ('telegram_token',''),('telegram_chat',''),
        ('model_path','yolov8n.pt'),('conf_threshold','0.28'),
    ]}
    return render_template('admin/config.html', cfg=cfg)

# ══════════════════════════════════════════════════════════════════
#  SEED DATA
# ══════════════════════════════════════════════════════════════════

BANYUMAS_SPOTS = [
    {"nama":"Simpang Purwokerto–Wangon–Bumiayu","jalan":"Jl. Gerilya / Jl. Sudirman (Titik Penelitian DIANA)",
     "lat":-7.4232,"lng":109.2398,"tingkat":"Tinggi","kejadian":35,
     "keterangan":"Simpang 3 arah utama. Volume LHR tertinggi Kab. Banyumas. (Dishub Banyumas 2023)"},
    {"nama":"Simpang Ajibarang Barat","jalan":"Jl. Raya Ajibarang–Wangon",
     "lat":-7.4196,"lng":109.0637,"tingkat":"Tinggi","kejadian":23,
     "keterangan":"Simpang 3 arah, banyak kecelakaan kendaraan berat. (Polres Banyumas 2022)"},
    {"nama":"Ruas Wangon – Prupuk","jalan":"Jl. Raya Wangon–Prupuk (Jalur Nasional)",
     "lat":-7.4723,"lng":109.0127,"tingkat":"Tinggi","kejadian":31,
     "keterangan":"Volume truk berat tinggi, TTC kritis. (Jurnal Sipil UMP 2023)"},
    {"nama":"Simpang Sokaraja","jalan":"Jl. Raya Sokaraja–Purwokerto",
     "lat":-7.3843,"lng":109.2874,"tingkat":"Tinggi","kejadian":28,
     "keterangan":"Persimpangan padat kawasan industri. (Dishub 2023)"},
    {"nama":"Ruas Rawalo","jalan":"Jl. Raya Rawalo (Purwokerto–Cilacap)",
     "lat":-7.5298,"lng":109.2012,"tingkat":"Sedang","kejadian":15,
     "keterangan":"Tikungan tajam, rawan saat hujan."},
    {"nama":"Sumpiuh – Petarukan","jalan":"Jl. Raya Sumpiuh (Jalur Nasional Timur)",
     "lat":-7.5694,"lng":109.3581,"tingkat":"Sedang","kejadian":18,
     "keterangan":"Overspeed dominan menjadi penyebab utama."},
    {"nama":"Jl. Ahmad Yani Purwokerto","jalan":"Jl. Ahmad Yani (Kota Purwokerto)",
     "lat":-7.4175,"lng":109.2290,"tingkat":"Sedang","kejadian":12,
     "keterangan":"Mixed traffic tinggi, jam sibuk padat."},
    {"nama":"Banyumas Kota","jalan":"Jl. Raya Banyumas (Kota Lama)",
     "lat":-7.5285,"lng":109.2923,"tingkat":"Sedang","kejadian":14,
     "keterangan":"Kawasan komersial, rawan di persimpangan."},
    {"nama":"Cilongok","jalan":"Jl. Raya Cilongok (Kec. Cilongok)",
     "lat":-7.3882,"lng":109.0128,"tingkat":"Sedang","kejadian":16,
     "keterangan":"Tikungan berbahaya, aspal bergelombang."},
    {"nama":"Sumbang","jalan":"Jl. Raya Sumbang (Kec. Sumbang)",
     "lat":-7.3671,"lng":109.2537,"tingkat":"Sedang","kejadian":13,
     "keterangan":"Jalur distribusi barang utara Purwokerto."},
    {"nama":"Baturaden","jalan":"Jl. Raya Baturaden (Jalur Wisata)",
     "lat":-7.3132,"lng":109.2125,"tingkat":"Sedang","kejadian":11,
     "keterangan":"Tanjakan berbahaya, hari libur padat."},
    {"nama":"Karanglewas","jalan":"Jl. Raya Karanglewas",
     "lat":-7.4123,"lng":109.1567,"tingkat":"Rendah","kejadian":8,
     "keterangan":"Jalan penghubung, volume sedang."},
    {"nama":"Kembaran","jalan":"Jl. Raya Kembaran",
     "lat":-7.4398,"lng":109.3008,"tingkat":"Rendah","kejadian":7,
     "keterangan":"Pinggiran Purwokerto, berkembang pesat."},
    {"nama":"Tambak","jalan":"Jl. Raya Tambak (Kec. Tambak)",
     "lat":-7.6009,"lng":109.1456,"tingkat":"Rendah","kejadian":9,
     "keterangan":"Geometrik jalan buruk, visibilitas rendah."},
    {"nama":"Lumbir","jalan":"Jl. Raya Lumbir (Kec. Lumbir)",
     "lat":-7.4895,"lng":109.0234,"tingkat":"Rendah","kejadian":6,
     "keterangan":"Volume rendah, kondisi jalan perlu perhatian."},
]

def seed():
    if User.query.count() > 0:
        return
    db.session.add(User(username='admin', email='admin@diana.id',
                        password=generate_password_hash('admin123'), role='admin'))
    db.session.add(User(username='demo', email='demo@diana.id',
                        password=generate_password_hash('demo123'), role='user'))
    db.session.commit()

    for s in BANYUMAS_SPOTS:
        db.session.add(MapSpot(**s, sumber='Penelitian'))

    news = [
        ('Waspadai Simpang Rawan di Kabupaten Banyumas',
         'Dinas Perhubungan Banyumas mengimbau pengemudi waspada di simpang rawan. '
         'Data Korlantas Polres Banyumas 2022–2024 menunjukkan 65% kecelakaan akibat '
         'gagal jaga jarak aman.',
         'berita','','https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600'),
        ('YOLOv8 untuk Deteksi Kendaraan Real-Time di ATCS',
         'Platform DIANA menggunakan YOLOv8 + ByteTrack untuk mendeteksi KR, KB, SM '
         'dari rekaman CCTV ATCS secara real-time sesuai standar PKJI 2023.',
         'berita','','https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=600'),
        ('Tips Aman Berkendara di Musim Hujan',
         'Kurangi kecepatan 30%, jaga jarak 2x normal, cek rem dan ban sebelum berkendara.',
         'berita','','https://images.unsplash.com/photo-1504701954957-2010ec3bcec1?w=600'),
        ('Video: Kampanye Keselamatan Jalan Dishub',
         'Tonton video edukasi keselamatan berkendara. Klik untuk menonton di YouTube.',
         'video','https://www.youtube.com/embed/c0RQzXMQJvA',''),
    ]
    for t,c,cat,vid,img in news:
        db.session.add(NewsItem(title=t,content=c,category=cat,
                                video_url=vid,image_url=img,author='Admin'))
    db.session.commit()
    print('[DIANA] Database seeded (dashboard kosong untuk user baru).')

# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed()
    print(f'[DIANA] BASE_DIR:    {BASE_DIR}')
    print(f'[DIANA] UPLOAD_DIR:  {UPLOAD_DIR}')
    print(f'[DIANA] RESULTS_DIR: {RESULTS_DIR}')
    print('[DIANA] Buka: http://localhost:5000')
    app.run(debug=True, port=5000, threaded=True)
