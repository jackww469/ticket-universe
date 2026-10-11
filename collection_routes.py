"""Collection tools: locations, thumbnails, recycle bin and portable ZIP backups."""
import datetime
import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import PurePosixPath

from flask import Blueprint, current_app, jsonify, request, render_template, send_file
from PIL import Image, ImageOps

from auth_utils import login_required, current_user_id
from database import (get_db, TICKET_FIELDS, validate_ticket, save_ticket_record,
                      duplicate_image, trash_tickets, restore_ticket, purge_ticket)
from locations import LOCATIONS
from media_service import inspect_image, save_image, local_image, remove_media, MAX_IMAGE_BYTES

collection = Blueprint('collection', __name__)
MAX_BACKUP_BYTES = 100 * 1024 * 1024


@collection.before_app_request
def backup_size_limit():
    # Single uploads include multipart overhead; the image itself is limited to 5 MB.
    request.max_content_length = MAX_BACKUP_BYTES if request.path == '/api/backup/import' else 6 * 1024 * 1024


@collection.app_errorhandler(413)
def too_large(error):
    return jsonify(success=False, message='文件过大：图片最多 5MB，备份最多 100MB'), 413


def find_duplicate(user_id, digest, exclude_id=0):
    # Backfill legacy image hashes once, without changing originals.
    with get_db() as conn:
        rows = conn.execute("SELECT id, image_path FROM tickets WHERE user_id=? AND image_path != '' AND (image_hash IS NULL OR image_hash='')", (user_id,)).fetchall()
        for row in rows:
            path = local_image(row['image_path'], current_app.config['UPLOAD_FOLDER'])
            if path and path.is_file():
                with path.open('rb') as stream:
                    digest_builder = hashlib.sha256()
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        digest_builder.update(chunk)
                    image_hash = digest_builder.hexdigest()
                conn.execute('UPDATE tickets SET image_hash=? WHERE id=? AND user_id=?', (image_hash, row['id'], user_id))
    return duplicate_image(user_id, digest, exclude_id)


@collection.get('/api/locations')
@login_required
def locations():
    return jsonify(success=True, data=LOCATIONS)


@collection.get('/api/tickets/<int:ticket_id>/thumbnail')
@login_required
def thumbnail(ticket_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM tickets WHERE id=? AND user_id=?', (ticket_id, current_user_id())).fetchone()
        if not row:
            return jsonify(success=False, message='图片不存在'), 404
        original = local_image(row['image_path'], current_app.config['UPLOAD_FOLDER'])
        if not original or not original.is_file():
            return jsonify(success=False, message='图片不存在'), 404
        thumb = local_image(row['thumbnail_path'], current_app.config['UPLOAD_FOLDER'])
        if not thumb or not thumb.is_file():
            thumb = original.with_name(original.name + '.thumb.jpg')
            try:
                data = original.read_bytes()
                _, digest = inspect_image(data)
                with Image.open(io.BytesIO(data)) as image:
                    image = ImageOps.exif_transpose(image)
                    image.thumbnail((640, 640))
                    image.convert('RGB').save(thumb, 'JPEG', quality=80, optimize=True)
                prefix = row['image_path'].rsplit('/', 1)[0]
                conn.execute('UPDATE tickets SET thumbnail_path=?, image_hash=? WHERE id=? AND user_id=?',
                             (prefix + '/' + thumb.name, digest, ticket_id, current_user_id()))
            except (ValueError, OSError):
                return jsonify(success=False, message='无法生成缩略图'), 400
    response = send_file(thumb, mimetype='image/jpeg', conditional=True)
    response.headers['Cache-Control'] = 'private, no-cache'
    return response


@collection.get('/collection')
@login_required
def collection_page():
    return render_template('collection.html', current_page='list')


@collection.get('/api/trash')
@login_required
def trash():
    rows = trash_tickets(current_user_id())
    for row in rows:
        if row.get('image_path'):
            row['thumbnail_url'] = f"/api/tickets/{row['id']}/thumbnail"
    return jsonify(success=True, data=rows)


@collection.post('/api/trash/<int:ticket_id>/restore')
@login_required
def restore(ticket_id):
    if not restore_ticket(ticket_id, current_user_id()):
        return jsonify(success=False, message='票据不存在或已超过 30 天恢复期限'), 404
    return jsonify(success=True, message='票据已恢复')


@collection.delete('/api/trash/<int:ticket_id>')
@login_required
def purge(ticket_id):
    row = purge_ticket(ticket_id, current_user_id())
    if not row:
        return jsonify(success=False, message='回收站票据不存在'), 404
    remove_media(row, current_app.config['UPLOAD_FOLDER'])
    return jsonify(success=True, message='已永久删除')


@collection.get('/api/backup/export')
@login_required
def export_backup():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM active_tickets WHERE user_id=? ORDER BY id', (current_user_id(),)).fetchall()
    output = tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024)
    try:
        tickets = []
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for row in rows:
                item = {key: row[key] or '' for key in TICKET_FIELDS}
                item['created_at'] = row['created_at']
                path = local_image(row['image_path'], current_app.config['UPLOAD_FOLDER'])
                if row['image_path'] and (not path or not path.is_file()):
                    raise ValueError(f"票据 {row['id']} 的原图缺失，请修复后再备份")
                if path:
                    item['image'] = f"images/{row['id']}{path.suffix}"
                    archive.write(path, item['image'])
                tickets.append(item)
            archive.writestr('manifest.json', json.dumps({'version': 1, 'tickets': tickets}, ensure_ascii=False))
        output.seek(0)
        response = send_file(output, mimetype='application/zip', as_attachment=True, download_name='ticket-universe-backup.zip')
        response.call_on_close(output.close)
        response.headers['Cache-Control'] = 'no-store'
        return response
    except ValueError as exc:
        output.close()
        return jsonify(success=False, message=str(exc)), 400
    except Exception:
        output.close()
        raise


