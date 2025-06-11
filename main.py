from flask import Flask, render_template, request, redirect, url_for, session, abort, jsonify
import json
import os
import re
import time
from functools import wraps

app = Flask(__name__)
app.secret_key = 'secretkey'
USERS_FILE = 'users.json'

ADMIN_USER = "admin"
ADMIN_PASS = "your_admin_password"
ADMIN_ALLOWED_IP = "60.150.253.112"  # ←ご自身のグローバルIP

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w', encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def ensure_vip_level(user):
    # vip_levelは1~4。なければ1
    if 'vip_level' not in user or not isinstance(user['vip_level'], int):
        user['vip_level'] = 1
    if user['vip_level'] < 1 or user['vip_level'] > 4:
        user['vip_level'] = 1
    return user

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    invite_code = ''
    VALID_INVITE_CODES = ['TeB7fuH5']
    error = None
    invite_code_error = None
    username = ''
    email = ''

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        pw = request.form['password']
        invite_code = request.form.get('invite_code', '').strip()
        users = load_users()
        if not re.fullmatch(r'[A-Za-z0-9]+', username):
            error = 'ユーザーネームは英字と数字のみ利用できます'
        elif len(username) <= 5:
            error = 'ユーザーネームは6文字以上で入力してください'
        elif len(pw) <= 5:
            error = 'パスワードは6文字以上で入力してください'
        elif email in users:
            error = '既に登録済みのメールアドレスです'
        elif any(u.get('username') == username for u in users.values()):
            error = 'そのユーザーネームは既に使われています'
        elif not invite_code:
            invite_code_error = '招待コードは必須です'
        elif invite_code not in VALID_INVITE_CODES:
            invite_code_error = '有効な招待コードではありません'
        else:
            users[email] = {
                "username": username,
                "email": email,
                "password": pw,
                "profile_completed": False,
                "invite_code": invite_code,
                "vip_level": 1  # 初期値
            }
            save_users(users)
            return redirect(url_for('login'))
    return render_template(
        'register.html',
        error=error,
        username=username,
        email=email,
        invite_code=invite_code,
        invite_code_error=invite_code_error
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return render_template('redirect_loading.html', redirect_url=url_for('mypage'))
    error = None
    if request.method == 'POST':
        login_id = request.form['email']
        pw = request.form['password']
        users = load_users()
        user = users.get(login_id)
        if not user:
            for u in users.values():
                if u.get('username') == login_id:
                    user = u
                    break
        if user and user['password'] == pw:
            session['user'] = user['email']
            user = ensure_vip_level(user)
            if not user.get('profile_completed'):
                return render_template('redirect_loading.html', redirect_url=url_for('profile_name'))
            else:
                return render_template('redirect_loading.html', redirect_url=url_for('mypage'))
        else:
            error = 'メールアドレス/ユーザーネームまたはパスワードが間違っています'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/profile/name', methods=['GET', 'POST'])
def profile_name():
    if 'user' not in session:
        return redirect(url_for('register'))
    name = session.get('profile_name', '')
    birthday = session.get('profile_birthday', '')
    if request.method == 'POST':
        name = request.form['name']
        birthday = request.form['birthday']
        session['profile_name'] = name
        session['profile_birthday'] = birthday
        return redirect(url_for('profile_device'))
    return render_template('profile_name.html', name=name, birthday=birthday)

@app.route('/profile/device', methods=['GET', 'POST'])
def profile_device():
    if 'user' not in session:
        return redirect(url_for('register'))
    users = load_users()
    device = session.get('profile_device', '')
    name = session.get('profile_name', '')
    birthday = session.get('profile_birthday', '')
    if request.method == 'POST':
        if 'back' in request.form:
            return redirect(url_for('profile_name'))
        device = request.form.get('device', '')
        session['profile_device'] = device
        email = session['user']
        users[email]['name'] = name
        users[email]['birthday'] = birthday
        users[email]['device'] = device
        users[email]['profile_completed'] = True
        users[email]['balance'] = users[email].get('balance', 0)
        users[email]['bonus_pending'] = True
        users[email]['bonus_wait_start'] = int(time.time())
        users[email]['notifications'] = users[email].get('notifications', [])
        users[email]['vip_level'] = users[email].get('vip_level', 1)
        save_users(users)
        session.pop('profile_name', None)
        session.pop('profile_birthday', None)
        session.pop('profile_device', None)
        return redirect(url_for('mypage'))
    return render_template('profile_device.html', device=device)

@app.route('/home')
def mypage():
    if 'user' not in session:
        return redirect(url_for('login'))
    users = load_users()
    user = users.get(session['user'])
    if user and not user.get('profile_completed'):
        return redirect(url_for('profile_name'))
    user = ensure_vip_level(user)
    now = int(time.time())
    updated = False
    if user and user.get('bonus_pending') and user.get('bonus_wait_start'):
        if now - user['bonus_wait_start'] >= 60:
            user['balance'] = user.get('balance', 0) + 300
            user['bonus_pending'] = False
            user['notifications'] = user.get('notifications', [])
            user['notifications'].insert(0, {
                "title": "貴方の残高に300円が付与されました",
                "desc": "招待キャンペーン",
                "timestamp": now,
                "unread": True
            })
            updated = True
    has_unread_notification = any(n.get('unread', False) for n in user.get('notifications', []))
    if updated:
        users[session['user']] = user
        save_users(users)
    return render_template(
        'home.html',
        user=user,
        notifications=user.get('notifications', []),
        has_unread_notification=has_unread_notification
    )

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    real_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if real_ip and ',' in real_ip:
        real_ip = real_ip.split(',')[0].strip()
    if real_ip != ADMIN_ALLOWED_IP:
        abort(404)
    error = None
    if request.method == 'POST':
        user = request.form['username']
        pw = request.form['password']
        if user == ADMIN_USER and pw == ADMIN_PASS:
            session['is_admin'] = True
            return redirect(url_for('admin_users'))
        else:
            error = "ユーザー名またはパスワードが違います"
    return render_template('admin_login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('admin_login'))

def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/users', methods=['GET', 'POST'])
@admin_login_required
def admin_users():
    users = load_users()
    if request.method == 'POST':
        email = request.form.get('email')
        vip_level = request.form.get('vip_level')
        if email in users:
            try:
                v = int(vip_level)
                if v < 1 or v > 4:
                    v = 1
                users[email]['vip_level'] = v
            except Exception:
                users[email]['vip_level'] = 1
            save_users(users)
    for u in users.values():
        ensure_vip_level(u)
    return render_template('admin_users.html', users=users)

@app.route('/admin/add_user')
@admin_login_required
def admin_add_user():
    return "未実装: add_user"

@app.route('/admin/delete_user/<email>', methods=['POST'])
@admin_login_required
def admin_delete_user(email):
    users = load_users()
    if email in users:
        users.pop(email)
        save_users(users)
    return redirect(url_for('admin_users'))

@app.route('/admin/reset_password/<email>', methods=['GET', 'POST'])
@admin_login_required
def admin_reset_password(email):
    users = load_users()
    user = users.get(email)
    if not user:
        return redirect(url_for('admin_users'))
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        if not new_password:
            return render_template('admin_reset_password.html', user=user, error="新しいパスワードを入力してください")
        user['password'] = new_password
        users[email] = user
        save_users(users)
        return redirect(url_for('admin_users'))
    return render_template('admin_reset_password.html', user=user)

@app.route('/admin/send_notification', methods=['POST'])
@admin_login_required
def admin_send_notification():
    if not session.get('is_admin'):
        return jsonify({'ok': False, 'message': '管理者権限が必要です'}), 403

    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({'ok': False, 'message': 'リクエストデータ不正'}), 400

    email = data.get('email')
    title = data.get('title')
    desc = data.get('desc')
    if not email or not title or not desc:
        return jsonify({'ok': False, 'message': '全ての項目を入力してください'}), 400

    users = load_users()
    user = users.get(email)
    if not user:
        return jsonify({'ok': False, 'message': f'ユーザー({email})が見つかりません'}), 404

    if 'notifications' not in user or not isinstance(user['notifications'], list):
        user['notifications'] = []
    user['notifications'].insert(0, {
        'title': title,
        'desc': desc,
        'timestamp': int(time.time()),
        'unread': True
    })
    users[email] = user

    try:
        save_users(users)
    except Exception as e:
        return jsonify({'ok': False, 'message': f'通知保存エラー: {e}'}), 500

    return jsonify({'ok': True, 'message': '通知を送信しました'})

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/user')
def user_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    users = load_users()
    user = users.get(session['user'])
    user = ensure_vip_level(user)
    total_balance = user.get('balance', 0) if user else 0
    today_profit = 0  # 必要なら今日の収益ロジックを追加
    notifications = user.get('notifications', []) if user else []
    return render_template(
        'user.html',
        user=user,
        total_balance=total_balance,
        today_profit=today_profit,
        notifications=notifications
    )

@app.route('/deposit')
def deposit():
    return render_template('deposit.html') 

@app.route('/withdraw')
def withdraw():
    return render_template('withdraw.html')

@app.route('/user_settings')
def user_settings():
    return render_template('user_settings.html')

@app.route('/account_delete', methods=['POST'])
def account_delete():
    # ここにアカウント削除処理を書く
    # 例: ユーザーをデータベースから削除
    return redirect(url_for('home'))  # 適切な遷移先に変更

@app.route('/vip_detail')
def vip_detail():
    return render_template('vip_detail.html')

@app.route('/notification_read', methods=['POST'])
def notification_read():
    if 'user' not in session:
        return '', 401
    users = load_users()
    user = users.get(session['user'])
    if user and 'notifications' in user:
        for n in user['notifications']:
            n['unread'] = False
        save_users(users)
    return '', 204


@app.route('/admin/change_balance/<email>', methods=['POST'])
@admin_login_required
def admin_change_balance(email):
    users = load_users()
    user = users.get(email)
    if not user:
        return redirect(url_for('admin_users'))
    try:
        change = int(request.form['balance_change'])
    except Exception:
        return redirect(url_for('admin_users'))
    user['balance'] = user.get('balance', 0) + change
    if user['balance'] < 0:
        user['balance'] = 0
    users[email] = user
    save_users(users)
    return redirect(url_for('admin_users'))

@app.route('/survey_list')
def survey_list():
    if 'user' not in session:
        return redirect(url_for('login'))
    users = load_users()
    user = users.get(session['user'])
    if not user:
        return redirect(url_for('login'))
    user = ensure_vip_level(user)
    return render_template('survey_list.html', user=user)

# アンケート回答API
@app.route('/survey_answer', methods=['POST'])
def survey_answer():
    if 'user' not in session:
        return jsonify({'ok': False}), 401
    users = load_users()
    user = users.get(session['user'])
    if not user:
        return jsonify({'ok': False}), 404

    # 通知を追加
    user.setdefault('notifications', [])
    user['notifications'].insert(0, {
        'title': 'アンケートの回答ありがとうございました！',
        'desc': '残高付与までもう暫くお待ちください。',
        'timestamp': int(time.time()),
        'unread': True
    })
    users[session['user']] = user
    save_users(users)
    return jsonify({'ok': True})
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)