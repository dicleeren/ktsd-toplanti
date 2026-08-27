import os
import uuid
import csv
import io
import tempfile
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, session
from flask_sqlalchemy import SQLAlchemy
from jinja2 import DictLoader

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ktsd-sec-key-2026-secret-poll-token-auth-restricted'

# Writable temporary database path
db_dir = tempfile.gettempdir()
db_path = os.path.join(db_dir, 'ktsd_poll.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Default KTSD Staff Emails
DEFAULT_STAFF_EMAILS = [
    "toplanti@ktsd.org.tr",
    "info@ktsd.org.tr",
    "sekreterya@ktsd.org.tr",
    "yonetim@ktsd.org.tr"
]

# Database Models
class Poll(db.Model):
    __tablename__ = 'polls'
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(32), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    organizer_name = db.Column(db.String(120), nullable=False)
    organizer_company = db.Column(db.String(150), nullable=True)
    authorized_emails = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='active')
    final_option_id = db.Column(db.Integer, nullable=True)

    options = db.relationship('Option', backref='poll', cascade='all, delete-orphan', order_by='Option.order_num')
    votes = db.relationship('Vote', backref='poll', cascade='all, delete-orphan', order_by='Vote.created_at.desc()')

    def get_authorized_email_list(self):
        if not self.authorized_emails:
            return DEFAULT_STAFF_EMAILS
        emails = [e.strip().lower() for e in self.authorized_emails.split(',') if e.strip()]
        return emails if emails else DEFAULT_STAFF_EMAILS

class Option(db.Model):
    __tablename__ = 'options'
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('polls.id'), nullable=False)
    date_val = db.Column(db.String(100), nullable=False)
    time_val = db.Column(db.String(100), nullable=False)
    order_num = db.Column(db.Integer, default=0)

    vote_details = db.relationship('VoteDetail', backref='option', cascade='all, delete-orphan')

class Vote(db.Model):
    __tablename__ = 'votes'
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('polls.id'), nullable=False)
    member_name = db.Column(db.String(120), nullable=False)
    member_company = db.Column(db.String(150), nullable=True)
    member_email = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    details = db.relationship('VoteDetail', backref='vote', cascade='all, delete-orphan')

class VoteDetail(db.Model):
    __tablename__ = 'vote_details'
    id = db.Column(db.Integer, primary_key=True)
    vote_id = db.Column(db.Integer, db.ForeignKey('votes.id'), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey('options.id'), nullable=False)
    status = db.Column(db.String(10), nullable=False)

def init_db():
    try:
        with app.app_context():
            db.create_all()
    except Exception as e:
        print("Init DB error:", e)

init_db()

