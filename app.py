# -*- coding: utf-8 -*-
"""电子票夹博物馆系统 - Flask 主程序"""
import os
import time as time_mod
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, abort

from werkzeug.utils import secure_filename

from config import UPLOAD_FOLDER, MAX_CONTENT_LENGTH, TICKET_TYPES, BAIDU_OCR_ENABLED, SECRET_KEY
from database import (
    init_db,
    add_ticket,
    get_ticket_by_id,
    get_tickets_by_type,
    get_tickets_by_time,
    search_tickets,
    update_ticket,
    delete_ticket,
    create_user,
    verify_user,
    user_owns_image_path,
    get_home_mini_stats,
    get_city_stats,
    get_yearly_stats,
    get_map_tickets,
)
from ocr_service import extract_ticket_fields
from auth_utils import login_required, login_user, logout_user, current_user_id

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    if 'image_path' in d and d['image_path']:
        d['image_url'] = '/' + d['image_path'].replace('\\', '/')
    return d


# ---------- 登录 / 注册 ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user_id():
        return redirect(url_for('index'))
    err = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = verify_user(username, password)
        if user:
            login_user(user['id'], user['username'])
            nxt = request.form.get('next') or request.args.get('next') or url_for('index')
            if not nxt.startswith('/'):
                nxt = url_for('index')
            return redirect(nxt)
        err = '用户名或密码错误'
    return render_template('login.html', error=err)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user_id():
        return redirect(url_for('index'))
    err = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')
        if len(username) < 2:
            err = '用户名至少 2 个字符'
        elif len(password) < 6:
            err = '密码至少 6 位'
        elif password != confirm:
            err = '两次密码不一致'
        else:
            uid = create_user(username, password)
            if uid:
                login_user(uid, username)
                return redirect(url_for('index'))
            err = '用户名已被占用'
    return render_template('register.html', error=err)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


# ---------- 页面路由（需登录）----------
@app.route('/')
@login_required
def index():
    return render_template('index.html', types=TICKET_TYPES, current_page='index')


@app.route('/upload')
@login_required
def upload_page():
    return render_template('upload.html', types=TICKET_TYPES[1:], current_page='upload')


@app.route('/list')
@login_required
def list_page():
    return render_template('list.html', types=TICKET_TYPES, current_page='list')


@app.route('/timeline')
@login_required
def timeline_page():
    return render_template('timeline.html', types=TICKET_TYPES, current_page='timeline')


@app.route('/detail/<int:ticket_id>')
@login_required
def detail_page(ticket_id):
    return render_template('detail.html', ticket_id=ticket_id, types=TICKET_TYPES[1:], current_page='list')


# ---------- 页面路由：地图与统计 ----------
@app.route('/map')
@login_required
def map_page():
    return render_template('map.html', types=TICKET_TYPES, current_page='map')


@app.route('/stats')
@login_required
def stats_page():
    return render_template('stats.html', types=TICKET_TYPES, current_page='stats')


# ---------- 图片访问（仅本人数据）----------
@app.route('/static/uploads/<path:relative>')
@login_required
def uploaded_file(relative):
    rel = relative.replace('\\', '/')
    if '..' in rel or rel.startswith('/'):
        abort(404)
    uid = current_user_id()
    parts = rel.split('/')
    if len(parts) >= 2 and parts[0].isdigit():
        if int(parts[0]) != uid:
            abort(403)
        folder = os.path.join(UPLOAD_FOLDER, parts[0])
        filename = parts[1] if len(parts) == 2 else os.path.join(*parts[1:])
        abs_file = os.path.normpath(os.path.join(folder, filename))
        if not abs_file.startswith(os.path.normpath(os.path.abspath(folder)) + os.sep):
            abort(404)
        if not os.path.isfile(abs_file):
            abort(404)
        return send_from_directory(folder, filename)
    path_in_db = 'static/uploads/' + rel
    if not user_owns_image_path(uid, path_in_db):
        abort(403)
    full = os.path.join(UPLOAD_FOLDER, rel)
    if not os.path.isfile(full):
        abort(404)
    return send_from_directory(UPLOAD_FOLDER, rel)


