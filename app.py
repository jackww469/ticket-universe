# -*- coding: utf-8 -*-
"""电子票夹博物馆系统 - Flask 主程序"""
import os
import time as time_mod
from pathlib import Path
from media_service import save_image, inspect_image, remove_media, local_image
from locations import LOCATIONS
from database import query_tickets, validate_ticket, save_ticket_record, duplicate_image, get_db
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
    update_ticket_notes,
    delete_ticket,
    create_user,
    verify_user,
    user_owns_image_path,
    get_user_stats,
    get_home_mini_stats,
    get_city_stats,
    get_yearly_stats,
    get_map_tickets,
    get_featured_tickets,
    get_top_places,
    get_memory_reminder_data,
)
from ocr_service import extract_ticket_fields
from auth_utils import login_required, login_user, logout_user, current_user_id
from semantic_service import (
    SemanticServiceError,
    answer_memory_query,
    refresh_user_index,
    search_user_tickets,
    semantic_enabled,
)

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
        d['thumbnail_url'] = '/api/tickets/' + str(d['id']) + '/thumbnail'
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
    uid = current_user_id()
    try:
        stats = get_yearly_stats(uid)
    except Exception:
        stats = {}
    return render_template(
        'stats.html',
        types=TICKET_TYPES,
        current_page='stats',
        current_year=stats.get('current_year', ''),
        available_years=stats.get('available_years', []),
    )


@app.route('/memory')
@login_required
def memory_page():
    return render_template(
        'memory.html',
        current_page='memory',
        semantic_enabled=semantic_enabled(),
    )


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
    media = None
    try:
        uid = current_user_id()
        fields = validate_ticket(request.form)
        f = request.files.get('image')
        if f and f.filename:
            image = f.read()
            _, digest = inspect_image(image)
            duplicate = find_duplicate(uid, digest)
            if duplicate and request.form.get('allow_duplicate') != '1':
                return jsonify(success=False, message='这张图片已收藏', duplicate=duplicate), 409
            media = save_image(image, uid, app.config['UPLOAD_FOLDER'])
        tid = save_ticket_record(uid, fields, media)
        return jsonify(success=True, id=tid, message='上传成功')
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    except Exception:
        if media:
            remove_media(media, app.config['UPLOAD_FOLDER'])
        app.logger.exception('Upload failed')
        return jsonify(success=False, message='保存失败，请重试'), 500


@app.route('/api/tickets')
@login_required
def api_list():
    try:
        result = query_tickets(current_user_id(), request.args)
        result['data'] = [row_to_dict(row) for row in result['data']]
        return jsonify(success=True, **result)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400


@app.route('/api/tickets/timeline')
@login_required
def api_timeline():
    uid = current_user_id()
    years = get_yearly_stats(uid)['available_years']
    year = request.args.get('year') or (years[0] if years else '')
    if year not in years:
        return jsonify(success=False, message='请选择有效年份'), 400
    with get_db() as conn:
        data = conn.execute("SELECT * FROM active_tickets WHERE user_id=? AND strftime('%Y', time)=? ORDER BY time, id", (uid, year)).fetchall()
    return jsonify(success=True, data=[row_to_dict(row) for row in data], years=years, year=year)


@app.route('/api/tickets/search')
@login_required
def api_search():
    return api_list()


@app.route('/api/semantic/search')
@login_required
def api_semantic_search():
    try:
        result = search_user_tickets(
            current_user_id(),
            request.args.get('q', ''),
            app.config['UPLOAD_FOLDER'],
            limit=request.args.get('limit', 12),
        )
        result['data'] = [row_to_dict(row) for row in result['data']]
        return jsonify(success=True, **result)
    except (ValueError, TypeError):
        return jsonify(success=False, message='检索参数无效'), 400
    except Exception:
        app.logger.exception('Semantic search failed')
        return jsonify(success=False, message='检索失败，请稍后重试'), 500


@app.route('/api/memory/query', methods=['POST'])
@login_required
def api_memory_query():
    payload = request.get_json(silent=True) or {}
    try:
        result = answer_memory_query(
            current_user_id(),
            payload.get('query', ''),
            app.config['UPLOAD_FOLDER'],
        )
        result['results'] = [row_to_dict(row) for row in result['results']]
        return jsonify(success=True, **result)
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    except Exception:
        app.logger.exception('Memory RAG query failed')
        return jsonify(success=False, message='记忆检索失败，请稍后重试'), 500


@app.route('/api/semantic/reindex', methods=['POST'])
@login_required
def api_semantic_reindex():
    if not semantic_enabled():
        return jsonify(
            success=False,
            message='未配置 DASHSCOPE_API_KEY，当前使用本地关键词模式',
        ), 400
    try:
        result = refresh_user_index(
            current_user_id(),
            app.config['UPLOAD_FOLDER'],
            force=True,
            include_visual=True,
        )
        return jsonify(success=True, data=result, message='阿里云百炼图文语义索引已更新')
    except SemanticServiceError:
        return jsonify(success=False, message='智能服务暂时不可用，请稍后重试'), 503
    except Exception:
        app.logger.exception('Semantic reindex failed')
        return jsonify(success=False, message='索引更新失败，请稍后重试'), 500


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


@app.route('/api/memory/reminder')
@login_required
def api_memory_reminder():
    uid = current_user_id()
    try:
        data = get_memory_reminder_data(uid)
        return jsonify({'success': True, 'data': data})
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
        return jsonify(success=False, message='票据不存在'), 404
    media = None
    try:
        fields = validate_ticket(request.form)
        f = request.files.get('image')
        if f and f.filename:
            image = f.read()
            _, digest = inspect_image(image)
            duplicate = find_duplicate(uid, digest, ticket_id)
            if duplicate and request.form.get('allow_duplicate') != '1':
                return jsonify(success=False, message='这张图片已收藏', duplicate=duplicate), 409
            media = save_image(image, uid, app.config['UPLOAD_FOLDER'])
        if not save_ticket_record(uid, fields, media, ticket_id):
            if media:
                remove_media(media, app.config['UPLOAD_FOLDER'])
            return jsonify(success=False, message='票据不存在'), 404
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    except Exception:
        if media:
            remove_media(media, app.config['UPLOAD_FOLDER'])
        app.logger.exception('Update failed')
        return jsonify(success=False, message='更新失败，请重试'), 500
    if media:
        remove_media(row, app.config['UPLOAD_FOLDER'])
    return jsonify(success=True, message='更新成功')


@app.route('/api/tickets/<int:ticket_id>', methods=['DELETE'])
@login_required
def api_delete(ticket_id):
    if not delete_ticket(ticket_id, current_user_id()):
        return jsonify(success=False, message='票据不存在'), 404
    return jsonify(success=True, message='已移入回收站，30 天内可恢复')


@app.route('/api/tickets/<int:ticket_id>/notes', methods=['PATCH'])
@login_required
def api_update_notes(ticket_id):
    uid = current_user_id()
    data = request.get_json()
    notes = (data.get('notes', '') or '').strip()
    ok = update_ticket_notes(ticket_id, uid, notes)
    if not ok:
        return jsonify({'success': False, 'message': '票据不存在'}), 404
    return jsonify({'success': True, 'message': '备注已更新'})


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
        stats = get_yearly_stats(uid, request.args.get('year'))
        return jsonify({'success': True, 'data': stats})
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
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


from collection_routes import collection, find_duplicate
app.register_blueprint(collection)


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