def fingerprint(fields, digest):
    return json.dumps([fields.get(key, '') or '' for key in TICKET_FIELDS] + [digest or ''], ensure_ascii=False)


@collection.post('/api/backup/import')
@login_required
def import_backup():
    file = request.files.get('backup')
    if not file:
        return jsonify(success=False, message='请选择备份 ZIP 文件'), 400
    created_media = []
    try:
        with zipfile.ZipFile(file.stream) as archive:
            members = archive.infolist()
            if len(members) > 2001 or len({m.filename for m in members}) != len(members):
                raise ValueError('备份条目过多或存在重复路径')
            if sum(m.file_size for m in members) > 200 * 1024 * 1024:
                raise ValueError('备份解压后不能超过 200MB')
            if archive.getinfo('manifest.json').file_size > 4 * 1024 * 1024:
                raise ValueError('备份清单过大')
            manifest = json.loads(archive.read('manifest.json'))
            if not isinstance(manifest, dict) or manifest.get('version') != 1:
                raise ValueError('不支持的备份版本')
            items = manifest.get('tickets')
            if not isinstance(items, list) or len(items) > 1000:
                raise ValueError('一次最多恢复 1000 张票据')
            prepared = []
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError('备份票据格式无效')
                fields = validate_ticket(item)
                data, digest = None, ''
                name = item.get('image')
                if name:
                    if not isinstance(name, str) or '\\' in name or PurePosixPath(name).parts[:1] != ('images',) or '..' in PurePosixPath(name).parts:
                        raise ValueError('备份图片路径无效')
                    if archive.getinfo(name).file_size > MAX_IMAGE_BYTES:
                        raise ValueError('备份中单张图片超过 5MB')
                    data = archive.read(name)
                    _, digest = inspect_image(data)
                created = item.get('created_at')
                if created:
                    try:
                        datetime.datetime.fromisoformat(created)
                    except (ValueError, TypeError):
                        raise ValueError('收藏时间无效')
                prepared.append((fields, data, digest, created))
        uid = current_user_id()
        find_duplicate(uid, '')  # Also makes legacy records comparable to restored images.
        imported, skipped = 0, 0
        with get_db() as conn:
            existing = {fingerprint(dict(r), r['image_hash']) for r in conn.execute('SELECT * FROM tickets WHERE user_id=?', (uid,))}
            for fields, data, digest, created in prepared:
                key = fingerprint(fields, digest)
                if key in existing:
                    skipped += 1
                    continue
                media = save_image(data, uid, current_app.config['UPLOAD_FOLDER']) if data else None
                if media:
                    created_media.append(media)
                tid = save_ticket_record(uid, fields, media, conn=conn)
                if created:
                    conn.execute('UPDATE tickets SET created_at=? WHERE id=? AND user_id=?', (created, tid, uid))
                existing.add(key)
                imported += 1
        return jsonify(success=True, imported=imported, skipped=skipped,
                       message=f'恢复 {imported} 张，跳过 {skipped} 张已存在的票据（含回收站）')
    except (ValueError, KeyError, zipfile.BadZipFile, UnicodeDecodeError, RuntimeError) as exc:
        for media in created_media:
            remove_media(media, current_app.config['UPLOAD_FOLDER'])
        return jsonify(success=False, message='备份无效：' + str(exc)), 400
    except Exception:
        for media in created_media:
            remove_media(media, current_app.config['UPLOAD_FOLDER'])
        current_app.logger.exception('Backup import failed')
        return jsonify(success=False, message='恢复失败，未导入票据'), 500
