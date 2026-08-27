import os
import uuid
import csv
import io
import tempfile
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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

# Official KTSD Staff Emails
DEFAULT_STAFF_EMAILS = [
    "turkan.dundar@ktsd.org.tr",
    "ilayda.huban@ktsd.org.tr",
    "dicle.eren@ktsd.org.tr",
    "ilayda.kaya@ktsd.org.tr"
]

# SMTP Configuration
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'mail.ktsd.org.tr')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', 'toplanti@ktsd.org.tr')
SMTP_PASS = os.environ.get('SMTP_PASS', '')

def send_async_email(subject, html_body, recipients):
    """ Sends email notifications in a background thread """
    if not recipients or not SMTP_PASS:
        print(f"[Email Notification Logged] Subject: {subject} -> Recipients: {recipients}")
        return

    def _send():
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"KTSD Toplantı Portalı <{SMTP_USER}>"
            msg['To'] = ", ".join(recipients)

            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, recipients, msg.as_string())
            server.quit()
            print(f"[Email Sent Successfully] to {recipients}")
        except Exception as e:
            print(f"[Email Notification Exception] {e}")

    threading.Thread(target=_send).start()

# Database Models
class Poll(db.Model):
    __tablename__ = 'polls'
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(32), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    organizer_name = db.Column(db.String(120), nullable=True, default='KTSD Genel Sekreterliği')
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