# ---------- API：上传 ----------
@app.route('/api/tickets', methods=['POST'])
@login_required
def api_upload():
    uid = current_user_id()
    data = request.form
    type_ = data.get('type', '').strip()
    platform = data.get('platform', '').strip()
    time_ = data.get('time', '').strip()
    place = data.get('place', '').strip()
    notes = data.get('notes', '').strip()
    ocr_text = data.get('ocr_text', '').strip()
    theme_color = data.get('theme_color', '').strip()
    province = data.get('province', '').strip()
    city = data.get('city', '').strip()
    if not type_:
        return jsonify({'success': False, 'message': '请输入票据类型'}), 400
    if not time_:
        return jsonify({'success': False, 'message': '请选择时间'}), 400
    image_path = None
    if 'image' in request.files:
        f = request.files['image']
        if f and f.filename and allowed_file(f.filename):
            filename = secure_filename(f.filename)
            base, ext = os.path.splitext(filename)
            filename = f"{base}_{int(time_mod.time() * 1000)}{ext}"
            user_dir = os.path.join(UPLOAD_FOLDER, str(uid))
            os.makedirs(user_dir, exist_ok=True)
            path = os.path.join(user_dir, filename)
            f.save(path)
            image_path = f'static/uploads/{uid}/{filename}'.replace('\\', '/')
    try:
        tid = add_ticket(uid, type_, platform, time_, place, notes, image_path, ocr_text, theme_color, province, city)
        return jsonify({'success': True, 'id': tid, 'message': '上传成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tickets')
@login_required
def api_list():
    uid = current_user_id()
    type_ = request.args.get('type', '全部')
    data = get_tickets_by_type(type_, uid)
    for item in data:
        if item.get('image_path'):
            item['image_url'] = '/' + item['image_path'].replace('\\', '/')
    return jsonify({'success': True, 'data': data})


@app.route('/api/tickets/timeline')
@login_required
def api_timeline():
    uid = current_user_id()
    data = get_tickets_by_time(uid)
    for item in data:
        if item.get('image_path'):
            item['image_url'] = '/' + item['image_path'].replace('\\', '/')
    return jsonify({'success': True, 'data': data})


@app.route('/api/tickets/search')
@login_required
def api_search():
    uid = current_user_id()
    keyword = request.args.get('q', '')
    type_ = request.args.get('type', '全部')
    data = search_tickets(keyword, uid, type_=type_)
    for item in data:
        if item.get('image_path'):
            item['image_url'] = '/' + item['image_path'].replace('\\', '/')
    return jsonify({'success': True, 'data': data})


@app.route('/api/stats/mini')
@login_required
def api_stats_mini():
    uid = current_user_id()
    try:
        stats = get_home_mini_stats(uid)
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/home/widgets')
@login_required
def api_home_widgets():
    uid = current_user_id()
    try:
        featured = get_featured_tickets(uid, 5)
        top_places = get_top_places(uid, 12)
        return jsonify({
            'success': True,
            'data': {
                'featured': featured,
                'top_places': top_places,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/stats/overview')
@login_required
def api_stats_overview():
    uid = current_user_id()
    try:
        stats = get_user_stats(uid)
        return jsonify({
            'success': True,
            'data': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tickets/<int:ticket_id>')
@login_required
def api_detail(ticket_id):
    uid = current_user_id()
    row = get_ticket_by_id(ticket_id, uid)
    if not row:
        return jsonify({'success': False, 'message': '票据不存在'}), 404
    d = row_to_dict(row)
    return jsonify({'success': True, 'data': d})


@app.route('/api/ocr/extract', methods=['POST'])
@login_required
def api_ocr_extract():
    if not BAIDU_OCR_ENABLED:
        return jsonify({
            'success': False,
            'message': '未配置百度 OCR 接口，请先在环境变量中设置 BAIDU_OCR_API_KEY / BAIDU_OCR_SECRET_KEY'
        }), 400
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': '请先选择要识别的图片'}), 400
    f = request.files['image']
    if not f or not f.filename:
        return jsonify({'success': False, 'message': '图片无效'}), 400
    if not allowed_file(f.filename):
        return jsonify({'success': False, 'message': '暂不支持的图片格式'}), 400
    try:
        image_bytes = f.read()
        if not image_bytes:
            return jsonify({'success': False, 'message': '图片内容为空'}), 400
        fields = extract_ticket_fields(image_bytes)
        return jsonify({'success': True, 'data': fields})
    except Exception as e:
        return jsonify({'success': False, 'message': f'OCR 识别失败：{e}'}), 500


@app.route('/api/tickets/<int:ticket_id>', methods=['PUT'])
@login_required
def api_update(ticket_id):
    uid = current_user_id()
    row = get_ticket_by_id(ticket_id, uid)
    if not row:
        return jsonify({'success': False, 'message': '票据不存在'}), 404
    data = request.form
    type_ = data.get('type', '').strip()
    platform = data.get('platform', '').strip()
    time_ = data.get('time', '').strip()
    place = data.get('place', '').strip()
    notes = data.get('notes', '').strip()
    ocr_text = data.get('ocr_text', '').strip()
    theme_color = data.get('theme_color', '').strip()
    province = data.get('province', '').strip()
    city = data.get('city', '').strip()
    if not type_:
        return jsonify({'success': False, 'message': '请输入票据类型'}), 400
    if not time_:
        return jsonify({'success': False, 'message': '请选择时间'}), 400
    image_path = None
    if 'image' in request.files:
        f = request.files['image']
        if f and f.filename and allowed_file(f.filename):
            filename = secure_filename(f.filename)
            base, ext = os.path.splitext(filename)
            filename = f"{base}_{int(time_mod.time() * 1000)}{ext}"
            user_dir = os.path.join(UPLOAD_FOLDER, str(uid))
            os.makedirs(user_dir, exist_ok=True)
            path = os.path.join(user_dir, filename)
            f.save(path)
            image_path = f'static/uploads/{uid}/{filename}'.replace('\\', '/')
    try:
        ok = update_ticket(ticket_id, uid, type_, platform, time_, place, notes, image_path, ocr_text, theme_color, province, city)
        if not ok:
            return jsonify({'success': False, 'message': '票据不存在'}), 404
        return jsonify({'success': True, 'message': '更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tickets/<int:ticket_id>', methods=['DELETE'])
@login_required
def api_delete(ticket_id):
    uid = current_user_id()
    row = get_ticket_by_id(ticket_id, uid)
    if not row:
        return jsonify({'success': False, 'message': '票据不存在'}), 404
    old_path = delete_ticket(ticket_id, uid)
    if old_path:
        full = os.path.join(os.path.dirname(__file__), old_path)
        if os.path.isfile(full):
            try:
                os.remove(full)
            except OSError:
                pass
    return jsonify({'success': True, 'message': '删除成功'})


# ---------- API：地图与统计 ----------
@app.route('/api/stats/cities')
@login_required
def api_cities():
    uid = current_user_id()
    try:
        stats = get_city_stats(uid)
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/stats/yearly')
@login_required
def api_yearly():
    uid = current_user_id()
    try:
        stats = get_yearly_stats(uid)
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/tickets/map')
@login_required
def api_map():
    uid = current_user_id()
    data = get_map_tickets(uid)
    for item in data:
        if item.get('image_path'):
            item['image_url'] = '/' + item['image_path'].replace('\\', '/')
    return jsonify({'success': True, 'data': data})


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
