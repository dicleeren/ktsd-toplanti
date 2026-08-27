import os
import uuid
import csv
import io
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, session
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ktsd-sec-key-2026-secret-poll-token-auth-restricted'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ktsd_poll.db'
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
    authorized_emails = db.Column(db.Text, nullable=True)  # Comma separated authorized staff emails
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='active')  # active, finalized
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
    status = db.Column(db.String(10), nullable=False)  # 'yes', 'maybe', 'no'

with app.app_context():
    db.create_all()

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
    recent_polls = Poll.query.order_by(Poll.created_at.desc()).limit(10).all()
    default_emails_str = ", ".join(DEFAULT_STAFF_EMAILS)
    return render_template('index.html', recent_polls=recent_polls, default_emails_str=default_emails_str)

@app.route('/create', methods=['POST'])
def create_poll():
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

    # Clean valid date/time options
    valid_options = []
    for i in range(len(dates)):
        d = dates[i].strip() if i < len(dates) else ''
        t = times[i].strip() if i < len(times) else ''
        if d:
            formatted_d = format_tr_date(d)
            time_display = t if t else "Tüm Gün / Belirtilmedi"
            valid_options.append((formatted_d, time_display))

    if not valid_options:
        flash("En az 1 adet geçerli tarih seçeneği eklemelisiniz.", "warning")
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

# PUBLIC MEMBER VIEW: Only voting form, NO collective results
@app.route('/poll/<slug>')
def view_poll(slug):
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    
    # Check if member just voted
    voted_flag = request.args.get('voted', '0') == '1'

    final_option = None
    if poll.final_option_id:
        final_option = Option.query.get(poll.final_option_id)

    return render_template('poll.html', 
                           poll=poll,
                           voted_flag=voted_flag,
                           final_option=final_option)

# MEMBER VOTE SUBMISSION
@app.route('/poll/<slug>/vote', methods=['POST'])
def submit_vote(slug):
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

# KTSD STAFF RESTRICTED RESULTS DASHBOARD
@app.route('/poll/<slug>/results')
def view_results(slug):
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    
    authorized_list = poll.get_authorized_email_list()
    current_staff_email = session.get(f'staff_email_{poll.id}')

    # Check authentication
    is_authenticated = False
    if current_staff_email and current_staff_email.lower() in authorized_list:
        is_authenticated = True

    if not is_authenticated:
        return render_template('results_auth.html', poll=poll, authorized_count=len(authorized_list))

    # Stats per option
    stats = {}
    for opt in poll.options:
        stats[opt.id] = {'yes': 0, 'maybe': 0, 'no': 0, 'score': 0}

    for vote in poll.votes:
        for detail in vote.details:
            if detail.option_id in stats:
                stats[detail.option_id][detail.status] += 1

    # Best option calculation
    best_option_id = None
    max_score = -1
    for opt_id, s in stats.items():
        score = s['yes'] * 2 + s['maybe'] * 1
        s['score'] = score
        if score > max_score and s['yes'] > 0:
            max_score = score
            best_option_id = opt_id

    # Matrix lookup
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

# KTSD STAFF AUTHENTICATION ROUTE
@app.route('/poll/<slug>/auth', methods=['POST'])
def staff_auth(slug):
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    email_input = request.form.get('staff_email', '').strip().lower()

    authorized_list = poll.get_authorized_email_list()

    if email_input in authorized_list:
        session[f'staff_email_{poll.id}'] = email_input
        flash(f"Giriş başarılı! Hoş geldiniz ({email_input}). Toplu sonuçları görüntülüyorsunuz.", "success")
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

@app.route('/poll/<slug>/vote/delete/<int:vote_id>', methods=['POST'])
def delete_vote(slug, vote_id):
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    
    # Require staff auth to delete vote
    authorized_list = poll.get_authorized_email_list()
    current_staff_email = session.get(f'staff_email_{poll.id}')
    if not current_staff_email or current_staff_email.lower() not in authorized_list:
        flash("Bu işlemi yapmak için yetkili KTSD çalışanı olarak giriş yapmalısınız.", "danger")
        return redirect(url_for('view_results', slug=slug))

    vote = Vote.query.filter_by(id=vote_id, poll_id=poll.id).first_or_404()
    db.session.delete(vote)
    db.session.commit()
    flash("Oy kaydı silindi.", "info")
    return redirect(url_for('view_results', slug=slug))

@app.route('/poll/<slug>/finalize', methods=['POST'])
def finalize_poll(slug):
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    
    # Require staff auth to finalize
    authorized_list = poll.get_authorized_email_list()
    current_staff_email = session.get(f'staff_email_{poll.id}')
    if not current_staff_email or current_staff_email.lower() not in authorized_list:
        flash("Tarih kesinleştirme işlemi için yetkili KTSD çalışanı girişi gereklidir.", "danger")
        return redirect(url_for('view_results', slug=slug))

    option_id = request.form.get('final_option_id', type=int)
    if option_id:
        poll.status = 'finalized'
        poll.final_option_id = option_id
        db.session.commit()
        flash("Toplantı tarihi ve saati başarıyla kesinleştirildi!", "success")
    
    return redirect(url_for('view_results', slug=slug))

@app.route('/poll/<slug>/reopen', methods=['POST'])
def reopen_poll(slug):
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    
    authorized_list = poll.get_authorized_email_list()
    current_staff_email = session.get(f'staff_email_{poll.id}')
    if not current_staff_email or current_staff_email.lower() not in authorized_list:
        flash("Bu işlem için yetkili KTSD çalışanı girişi gereklidir.", "danger")
        return redirect(url_for('view_results', slug=slug))

    poll.status = 'active'
    poll.final_option_id = None
    db.session.commit()
    flash("Anket tekrar oylamaya açıldı.", "info")
    return redirect(url_for('view_results', slug=slug))

@app.route('/poll/<slug>/export')
def export_csv(slug):
    poll = Poll.query.filter_by(slug=slug).first_or_404()

    # Require staff auth to export
    authorized_list = poll.get_authorized_email_list()
    current_staff_email = session.get(f'staff_email_{poll.id}')
    if not current_staff_email or current_staff_email.lower() not in authorized_list:
        flash("Sonuçları Excel / CSV olarak indirmek için yetkili KTSD çalışanı girişi gereklidir.", "danger")
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