# EMBEDDED HTML TEMPLATES
BASE_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}KTSD Toplantı Portalı{% endblock %}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    :root {
      --ktsd-blue: #005BB5;
      --ktsd-blue-dark: #003D7A;
      --bg-light: #F8FAFC;
      --card-bg: #FFFFFF;
      --status-yes-bg: #E6F4EA; --status-yes-color: #137333; --status-yes-btn: #10B981;
      --status-maybe-bg: #FEF7E0; --status-maybe-color: #B06000; --status-maybe-btn: #F59E0B;
      --status-no-bg: #F1F3F4; --status-no-color: #5F6368; --status-no-btn: #EF4444;
      --radius-sm: 8px; --radius-md: 14px;
      --shadow-md: 0 8px 24px -4px rgba(0, 91, 181, 0.12);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Inter', sans-serif; background: var(--bg-light); color: #202124; line-height: 1.5; min-height: 100vh; display: flex; flex-direction: column; }
    .ktsd-header { background: #FFFFFF; padding: 1rem 2rem; box-shadow: 0 2px 10px rgba(0, 61, 122, 0.08); position: sticky; top: 0; z-index: 100; border-bottom: 4px solid var(--ktsd-blue); }
    .header-container { max-width: 1250px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }
    .ktsd-brand { display: flex; align-items: center; gap: 1rem; text-decoration: none; color: #202124; }
    .ktsd-logo-badge { background: var(--ktsd-blue); color: white; padding: 0.45rem 0.85rem; border-radius: 10px; font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 1.25rem; }
    .brand-text h1 { font-family: 'Outfit', sans-serif; font-size: 1.3rem; font-weight: 700; color: var(--ktsd-blue-dark); }
    .brand-text p { font-size: 0.78rem; color: #5F6368; }
    .btn-header { background: var(--ktsd-blue); color: white; padding: 0.6rem 1.2rem; border-radius: var(--radius-sm); text-decoration: none; font-size: 0.88rem; font-weight: 600; }
    .btn-header:hover { background: var(--ktsd-blue-dark); }
    .btn-header-outline { border: 1.5px solid var(--ktsd-blue-dark); color: var(--ktsd-blue-dark); padding: 0.6rem 1.2rem; border-radius: var(--radius-sm); text-decoration: none; font-size: 0.88rem; font-weight: 600; }
    .main-wrapper { max-width: 1250px; margin: 2rem auto; padding: 0 1.5rem; flex: 1; width: 100%; }
    .card { background: white; border-radius: var(--radius-md); box-shadow: var(--shadow-md); border: 1px solid #E8EAED; padding: 2rem; margin-bottom: 2rem; }
    .hero-section { background: linear-gradient(135deg, #005BB5 0%, #003D7A 100%); color: white; padding: 2.25rem; border-radius: var(--radius-md); margin-bottom: 2rem; }
    .form-group { margin-bottom: 1.25rem; }
    .form-label { display: block; font-weight: 600; font-size: 0.9rem; color: var(--ktsd-blue-dark); margin-bottom: 0.4rem; }
    .form-control { width: 100%; padding: 0.75rem 1rem; font-size: 0.95rem; border: 1.5px solid #BDC1C6; border-radius: var(--radius-sm); }
    .btn-primary { background: var(--ktsd-blue); color: white; padding: 0.85rem 1.75rem; border-radius: var(--radius-sm); border: none; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 0.5rem; justify-content: center; }
    .btn-primary:hover { background: var(--ktsd-blue-dark); }
    .btn-teal { background: #1e8e3e; color: white; padding: 0.85rem 1.75rem; border-radius: var(--radius-sm); border: none; font-weight: 600; cursor: pointer; }
    .btn-outline { border: 1.5px solid var(--ktsd-blue-dark); color: var(--ktsd-blue-dark); padding: 0.5rem 1rem; border-radius: var(--radius-sm); text-decoration: none; font-weight: 600; font-size: 0.88rem; background: transparent; cursor: pointer; }
    .share-banner { background: #003D7A; color: white; padding: 1.25rem 1.5rem; border-radius: var(--radius-md); margin-bottom: 1.5rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; }
    
    .stat-cards-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.25rem; margin-bottom: 1.5rem; }
    .stat-card { background: #F8F9FA; border: 1px solid #DADCE0; border-radius: 12px; padding: 1.25rem; text-align: center; }
    .stat-card-title { font-size: 0.82rem; font-weight: 700; color: #5F6368; text-transform: uppercase; margin-bottom: 0.3rem; }
    .stat-card-val { font-family: 'Outfit', sans-serif; font-size: 1.8rem; font-weight: 800; color: var(--ktsd-blue-dark); }
    .stat-card-sub { font-size: 0.8rem; color: #1e8e3e; font-weight: 600; margin-top: 0.2rem; }

    .best-date-box { background: linear-gradient(135deg, #E6F4EA 0%, #CEEAD6 100%); border: 2px solid #34A853; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
    
    .doodle-table-wrapper { width: 100%; overflow-x: auto; border: 1px solid #DADCE0; border-radius: 12px; background: white; margin-top: 1rem; }
    .doodle-table { width: 100%; border-collapse: separate; border-spacing: 0; }
    .doodle-header-cell { background: #F8F9FA; padding: 1rem 0.75rem; text-align: center; border-bottom: 2px solid #DADCE0; border-right: 1px solid #E8EAED; min-width: 140px; }
    .doodle-header-participant { background: #F1F3F4; padding: 1rem; text-align: left; border-bottom: 2px solid #DADCE0; border-right: 2px solid #DADCE0; min-width: 220px; font-weight: 700; color: var(--ktsd-blue-dark); }
    
    .doodle-date-card { display: flex; flex-direction: column; align-items: center; gap: 0.15rem; }
    .doodle-star { color: #F9AB00; font-size: 0.9rem; }
    .doodle-date-num { font-family: 'Outfit', sans-serif; font-size: 1.6rem; font-weight: 800; color: #202124; line-height: 1; }
    .doodle-date-day { font-size: 0.8rem; font-weight: 700; color: #5F6368; text-transform: uppercase; }
    .doodle-time-text { font-size: 0.78rem; color: #3C4043; font-weight: 600; margin-top: 0.25rem; background: #E8F0FE; padding: 0.15rem 0.4rem; border-radius: 4px; }
    .doodle-voters-count { font-size: 0.75rem; color: #5F6368; margin-top: 0.3rem; display: flex; align-items: center; gap: 0.25rem; }
    
    .doodle-row-participant { padding: 0.85rem 1rem; border-bottom: 1px solid #E8EAED; border-right: 2px solid #DADCE0; background: #FFFFFF; display: flex; align-items: center; gap: 0.65rem; }
    .avatar-circle { width: 36px; height: 36px; border-radius: 50%; background: var(--ktsd-blue); color: white; font-weight: 700; font-size: 0.85rem; display: flex; align-items: center; justify-content: center; text-transform: uppercase; }
    .participant-info { line-height: 1.2; }
    .participant-name { font-weight: 700; font-size: 0.92rem; color: #202124; }
    .participant-sub { font-size: 0.75rem; color: #5F6368; }

    .doodle-cell { padding: 0.65rem; border-bottom: 1px solid #E8EAED; border-right: 1px solid #E8EAED; text-align: center; vertical-align: middle; }
    
    .pill-badge { display: inline-flex; align-items: center; justify-content: center; width: 38px; height: 38px; border-radius: 8px; font-size: 1.1rem; font-weight: 800; }
    .pill-yes { background: #E6F4EA; color: #137333; }
    .pill-maybe { background: #FEF7E0; color: #B06000; }
    .pill-no { background: #F1F3F4; color: #70757A; }

    .vote-toggle-pill { display: flex; gap: 0.25rem; justify-content: center; }
    .v-btn { width: 36px; height: 36px; border-radius: 8px; border: 1.5px solid #DADCE0; background: white; cursor: pointer; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 1rem; transition: all 0.15s ease; }
    .v-btn input[type="radio"] { display: none; }
    .v-btn.v-yes:has(input:checked), .v-btn.v-yes.active { background: #137333; color: white; border-color: #137333; }
    .v-btn.v-maybe:has(input:checked), .v-btn.v-maybe.active { background: #F59E0B; color: white; border-color: #F59E0B; }
    .v-btn.v-no:has(input:checked), .v-btn.v-no.active { background: #5F6368; color: white; border-color: #5F6368; }

    .matrix-table { width: 100%; border-collapse: collapse; text-align: center; font-size: 0.9rem; }
    .matrix-table th, .matrix-table td { padding: 0.85rem; border: 1px solid #E2E8F0; }
    .matrix-table th { background: #F8FAFC; color: var(--ktsd-blue-dark); font-weight: 600; }

    .ktsd-footer { background: var(--ktsd-blue-dark); color: #93C5FD; padding: 1.5rem; text-align: center; font-size: 0.85rem; margin-top: auto; }
    .alert { padding: 0.85rem 1.25rem; border-radius: var(--radius-sm); margin-bottom: 1rem; font-size: 0.92rem; background: #E6F4EA; color: #137333; border: 1px solid #CEEAD6; }
    .alert-danger { background: #FCE8E6; color: #C5221F; border-color: #FAD2CF; }
  </style>
</head>
<body>
  <header class="ktsd-header">
    <div class="header-container">
      <a href="{{ url_for('index') }}" class="ktsd-brand">
        <img src="data:image/png;base64,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" alt="KTSD Logo" style="height: 52px; width: auto; object-fit: contain;">
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
        row.style.display = 'grid';
        row.style.gridTemplateColumns = '1fr 1fr 45px';
        row.style.gap = '0.75rem';
        row.style.marginBottom = '0.75rem';
        row.style.background = '#F8FAFC';
        row.style.padding = '0.75rem';
        row.style.borderRadius = '8px';
        row.style.border = '1px dashed #CBD5E1';
        row.innerHTML = `
          <div><input type="date" name="option_date[]" class="form-control" value="${d}" required></div>
          <div><input type="text" name="option_time[]" class="form-control" value="${t}" placeholder="Örn: 09:00 - 10:00"></div>
          <div><button type="button" class="btn-remove-row" style="background:#FEE2E2; color:#EF4444; border:1px solid #FECACA; width:40px; height:40px; border-radius:6px; cursor:pointer;">×</button></div>
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

      document.querySelectorAll('.v-btn').forEach(btn => {
        btn.addEventListener('click', function() {
          const radio = this.querySelector('input[type="radio"]');
          if (radio) {
            const name = radio.getAttribute('name');
            document.querySelectorAll(`input[name="${name}"]`).forEach(r => {
              r.closest('.v-btn').classList.remove('active');
            });
            radio.checked = true;
            this.classList.add('active');
          }
        });
      });

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
  <p>Takvim kartları ile üyelere toplantı anketi bağlantısı gönderin. Üyeler sadece tarih seçimi yapabilir; toplu sonuçlar ve anlık e-posta bildirimleri seçtiğiniz yetkili KTSD çalışanına iletilir.</p>
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

      <!-- YETKİLİ KİŞİ DROPDOWN SELECT (OK İLE SEÇİM) -->
      <div class="form-group" style="background:#F0F9FF; padding:1rem; border-radius:8px; border:1px solid #BAE6FD;">
        <label class="form-label" style="color:#0369A1;"><i class="fas fa-user-shield"></i> Anlık Bildirim Gönderilecek KTSD Yetkilisi *</label>
        <select name="authorized_emails" class="form-control" style="font-weight:600; cursor:pointer;">
          <option value="turkan.dundar@ktsd.org.tr" selected>1. Türkan Dündar (turkan.dundar@ktsd.org.tr)</option>
          <option value="ilayda.huban@ktsd.org.tr">2. İlayda Hüban (ilayda.huban@ktsd.org.tr)</option>
          <option value="dicle.eren@ktsd.org.tr">3. Dicle Eren (dicle.eren@ktsd.org.tr)</option>
          <option value="ilayda.kaya@ktsd.org.tr">4. İlayda Kaya (ilayda.kaya@ktsd.org.tr)</option>
          <option value="turkan.dundar@ktsd.org.tr, ilayda.huban@ktsd.org.tr, dicle.eren@ktsd.org.tr, ilayda.kaya@ktsd.org.tr">Tüm KTSD Ekibi (4 Yetkili Mail)</option>
        </select>
        <small style="color:#0284C7; display:block; margin-top:0.3rem;"><i class="fas fa-bell"></i> Seçilen KTSD yetkilisine her yeni üye işaretlemesinde anlık e-posta bildirimi iletilir.</small>
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
          <div class="option-row" style="display:grid; grid-template-columns:1fr 1fr 45px; gap:0.75rem; margin-bottom:0.75rem; background:#F8FAFC; padding:0.75rem; border-radius:8px; border:1px dashed #CBD5E1;">
            <div><input type="date" name="option_date[]" class="form-control" required></div>
            <div><input type="text" name="option_time[]" class="form-control" placeholder="Örn: 09:00 - 10:00"></div>
            <div><button type="button" class="btn-remove-row" style="background:#FEE2E2; color:#EF4444; border:1px solid #FECACA; width:40px; height:40px; border-radius:6px; cursor:pointer;">×</button></div>
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
    <p style="font-size:0.88rem; color:#93C5FD;">Bu bağlantıyı üyelerinize göndererek oylarını alabilirsiniz.</p>
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
  <p style="font-size:0.85rem; color:#64748B;">Gizlilik: Üye Oylaması (Toplu sonuçlar KTSD yetkililerine özeldir)</p>
</div>

{% if voted_flag %}
  <div style="background:#ECFDF5; border:2px solid #A7F3D0; padding:1.5rem; border-radius:12px; text-align:center; margin-bottom:2rem;">
    <i class="fas fa-check-circle" style="font-size:2.5rem; color:#059669;"></i>
    <h3 style="color:#065F46; margin-top:0.5rem;">Katılım Tercihleriniz Kaydedilmiştir!</h3>
    <p style="color:#047857;">Toplantı tarihi kesinleştiğinde bilgilendirme yapılacaktır. Katılımınız için teşekkür ederiz.</p>
  </div>
{% endif %}

{% if poll.status == 'active' %}
  <div class="card">
    <h3 style="color:var(--ktsd-blue-dark); margin-bottom:0.5rem;"><i class="fas fa-calendar-check" style="color:var(--ktsd-blue);"></i> Toplantı Katılım Tercihleri</h3>
    <p style="font-size:0.88rem; color:#5F6368; margin-bottom:1.5rem;">Lütfen adınızı girerek aşağıdaki tarih sütunlarında durumunuzu (✓ Uygun, ? Olabilir, ✗ Değil) seçin.</p>
    
    <form action="{{ url_for('submit_vote', slug=poll.slug) }}" method="POST">
      <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:1rem; margin-bottom:1.5rem; background:#F8F9FA; padding:1.25rem; border-radius:10px; border:1px solid #DADCE0;">
        <div><label class="form-label">Adınız Soyadınız *</label><input type="text" name="member_name" class="form-control" placeholder="Örn: Mehmet Özkan" required></div>
        <div><label class="form-label">Üye Kurum / Firma</label><input type="text" name="member_company" class="form-control" placeholder="Örn: ABC Kimya A.Ş."></div>
        <div><label class="form-label">E-posta Adresiniz</label><input type="email" name="member_email" class="form-control" placeholder="Örn: mehmet@abckimya.com"></div>
      </div>

      <div class="doodle-table-wrapper">
        <table class="doodle-table">
          <thead>
            <tr>
              <th class="doodle-header-participant">Katılımcı / Tarihler</th>
              {% for opt in poll.options %}
                <th class="doodle-header-cell">
                  <div class="doodle-date-card">
                    <div class="doodle-star">⭐</div>
                    <div class="doodle-date-num">{{ opt.date_val.split()[0] if opt.date_val else '' }}</div>
                    <div class="doodle-date-day">{{ opt.date_val.split()[1] if opt.date_val.split()|length > 1 else '' }} {{ opt.date_val.split()[-1] if opt.date_val.split()|length > 2 else '' }}</div>
                    <div class="doodle-time-text"><i class="far fa-clock"></i> {{ opt.time_val }}</div>
                  </div>
                </th>
              {% endfor %}
            </tr>
          </thead>
          <tbody>
            <tr style="background:#F0F7FF;">
              <td class="doodle-row-participant" style="background:#E8F0FE;">
                <div class="avatar-circle" style="background:#1A73E8;">SİZ</div>
                <div class="participant-info">
                  <div class="participant-name" style="color:#1A73E8;">Sizin Tercihiniz</div>
                  <div class="participant-sub">Aşağıdan seçin</div>
                </div>
              </td>
              {% for opt in poll.options %}
                <td class="doodle-cell">
                  <div class="vote-toggle-pill">
                    <label class="v-btn v-yes active" title="Uygun">
                      <input type="radio" name="opt_{{ opt.id }}" value="yes" checked> ✓
                    </label>
                    <label class="v-btn v-maybe" title="Olabilir">
                      <input type="radio" name="opt_{{ opt.id }}" value="maybe"> ?
                    </label>
                    <label class="v-btn v-no" title="Uygun Değil">
                      <input type="radio" name="opt_{{ opt.id }}" value="no"> ✗
                    </label>
                  </div>
                </td>
              {% endfor %}
            </tr>
          </tbody>
        </table>
      </div>

      <div style="text-align:right; margin-top:1.5rem;">
        <button type="submit" class="btn-teal" style="font-size:1.1rem; padding:0.9rem 2.2rem;"><i class="fas fa-paper-plane"></i> Katılım Durumumu Kaydet</button>
      </div>
    </form>
  </div>
{% endif %}
{% endblock %}"""

RESULTS_AUTH_HTML = """{% extends 'base.html' %}
{% block title %}KTSD Yetkili Girişi{% endblock %}
{% block content %}
<div style="max-width:520px; margin:3rem auto;" class="card">
  <h2 style="color:var(--ktsd-blue-dark); text-align:center; margin-bottom:1rem;"><i class="fas fa-user-shield"></i> KTSD Yetkili Girişi</h2>
  <p style="font-size:0.88rem; color:#5F6368; text-align:center; margin-bottom:1.5rem;">Bu anketin toplu sonuçları sadece yetkili KTSD e-posta adresleri (turkan.dundar, ilayda.huban, dicle.eren, ilayda.kaya@ktsd.org.tr) tarafından görüntülenebilir.</p>
  <form action="{{ url_for('staff_auth', slug=poll.slug) }}" method="POST">
    <div class="form-group">
      <label class="form-label">Yetkili KTSD E-posta Adresiniz</label>
      <input type="email" name="staff_email" class="form-control" placeholder="Örn: turkan.dundar@ktsd.org.tr" required>
    </div>
    <button type="submit" class="btn-primary" style="width:100%; font-size:1rem; padding:0.85rem;"><i class="fas fa-key"></i> Giriş Yap ve Sonuçları Aç</button>
  </form>
</div>
{% endblock %}"""

RESULTS_HTML = """{% extends 'base.html' %}
{% block title %}{{ poll.title }} - Toplu Sonuçlar ve Özet İstatistikler{% endblock %}
{% block content %}
<div style="background:#003D7A; color:white; padding:1rem 1.5rem; border-radius:12px; margin-bottom:1.5rem; display:flex; justify-content:space-between; align-items:center;">
  <div><strong>Yetkili KTSD Oturumu:</strong> {{ staff_email }}</div>
  <div style="display:flex; gap:0.5rem;">
    <a href="{{ url_for('export_csv', slug=poll.slug) }}" class="btn-primary" style="background:#1e8e3e;"><i class="fas fa-file-excel"></i> Excel / CSV İndir</a>
    <form action="{{ url_for('staff_logout', slug=poll.slug) }}" method="POST"><button type="submit" class="btn-outline" style="color:white; border-color:white;">Çıkış Yap</button></form>
  </div>
</div>

<div class="card" style="background:linear-gradient(135deg, #FFFFFF 0%, #F0F4F9 100%); border-top: 5px solid var(--ktsd-blue);">
  <div class="card-header">
    <h2><i class="fas fa-chart-pie" style="color:var(--ktsd-blue);"></i> KTSD Yetkili Özet & Analiz Raporu</h2>
    <span style="font-size:0.82rem; background:#E8F0FE; color:#1A73E8; padding:0.3rem 0.75rem; border-radius:50px; font-weight:700;">GİZLİ & KİŞİYE ÖZEL</span>
  </div>

  {% if best_option_id %}
    {% set best_opt = poll.options|selectattr('id', 'equalto', best_option_id)|first %}
    {% if best_opt %}
      <div class="best-date-box">
        <div style="display:flex; align-items:center; gap:1rem;">
          <div style="font-size:2.5rem; color:#34A853;"><i class="fas fa-trophy"></i></div>
          <div>
            <div style="font-size:0.82rem; font-weight:700; color:#137333; text-transform:uppercase;">🏆 EN ÇOK KATILIM SAĞLANAN EN UYGUN GÜN</div>
            <div style="font-family:'Outfit',sans-serif; font-size:1.4rem; font-weight:800; color:#065F46; margin-top:0.2rem;">
              {{ best_opt.date_val }} — Saat: {{ best_opt.time_val }}
            </div>
          </div>
        </div>
        <div>
          <span style="background:#137333; color:white; padding:0.5rem 1.25rem; border-radius:50px; font-weight:800; font-size:0.95rem;">
            <i class="fas fa-users"></i> {{ stats[best_opt.id]['yes'] }} ÜYE UYGUN
          </span>
        </div>
      </div>
    {% endif %}
  {% endif %}

  <div class="stat-cards-grid">
    <div class="stat-card">
      <div class="stat-card-title"><i class="fas fa-users"></i> Toplam İşaretleyen Üye</div>
      <div class="stat-card-val">{{ poll.votes|length }}</div>
      <div class="stat-card-sub">Oy kullanan üye sayısı</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-title"><i class="fas fa-check-circle" style="color:#137333;"></i> Toplam Uygun (✓)</div>
      <div class="stat-card-val" style="color:#137333;">{{ total_yes_count }}</div>
      <div class="stat-card-sub">Toplam yeşil tik sayısı</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-title"><i class="fas fa-question-circle" style="color:#B06000;"></i> Toplam Belirsiz (?)</div>
      <div class="stat-card-val" style="color:#B06000;">{{ total_maybe_count }}</div>
      <div class="stat-card-sub">Toplam sarı soru işareti</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-title"><i class="fas fa-times-circle" style="color:#5F6368;"></i> Toplam Uygun Değil (✗)</div>
      <div class="stat-card-val" style="color:#5F6368;">{{ total_no_count }}</div>
      <div class="stat-card-sub">Toplam çarpı işaretlemesi</div>
    </div>
  </div>

  <div style="margin-top:1.5rem;">
    <h4 style="color:var(--ktsd-blue-dark); margin-bottom:0.75rem;"><i class="fas fa-list-ol"></i> Oy Kullanan Üyelerin Listesi (Kimler İşaretledi?)</h4>
    {% if poll.votes %}
      <div style="overflow-x:auto; border:1px solid #DADCE0; border-radius:8px;">
        <table class="matrix-table">
          <thead>
            <tr style="background:#F8F9FA;">
              <th style="text-align:left;">Katılımcı Üye Adı</th>
              <th style="text-align:left;">Kurum / Firma</th>
              <th style="text-align:left;">E-posta</th>
              <th>İşaretleme Tarihi</th>
            </tr>
          </thead>
          <tbody>
            {% for v in poll.votes %}
              <tr>
                <td style="text-align:left; font-weight:700; color:var(--ktsd-blue-dark);">{{ v.member_name }}</td>
                <td style="text-align:left; color:#5F6368;">{{ v.member_company or '-' }}</td>
                <td style="text-align:left; color:#1A73E8;">{{ v.member_email or '-' }}</td>
                <td>{{ v.created_at.strftime('%d.%m.%Y %H:%M') }}</td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <p style="color:#70757A; font-size:0.88rem;">Henüz katılım tercihi yapan üye bulunmuyor.</p>
    {% endif %}
  </div>
</div>

<div class="card">
  <h3 style="color:var(--ktsd-blue-dark); margin-bottom:1rem;"><i class="fas fa-poll"></i> Katılımcı Detaylı Oy Matrisi</h3>
  <div class="doodle-table-wrapper">
    <table class="doodle-table">
      <thead>
        <tr>
          <th class="doodle-header-participant">Katılımcı Üye / Firma</th>
          {% for opt in poll.options %}
            {% set s = stats[opt.id] %}
            <th class="doodle-header-cell">
              <div class="doodle-date-card">
                <div class="doodle-star">⭐</div>
                <div class="doodle-date-num">{{ opt.date_val.split()[0] if opt.date_val else '' }}</div>
                <div class="doodle-date-day">{{ opt.date_val.split()[1] if opt.date_val.split()|length > 1 else '' }} {{ opt.date_val.split()[-1] if opt.date_val.split()|length > 2 else '' }}</div>
                <div class="doodle-time-text">{{ opt.time_val }}</div>
                <div class="doodle-voters-count"><i class="fas fa-users"></i> {{ s['yes'] }} Uygun</div>
              </div>
            </th>
          {% endfor %}
        </tr>
      </thead>
      <tbody>
        {% if poll.votes %}
          {% for vote in poll.votes %}
            <tr>
              <td class="doodle-row-participant">
                <div class="avatar-circle">{{ vote.member_name[:2] }}</div>
                <div class="participant-info">
                  <div class="participant-name">{{ vote.member_name }}</div>
                  <div class="participant-sub">{{ vote.member_company or '' }}</div>
                </div>
              </td>
              {% for opt in poll.options %}
                {% set st = vote_matrix[vote.id][opt.id] %}
                <td class="doodle-cell">
                  {% if st == 'yes' %}<span class="pill-badge pill-yes" title="Uygun">✓</span>
                  {% elif st == 'maybe' %}<span class="pill-badge pill-maybe" title="Olabilir">?</span>
                  {% else %}<span class="pill-badge pill-no" title="Uygun Değil">✗</span>{% endif %}
                </td>
              {% endfor %}
            </tr>
          {% endfor %}
        {% else %}
          <tr>
            <td colspan="{{ poll.options|length + 1 }}" style="padding:2rem; text-align:center; color:#70757A;">Henüz katılım tercihi yapan üye bulunmuyor.</td>
          </tr>
        {% endif %}

        <tr style="background:#F1F3F4; font-weight:700;">
          <td class="doodle-row-participant" style="background:#E8EAED;">
            <div class="avatar-circle" style="background:var(--ktsd-blue-dark);">ÖZET</div>
            <div class="participant-info">
              <div class="participant-name">TOPLAM SAYILAR</div>
              <div class="participant-sub">Genel Özet</div>
            </div>
          </td>
          {% for opt in poll.options %}
            {% set s = stats[opt.id] %}
            <td class="doodle-cell" style="background:#F8F9FA;">
              <div style="font-size:0.8rem; line-height:1.4;">
                <div style="color:#137333; font-weight:700;">✓ {{ s['yes'] }} Uygun</div>
                <div style="color:#B06000;">? {{ s['maybe'] }} Olabilir</div>
                <div style="color:#70757A;">✗ {{ s['no'] }} Değil</div>
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
    auth_emails = request.form.get('authorized_emails', '').strip()
    
    dates = request.form.getlist('option_date[]')
    times = request.form.getlist('option_time[]')

    if not title:
        flash("Lütfen toplantı başlığını giriniz.", "danger")
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
        auth_emails = "turkan.dundar@ktsd.org.tr"

    slug = uuid.uuid4().hex[:10]
    poll = Poll(
        slug=slug,
        title=title,
        description=description,
        organizer_name='KTSD Genel Sekreterliği',
        organizer_company='KTSD',
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

    vote_summary_lines = []
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
        
        st_label = "✓ Uygun" if status == 'yes' else ("? Olabilir" if status == 'maybe' else "✗ Değil")
        vote_summary_lines.append(f"<li><b>{opt.date_val} ({opt.time_val}):</b> {st_label}</li>")

    db.session.commit()

    # Trigger Async Email Notification to Authorized Staff
    recipients = poll.get_authorized_email_list()
    subject = f"[KTSD Toplantı Portalı] Yeni Katılım İşaretlemesi: {member_name} - {poll.title}"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f7fa;">
      <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; padding: 25px; border-top: 5px solid #005BB5;">
        <h2 style="color: #003D7A; margin-top: 0;">Yeni Katılım İşaretlemesi Alındı</h2>
        <p><b>Toplantı Konusu:</b> {poll.title}</p>
        <p><b>İşaretleyen Üye:</b> {member_name} ({member_company or 'Kurum Belirtilmedi'})</p>
        <p><b>E-posta:</b> {member_email or 'Belirtilmedi'}</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <h4 style="color: #005BB5;">Üyenin Tarih Tercihleri:</h4>
        <ul style="line-height: 1.6; color: #333;">
          {"".join(vote_summary_lines)}
        </ul>
        <div style="margin-top: 25px; text-align: center;">
          <a href="{request.host_url}poll/{poll.slug}/results" style="background: #005BB5; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">Toplu Sonuçları Görüntüle</a>
        </div>
      </div>
    </div>
    """
    send_async_email(subject, html_body, recipients)

    flash(f"Teşekkürler {member_name}, katılım tercihleriniz başarıyla alındı ve yetkili KTSD ekibine e-posta bildirimi iletildi!", "success")
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
    total_yes_count = 0
    total_maybe_count = 0
    total_no_count = 0

    for opt in poll.options:
        stats[opt.id] = {'yes': 0, 'maybe': 0, 'no': 0, 'score': 0}

    for vote in poll.votes:
        for detail in vote.details:
            if detail.option_id in stats:
                stats[detail.option_id][detail.status] += 1
                if detail.status == 'yes':
                    total_yes_count += 1
                elif detail.status == 'maybe':
                    total_maybe_count += 1
                elif detail.status == 'no':
                    total_no_count += 1

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
                           total_yes_count=total_yes_count,
                           total_maybe_count=total_maybe_count,
                           total_no_count=total_no_count,
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