# EMBEDDED HTML TEMPLATES (Zero external file dependencies)
BASE_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}KTSD Toplantı ve Tarih Belirleme Portalı{% endblock %}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    :root {
      --ktsd-blue: #005BB5;
      --ktsd-blue-dark: #003D7A;
      --ktsd-blue-light: #0284C7;
      --bg-light: #F4F7FA;
      --card-bg: #FFFFFF;
      --status-yes-bg: #ECFDF5; --status-yes-color: #065F46; --status-yes-btn: #10B981;
      --status-maybe-bg: #FFFBEB; --status-maybe-color: #92400E; --status-maybe-btn: #F59E0B;
      --status-no-bg: #FEF2F2; --status-no-color: #991B1B; --status-no-btn: #EF4444;
      --radius-sm: 8px; --radius-md: 14px;
      --shadow-md: 0 10px 25px -5px rgba(0, 91, 181, 0.12);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Inter', sans-serif; background: var(--bg-light); color: #1E293B; line-height: 1.6; min-height: 100vh; display: flex; flex-direction: column; }
    .ktsd-header { background: #FFFFFF; padding: 1rem 2rem; box-shadow: 0 4px 20px rgba(0, 61, 122, 0.1); sticky: top: 0; z-index: 100; border-bottom: 4px solid var(--ktsd-blue); }
    .header-container { max-width: 1200px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }
    .ktsd-brand { display: flex; align-items: center; gap: 1rem; text-decoration: none; color: #1E293B; }
    .ktsd-logo-badge { background: var(--ktsd-blue); color: white; padding: 0.4rem 0.8rem; border-radius: 10px; font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 1.2rem; }
    .brand-text h1 { font-family: 'Outfit', sans-serif; font-size: 1.3rem; font-weight: 700; color: var(--ktsd-blue-dark); }
    .brand-text p { font-size: 0.78rem; color: #64748B; }
    .btn-header { background: var(--ktsd-blue); color: white; padding: 0.6rem 1.2rem; border-radius: var(--radius-sm); text-decoration: none; font-size: 0.88rem; font-weight: 600; }
    .btn-header:hover { background: var(--ktsd-blue-dark); }
    .btn-header-outline { border: 1.5px solid var(--ktsd-blue-dark); color: var(--ktsd-blue-dark); padding: 0.6rem 1.2rem; border-radius: var(--radius-sm); text-decoration: none; font-size: 0.88rem; font-weight: 600; }
    .main-wrapper { max-width: 1200px; margin: 2rem auto; padding: 0 1.5rem; flex: 1; width: 100%; }
    .card { background: white; border-radius: var(--radius-md); box-shadow: var(--shadow-md); border: 1px solid #E2E8F0; padding: 2rem; margin-bottom: 2rem; }
    .card-header { border-bottom: 2px solid #F1F5F9; padding-bottom: 1rem; margin-bottom: 1.5rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; }
    .hero-section { background: linear-gradient(135deg, #005BB5 0%, #003D7A 100%); color: white; padding: 2rem; border-radius: var(--radius-md); margin-bottom: 2rem; }
    .form-group { margin-bottom: 1.25rem; }
    .form-label { display: block; font-weight: 600; font-size: 0.9rem; color: var(--ktsd-blue-dark); margin-bottom: 0.4rem; }
    .form-control { width: 100%; padding: 0.75rem 1rem; font-size: 0.95rem; border: 1.5px solid #CBD5E1; border-radius: var(--radius-sm); }
    .btn-primary { background: var(--ktsd-blue); color: white; padding: 0.85rem 1.75rem; border-radius: var(--radius-sm); border: none; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 0.5rem; justify-content: center; }
    .btn-primary:hover { background: var(--ktsd-blue-dark); }
    .btn-teal { background: #10B981; color: white; padding: 0.85rem 1.75rem; border-radius: var(--radius-sm); border: none; font-weight: 600; cursor: pointer; }
    .btn-outline { border: 1.5px solid var(--ktsd-blue-dark); color: var(--ktsd-blue-dark); padding: 0.5rem 1rem; border-radius: var(--radius-sm); text-decoration: none; font-weight: 600; font-size: 0.88rem; background: transparent; cursor: pointer; }
    .option-row { display: grid; grid-template-columns: 1fr 1fr 45px; gap: 0.75rem; align-items: center; margin-bottom: 0.75rem; background: #F8FAFC; padding: 0.75rem; border-radius: var(--radius-sm); border: 1px dashed #CBD5E1; }
    .btn-remove-row { background: #FEE2E2; color: #EF4444; border: 1px solid #FECACA; width: 40px; height: 40px; border-radius: 6px; cursor: pointer; }
    .share-banner { background: #003D7A; color: white; padding: 1.25rem 1.5rem; border-radius: var(--radius-md); margin-bottom: 1.5rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; }
    .matrix-table { width: 100%; border-collapse: collapse; text-align: center; font-size: 0.9rem; }
    .matrix-table th, .matrix-table td { padding: 0.85rem; border: 1px solid #E2E8F0; }
    .matrix-table th { background: #F8FAFC; color: var(--ktsd-blue-dark); font-weight: 600; }
    .badge-status { width: 32px; height: 32px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: 700; }
    .badge-yes { background: #ECFDF5; color: #065F46; border: 2px solid #A7F3D0; }
    .badge-maybe { background: #FFFBEB; color: #92400E; border: 2px solid #FDE68A; }
    .badge-no { background: #FEF2F2; color: #991B1B; border: 2px solid #FECACA; }
    .ktsd-footer { background: var(--ktsd-blue-dark); color: #93C5FD; padding: 1.5rem; text-align: center; font-size: 0.85rem; margin-top: auto; }
    .alert { padding: 0.85rem 1.25rem; border-radius: var(--radius-sm); margin-bottom: 1rem; font-size: 0.92rem; background: #ECFDF5; color: #065F46; border: 1px solid #A7F3D0; }
    .alert-danger { background: #FEF2F2; color: #991B1B; border-color: #FECACA; }
  </style>
</head>
<body>
  <header class="ktsd-header">
    <div class="header-container">
      <a href="{{ url_for('index') }}" class="ktsd-brand">
        <div class="ktsd-logo-badge">KTSD</div>
        <div class="brand-text">
          <h1>Toplantı Portalı</h1>
          <p>Kozmetik ve Temizlik Ürünleri Sanayicileri Derneği</p>
        </div>
      </a>
      <div class="header-actions">
        <a href="{{ url_for('index') }}" class="btn-header"><i class="fas fa-plus-circle"></i> Yeni Anket</a>
        <a href="https://www.ktsd.org.tr" target="_blank" class="btn-header-outline"><i class="fas fa-globe"></i> ktsd.org.tr</a>
      </div>
    </div>
  </header>
  <main class="main-wrapper">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="alert alert-{{ category }}"><span>{{ message }}</span></div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
  </main>
  <footer class="ktsd-footer">
    <p>&copy; 2026 KTSD - Kozmetik ve Temizlik Ürünleri Sanayicileri Derneği. Tüm hakları saklıdır.</p>
  </footer>
  <script>
    document.addEventListener('DOMContentLoaded', () => {
      const optContainer = document.getElementById('options-container');
      const addBtn = document.getElementById('add-option-btn');
      const autoGenBtn = document.getElementById('auto-gen-btn');
      const autoDate = document.getElementById('auto-gen-date');
      const durationSel = document.getElementById('meeting-duration');

      function addRow(d='', t='') {
        if (!optContainer) return;
        const row = document.createElement('div');
        row.className = 'option-row';
        row.innerHTML = `
          <div><input type="date" name="option_date[]" class="form-control" value="${d}" required></div>
          <div><input type="text" name="option_time[]" class="form-control" value="${t}" placeholder="Örn: 09:00 - 10:00"></div>
          <div><button type="button" class="btn-remove-row">×</button></div>
        `;
        optContainer.appendChild(row);
      }

      if (addBtn) addBtn.addEventListener('click', () => addRow());
      if (optContainer) optContainer.addEventListener('click', (e) => {
        if (e.target.classList.contains('btn-remove-row')) {
          if (optContainer.querySelectorAll('.option-row').length > 1) e.target.closest('.option-row').remove();
        }
      });

      if (autoGenBtn && autoDate && durationSel) {
        autoGenBtn.addEventListener('click', () => {
          const dateVal = autoDate.value;
          if (!dateVal) { alert('Lütfen tarih seçiniz.'); return; }
          const dur = parseInt(durationSel.value) || 60;
          let count = 0;
          for (let m = 540; m + dur <= 1020; m += dur) {
            const h1 = String(Math.floor(m/60)).padStart(2,'0'), m1 = String(m%60).padStart(2,'0');
            const h2 = String(Math.floor((m+dur)/60)).padStart(2,'0'), m2 = String((m+dur)%60).padStart(2,'0');
            addRow(dateVal, `${h1}:${m1} - ${h2}:${m2}`);
            count++;
          }
          alert(`${count} adet saat seçeneği eklendi!`);
        });
      }

      const copyBtn = document.getElementById('copy-share-url');
      const shareInp = document.getElementById('share-poll-url');
      if (copyBtn && shareInp) {
        copyBtn.addEventListener('click', () => {
          shareInp.select();
          navigator.clipboard.writeText(shareInp.value).then(() => { alert('Bağlantı kopyalandı!'); });
        });
      }
    });
  </script>
</body>
</html>"""

INDEX_HTML = """{% extends 'base.html' %}
{% block title %}Yeni Toplantı Anketi Oluştur - KTSD{% endblock %}
{% block content %}
<div class="hero-section">
  <h2><i class="fas fa-calendar-alt"></i> Kurumsal Toplantı Tarihi Planlayıcı</h2>
  <p>KTSD Yönetim Kurulu ve Komite toplantılarınız için üyelere anket bağlantısı gönderin. Üyeler sadece tarih seçimi yapabilir; toplu sonuçlar yetkili KTSD çalışanlarına özeldir.</p>
</div>
<div style="display: grid; grid-template-columns: 2fr 1fr; gap: 2rem;">
  <div class="card">
    <div class="card-header">
      <h3 style="font-family:'Outfit',sans-serif; color:var(--ktsd-blue-dark);"><i class="fas fa-edit"></i> Yeni Toplantı Anketi Oluştur</h3>
    </div>
    <form action="{{ url_for('create_poll') }}" method="POST">
      <div class="form-group">
        <label class="form-label">Toplantı Başlığı / Konusu *</label>
        <input type="text" name="title" class="form-control" placeholder="Örn: 2026 3. Çeyrek Yönetim Kurulu Toplantısı" required>
      </div>
      <div class="form-group">
        <label class="form-label">Toplantı Açıklaması / Gündemi</label>
        <textarea name="description" class="form-control" placeholder="Gündem ve konum notları..."></textarea>
      </div>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
        <div class="form-group">
          <label class="form-label">Düzenleyen Ad Soyad *</label>
          <input type="text" name="organizer_name" class="form-control" placeholder="Örn: Ahmet Yılmaz" required>
        </div>
        <div class="form-group">
          <label class="form-label">Kurum / Görev</label>
          <input type="text" name="organizer_company" class="form-control" placeholder="Örn: KTSD Genel Sekreterliği">
        </div>
      </div>
      <div class="form-group" style="background:#F0F9FF; padding:1rem; border-radius:8px; border:1px solid #BAE6FD;">
        <label class="form-label" style="color:#0369A1;"><i class="fas fa-user-shield"></i> Sonuçları Görmeye Yetkili KTSD E-posta Adresleri</label>
        <input type="text" name="authorized_emails" class="form-control" value="{{ default_emails_str }}">
      </div>
      <div style="background:#F8FAFC; border:1px solid #CBD5E1; padding:1.25rem; border-radius:8px; margin-bottom:1.5rem;">
        <h4 style="color:var(--ktsd-blue-dark); margin-bottom:0.5rem;"><i class="fas fa-magic"></i> Otomatik Saat Üretici (09:00 - 17:00)</h4>
        <div style="display:grid; grid-template-columns: 1fr 1.2fr 1.5fr; gap:1rem; align-items:flex-end;">
          <div>
            <label class="form-label">Toplantı Süresi</label>
            <select id="meeting-duration" class="form-control">
              <option value="60" selected>1 Saat (60 Dk)</option>
              <option value="30">30 Dakika</option>
              <option value="45">45 Dakika</option>
            </select>
          </div>
          <div>
            <label class="form-label">Tarih Seçin</label>
            <input type="date" id="auto-gen-date" class="form-control">
          </div>
          <div>
            <button type="button" id="auto-gen-btn" class="btn-primary" style="width:100%;"><i class="fas fa-bolt"></i> 09:00-17:00 Saatlerini Üret</button>
          </div>
        </div>
      </div>
      <div class="form-group">
        <label class="form-label"><i class="fas fa-clock"></i> Alternatif Tarih ve Saat Listesi *</label>
        <div id="options-container">
          <div class="option-row">
            <div><input type="date" name="option_date[]" class="form-control" required></div>
            <div><input type="text" name="option_time[]" class="form-control" placeholder="Örn: 09:00 - 10:00"></div>
            <div><button type="button" class="btn-remove-row">×</button></div>
          </div>
        </div>
        <button type="button" id="add-option-btn" class="btn-outline" style="width:100%; margin-top:0.5rem;"><i class="fas fa-plus"></i> Seçenek Ekle</button>
      </div>
      <button type="submit" class="btn-primary" style="width:100%; font-size:1.05rem;"><i class="fas fa-paper-plane"></i> Anketi Oluştur ve Linki Al</button>
    </form>
  </div>
  <div>
    <div class="card">
      <h4 style="color:var(--ktsd-blue-dark); border-bottom:1px solid #E2E8F0; padding-bottom:0.5rem; margin-bottom:1rem;"><i class="fas fa-history"></i> Son Anketler</h4>
      {% if recent_polls %}
        {% for p in recent_polls %}
          <div style="padding:0.75rem; border:1px solid #E2E8F0; border-radius:6px; margin-bottom:0.5rem; background:#F8FAFC;">
            <a href="{{ url_for('view_poll', slug=p.slug) }}" style="text-decoration:none; font-weight:600; color:var(--ktsd-blue-dark);">{{ p.title }}</a>
            <div style="font-size:0.78rem; color:#64748B; margin-top:0.2rem;">Düzenleyen: {{ p.organizer_name }}</div>
          </div>
        {% endfor %}
      {% else %}
        <p style="font-size:0.85rem; color:#94A3B8;">Henüz anket bulunmuyor.</p>
      {% endif %}
    </div>
  </div>
</div>
{% endblock %}"""

POLL_HTML = """{% extends 'base.html' %}
{% block title %}{{ poll.title }} - KTSD Anketi{% endblock %}
{% block content %}
<div class="share-banner">
  <div>
    <h3 style="font-family:'Outfit',sans-serif;"><i class="fas fa-link"></i> Anket Paylaşım Bağlantısı</h3>
    <p style="font-size:0.88rem; color:#93C5FD;">Bu bağlantıyı üyelerinize göndererek oy kullanmalarını sağlayın.</p>
  </div>
  <div style="display:flex; gap:0.5rem;">
    <input type="text" id="share-poll-url" value="{{ request.url }}" readonly style="padding:0.5rem; border-radius:4px; border:none; width:280px;">
    <button type="button" id="copy-share-url" class="btn-primary" style="background:#0284C7;"><i class="fas fa-copy"></i> Kopyala</button>
  </div>
</div>
<div class="card">
  <div class="card-header">
    <h2>{{ poll.title }}</h2>
    <a href="{{ url_for('view_results', slug=poll.slug) }}" class="btn-outline"><i class="fas fa-user-shield"></i> KTSD Yetkili Girişi</a>
  </div>
  {% if poll.description %}<p style="background:#F8FAFC; padding:0.85rem; border-left:4px solid var(--ktsd-blue); margin-bottom:1rem;"><strong>Toplantı Notu:</strong> {{ poll.description }}</p>{% endif %}
  <p style="font-size:0.9rem; color:#64748B;">Düzenleyen: {{ poll.organizer_name }} | Gizlilik: Üye Oylaması (Toplu sonuçlar gizlidir)</p>
</div>
{% if voted_flag %}
  <div style="background:#ECFDF5; border:2px solid #A7F3D0; padding:1.5rem; border-radius:12px; text-align:center; margin-bottom:2rem;">
    <i class="fas fa-check-circle" style="font-size:2.5rem; color:#059669;"></i>
    <h3 style="color:#065F46; margin-top:0.5rem;">Katılım Durumunuz Kaydedilmiştir!</h3>
    <p style="color:#047857;">Teşekkür ederiz.</p>
  </div>
{% endif %}
{% if poll.status == 'active' %}
  <div class="card" style="background:#F8FAFC;">
    <h3 style="color:var(--ktsd-blue-dark); margin-bottom:1rem;"><i class="fas fa-user-check"></i> Katılım Durumunuzu İşaretleyin</h3>
    <form action="{{ url_for('submit_vote', slug=poll.slug) }}" method="POST">
      <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:1rem; margin-bottom:1.5rem;">
        <div><label class="form-label">Adınız Soyadınız *</label><input type="text" name="member_name" class="form-control" required></div>
        <div><label class="form-label">Üye Kurum / Firma</label><input type="text" name="member_company" class="form-control"></div>
        <div><label class="form-label">E-posta Adresiniz</label><input type="email" name="member_email" class="form-control"></div>
      </div>
      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:1rem; margin-bottom:1.5rem;">
        {% for opt in poll.options %}
          <div style="background:white; border:1px solid #CBD5E1; padding:1rem; border-radius:8px; text-align:center;">
            <div style="font-weight:700; color:var(--ktsd-blue-dark);">{{ opt.date_val }}</div>
            <div style="font-size:0.85rem; color:#64748B; margin-bottom:0.75rem;">{{ opt.time_val }}</div>
            <select name="opt_{{ opt.id }}" class="form-control" style="font-weight:600;">
              <option value="yes" selected>✓ Uygun</option>
              <option value="maybe">? Olabilir</option>
              <option value="no">✗ Uygun Değil</option>
            </select>
          </div>
        {% endfor %}
      </div>
      <div style="text-align:right;">
        <button type="submit" class="btn-teal" style="font-size:1.05rem;"><i class="fas fa-paper-plane"></i> Tercihlerimi Kaydet</button>
      </div>
    </form>
  </div>
{% endif %}
{% endblock %}"""

RESULTS_AUTH_HTML = """{% extends 'base.html' %}
{% block title %}KTSD Yetkili Girişi{% endblock %}
{% block content %}
<div style="max-width:500px; margin:3rem auto;" class="card">
  <h2 style="color:var(--ktsd-blue-dark); text-align:center; margin-bottom:1rem;"><i class="fas fa-user-shield"></i> KTSD Yetkili Girişi</h2>
  <p style="font-size:0.88rem; color:#64748B; text-align:center; margin-bottom:1.5rem;">Bu anketin toplu sonuçları sadece tanımlı {{ authorized_count }} yetkili KTSD e-posta adresi tarafından görüntülenebilir.</p>
  <form action="{{ url_for('staff_auth', slug=poll.slug) }}" method="POST">
    <div class="form-group">
      <label class="form-label">Yetkili KTSD E-posta Adresiniz</label>
      <input type="email" name="staff_email" class="form-control" placeholder="Örn: toplanti@ktsd.org.tr" required>
    </div>
    <button type="submit" class="btn-primary" style="width:100%;"><i class="fas fa-key"></i> Giriş Yap ve Sonuçları Aç</button>
  </form>
</div>
{% endblock %}"""

RESULTS_HTML = """{% extends 'base.html' %}
{% block title %}{{ poll.title }} - Toplu Sonuçlar{% endblock %}
{% block content %}
<div style="background:#003D7A; color:white; padding:1rem 1.5rem; border-radius:12px; margin-bottom:1.5rem; display:flex; justify-content:space-between; align-items:center;">
  <div><strong>Yetkili Oturumu:</strong> {{ staff_email }}</div>
  <div style="display:flex; gap:0.5rem;">
    <a href="{{ url_for('export_csv', slug=poll.slug) }}" class="btn-primary" style="background:#10B981;"><i class="fas fa-file-excel"></i> Excel / CSV İndir</a>
    <form action="{{ url_for('staff_logout', slug=poll.slug) }}" method="POST"><button type="submit" class="btn-outline" style="color:white; border-color:white;">Çıkış Yap</button></form>
  </div>
</div>
<div class="card">
  <div class="card-header">
    <h2>{{ poll.title }} — Toplu Sonuçlar</h2>
    <a href="{{ url_for('view_poll', slug=poll.slug) }}" target="_blank" class="btn-outline">Üye Sayfasını Gör</a>
  </div>
  <p>Toplam Katılımcı Sayısı: {{ poll.votes|length }} Üye</p>
</div>
<div class="card">
  <h3 style="color:var(--ktsd-blue-dark); margin-bottom:1rem;"><i class="fas fa-table"></i> Katılım Durum Matrisi</h3>
  <div style="overflow-x:auto;">
    <table class="matrix-table">
      <thead>
        <tr>
          <th style="text-align:left;">Katılımcı Üye</th>
          {% for opt in poll.options %}
            <th>{{ opt.date_val }}<br><small>{{ opt.time_val }}</small></th>
          {% endfor %}
        </tr>
      </thead>
      <tbody>
        {% for vote in poll.votes %}
          <tr>
            <td style="text-align:left;"><strong>{{ vote.member_name }}</strong><br><small>{{ vote.member_company or '' }}</small></td>
            {% for opt in poll.options %}
              {% set st = vote_matrix[vote.id][opt.id] %}
              <td>
                {% if st == 'yes' %}<span class="badge-status badge-yes">✓</span>
                {% elif st == 'maybe' %}<span class="badge-status badge-maybe">?</span>
                {% else %}<span class="badge-status badge-no">✗</span>{% endif %}
              </td>
            {% endfor %}
          </tr>
        {% endfor %}
        <tr style="background:#F1F5F9; font-weight:700;">
          <td style="text-align:left;">TOPLAM ÖZETİ</td>
          {% for opt in poll.options %}
            {% set s = stats[opt.id] %}
            <td>
              <div style="font-size:0.8rem;">
                <div style="color:#065F46;">✓ {{ s['yes'] }} Uygun</div>
                <div style="color:#92400E;">? {{ s['maybe'] }} Olabilir</div>
                <div style="color:#991B1B;">✗ {{ s['no'] }} Değil</div>
              </div>
            </td>
          {% endfor %}
        </tr>
      </tbody>
    </table>
  </div>
</div>
{% endblock %}"""

DICT_TEMPLATES = {
    'base.html': BASE_HTML,
    'index.html': INDEX_HTML,
    'poll.html': POLL_HTML,
    'results_auth.html': RESULTS_AUTH_HTML,
    'results.html': RESULTS_HTML
}

app.jinja_loader = DictLoader(DICT_TEMPLATES)

# Helper Turkish Date Formatter
WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

def format_tr_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekday = WEEKDAYS[dt.weekday()]
        month = MONTHS[dt.month - 1]
        return f"{dt.day} {month} {dt.year} {weekday}"
    except Exception:
        return date_str

@app.route('/')
def index():
    init_db()
    try:
        recent_polls = Poll.query.order_by(Poll.created_at.desc()).limit(10).all()
    except Exception:
        recent_polls = []
    default_emails_str = ", ".join(DEFAULT_STAFF_EMAILS)
    return render_template('index.html', recent_polls=recent_polls, default_emails_str=default_emails_str)

@app.route('/create', methods=['POST'])
def create_poll():
    init_db()
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    organizer_name = request.form.get('organizer_name', '').strip()
    organizer_company = request.form.get('organizer_company', '').strip()
    auth_emails = request.form.get('authorized_emails', '').strip()
    
    dates = request.form.getlist('option_date[]')
    times = request.form.getlist('option_time[]')

    if not title or not organizer_name:
        flash("Lütfen toplantı başlığını ve düzenleyen adını giriniz.", "danger")
        return redirect(url_for('index'))

    valid_options = []
    for i in range(len(dates)):
        d = dates[i].strip() if i < len(dates) else ''
        t = times[i].strip() if i < len(times) else ''
        if d:
            formatted_d = format_tr_date(d)
            time_display = t if t else "Tüm Gün / Belirtilmedi"
            valid_options.append((formatted_d, time_display))

    if not valid_options:
        flash("En az 1 adet geçerli tarih seçeneği eklemelisiniz.", "danger")
        return redirect(url_for('index'))

    if not auth_emails:
        auth_emails = ", ".join(DEFAULT_STAFF_EMAILS)

    slug = uuid.uuid4().hex[:10]
    poll = Poll(
        slug=slug,
        title=title,
        description=description,
        organizer_name=organizer_name,
        organizer_company=organizer_company,
        authorized_emails=auth_emails
    )
    db.session.add(poll)
    db.session.flush()

    for idx, (d_val, t_val) in enumerate(valid_options):
        opt = Option(
            poll_id=poll.id,
            date_val=d_val,
            time_val=t_val,
            order_num=idx
        )
        db.session.add(opt)

    db.session.commit()
    flash("Toplantı anketi başarıyla oluşturuldu!", "success")
    return redirect(url_for('view_poll', slug=slug))

@app.route('/poll/<slug>')
def view_poll(slug):
    init_db()
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    voted_flag = request.args.get('voted', '0') == '1'

    final_option = None
    if poll.final_option_id:
        final_option = Option.query.get(poll.final_option_id)

    return render_template('poll.html', 
                           poll=poll,
                           voted_flag=voted_flag,
                           final_option=final_option)

@app.route('/poll/<slug>/vote', methods=['POST'])
def submit_vote(slug):
    init_db()
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    
    if poll.status == 'finalized':
        flash("Bu anketin oylaması tamamlanmıştır. Yeni oy kabul edilmemektedir.", "warning")
        return redirect(url_for('view_poll', slug=slug))

    member_name = request.form.get('member_name', '').strip()
    member_company = request.form.get('member_company', '').strip()
    member_email = request.form.get('member_email', '').strip()

    if not member_name:
        flash("Lütfen adınızı ve soyadınızı belirtiniz.", "danger")
        return redirect(url_for('view_poll', slug=slug))

    vote = Vote(
        poll_id=poll.id,
        member_name=member_name,
        member_company=member_company,
        member_email=member_email
    )
    db.session.add(vote)
    db.session.flush()

    for opt in poll.options:
        status = request.form.get(f'opt_{opt.id}', 'no')
        if status not in ['yes', 'maybe', 'no']:
            status = 'no'
        detail = VoteDetail(
            vote_id=vote.id,
            option_id=opt.id,
            status=status
        )
        db.session.add(detail)

    db.session.commit()
    flash(f"Teşekkürler {member_name}, katılım tercihleriniz başarıyla alındı ve kaydedildi!", "success")
    return redirect(url_for('view_poll', slug=slug, voted=1))

@app.route('/poll/<slug>/results')
def view_results(slug):
    init_db()
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    
    authorized_list = poll.get_authorized_email_list()
    current_staff_email = session.get(f'staff_email_{poll.id}')

    is_authenticated = False
    if current_staff_email and current_staff_email.lower() in authorized_list:
        is_authenticated = True

    if not is_authenticated:
        return render_template('results_auth.html', poll=poll, authorized_count=len(authorized_list))

    stats = {}
    for opt in poll.options:
        stats[opt.id] = {'yes': 0, 'maybe': 0, 'no': 0, 'score': 0}

    for vote in poll.votes:
        for detail in vote.details:
            if detail.option_id in stats:
                stats[detail.option_id][detail.status] += 1

    best_option_id = None
    max_score = -1
    for opt_id, s in stats.items():
        score = s['yes'] * 2 + s['maybe'] * 1
        s['score'] = score
        if score > max_score and s['yes'] > 0:
            max_score = score
            best_option_id = opt_id

    vote_matrix = {}
    for vote in poll.votes:
        vote_matrix[vote.id] = {}
        for detail in vote.details:
            vote_matrix[vote.id][detail.option_id] = detail.status

    final_option = None
    if poll.final_option_id:
        final_option = Option.query.get(poll.final_option_id)

    return render_template('results.html',
                           poll=poll,
                           stats=stats,
                           best_option_id=best_option_id,
                           vote_matrix=vote_matrix,
                           final_option=final_option,
                           staff_email=current_staff_email,
                           authorized_list=authorized_list)

@app.route('/poll/<slug>/auth', methods=['POST'])
def staff_auth(slug):
    init_db()
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    email_input = request.form.get('staff_email', '').strip().lower()

    authorized_list = poll.get_authorized_email_list()

    if email_input in authorized_list:
        session[f'staff_email_{poll.id}'] = email_input
        flash(f"Giriş başarılı! Hoş geldiniz ({email_input}).", "success")
        return redirect(url_for('view_results', slug=slug))
    else:
        flash(f"Yetkisiz e-posta adresi! Toplu sonuçlar sadece yetkili KTSD e-posta adresleri ({len(authorized_list)} adet) tarafından görüntülenebilir.", "danger")
        return redirect(url_for('view_results', slug=slug))

@app.route('/poll/<slug>/staff_logout', methods=['POST'])
def staff_logout(slug):
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    session.pop(f'staff_email_{poll.id}', None)
    flash("Yetkili oturumunuz kapatıldı.", "info")
    return redirect(url_for('view_poll', slug=slug))

@app.route('/poll/<slug>/export')
def export_csv(slug):
    init_db()
    poll = Poll.query.filter_by(slug=slug).first_or_404()

    authorized_list = poll.get_authorized_email_list()
    current_staff_email = session.get(f'staff_email_{poll.id}')
    if not current_staff_email or current_staff_email.lower() not in authorized_list:
        flash("Sonuçları indirmek için yetkili KTSD çalışanı girişi gereklidir.", "danger")
        return redirect(url_for('view_results', slug=slug))
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    header = ['Katılımcı Adı', 'Kurum / Firma', 'E-posta', 'Oylama Tarihi']
    for opt in poll.options:
        header.append(f"{opt.date_val} ({opt.time_val})")
    writer.writerow(header)

    for vote in poll.votes:
        row = [vote.member_name, vote.member_company or '', vote.member_email or '', vote.created_at.strftime('%d.%m.%Y %H:%M')]
        detail_map = {d.option_id: d.status for d in vote.details}
        for opt in poll.options:
            st = detail_map.get(opt.id, 'no')
            st_text = 'Uygun' if st == 'yes' else ('Belirsiz / Olabilir' if st == 'maybe' else 'Uygun Değil')
            row.append(st_text)
        writer.writerow(row)

    output.seek(0)
    response = Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={"Content-Disposition": f"attachment;filename=KTSD_Toplanti_Sonuclari_{poll.slug}.csv"}
    )
    return response

if __name__ == '__main__':
    print("KTSD Toplantı Anketi Portalı Başlatılıyor...")
    app.run(debug=True, port=5000)
