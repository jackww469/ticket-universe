import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import app as web
import database
import collection_routes
from locations import LOCATIONS, normalize_location, extract_location


def picture(color='red', size=(1200, 900)):
    out = io.BytesIO()
    Image.new('RGB', size, color).save(out, 'PNG')
    return out.getvalue()


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.uploads = self.root / 'uploads'
        self.uploads.mkdir()
        for target, name, value in [(database, 'DATABASE_PATH', str(self.root / 'test.db')),
                                     (web, 'UPLOAD_FOLDER', str(self.uploads))]:
            mock = patch.object(target, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        config = patch.dict(web.app.config, UPLOAD_FOLDER=str(self.uploads), TESTING=True)
        config.start()
        self.addCleanup(config.stop)
        database.init_db()
        self.uid = database.create_user('collector', 'testing-password')
        self.other = database.create_user('someone-else', 'testing-password')
        self.client = web.app.test_client()
        self.login(self.uid)

    def login(self, uid):
        with self.client.session_transaction() as session:
            session['user_id'] = uid

    def upload(self, data=None, **fields):
        payload = {'type': '车票', 'time': '2024-01-02', 'province': '浙江省', 'city': '杭州市', 'platform': '12306'}
        payload.update(fields)
        if data is not None:
            payload['image'] = (io.BytesIO(data), '票根.png')
        return self.client.post('/api/tickets', data=payload)

    def get_record(self, tid):
        with database.get_db() as conn:
            return dict(conn.execute('SELECT * FROM tickets WHERE id=?', (tid,)).fetchone())

    def export(self):
        response = self.client.get('/api/backup/export')
        self.assertEqual(response.status_code, 200)
        data = response.data
        response.close()
        return data

    def restore(self, data):
        return self.client.post('/api/backup/import', data={'backup': (io.BytesIO(data), 'backup.zip')})

    def test_locations_normalize_and_preserve_unknown(self):
        self.assertEqual(normalize_location('浙江省', '杭州市'), ('浙江', '杭州'))
        self.assertEqual(normalize_location('', '深圳市'), ('广东', '深圳'))
        self.assertEqual(normalize_location('新疆维吾尔自治区', '乌鲁木齐市'), ('新疆', '乌鲁木齐'))
        self.assertEqual(normalize_location('海外', '京都'), ('海外', '京都'))

    def test_ocr_city_inference_and_ambiguous_candidates(self):
        self.assertEqual(extract_location('杭州东站')['province'], '浙江')
        self.assertEqual(extract_location('南京演唱会')['city'], '南京')
        result = extract_location('北京南 → 上海虹桥')
        self.assertEqual(result['city'], '')
        self.assertEqual(len(result['candidates']), 2)
        with patch.dict(LOCATIONS, {'甲省': ['同名城'], '乙省': ['同名城']}):
            self.assertEqual(extract_location('同名城')['city'], '')
            self.assertEqual(extract_location('甲省同名城')['province'], '甲省')

    def test_upload_normalization_and_private_thumbnail(self):
        data = picture()
        response = self.upload(data)
        self.assertEqual(response.status_code, 200)
        tid = response.json['id']
        detail = self.client.get(f'/api/tickets/{tid}').json['data']
        self.assertEqual((detail['province'], detail['city']), ('浙江', '杭州'))
        thumb = self.client.get(detail['thumbnail_url'])
        self.assertEqual(thumb.status_code, 200)
        with Image.open(io.BytesIO(thumb.data)) as image:
            self.assertLessEqual(max(image.size), 640)
        thumb.close()
        self.login(self.other)
        self.assertEqual(self.client.get(detail['thumbnail_url']).status_code, 404)
        self.assertEqual(self.client.get(detail['image_url']).status_code, 403)

    def test_duplicate_warning_requires_explicit_override(self):
        data = picture()
        first = self.upload(data).json['id']
        duplicate = self.upload(data)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json['duplicate']['id'], first)
        self.assertEqual(self.upload(data, allow_duplicate='1').status_code, 200)
        self.login(self.other)
        self.assertEqual(self.upload(data).status_code, 200)

    def test_invalid_image_and_date_do_not_create_files_or_records(self):
        self.assertEqual(self.upload(b'not-an-image').status_code, 400)
        self.assertEqual(self.upload(picture(), time='2024-02-31').status_code, 400)
        self.assertEqual(self.client.get('/api/tickets').json['total'], 0)
        self.assertEqual(list(self.uploads.rglob('*')), [])

    def test_combined_filters_pagination_and_stable_order(self):
        ids = [self.upload(type='音乐节票').json['id'] for _ in range(6)]
        self.upload(city='上海市', province='上海', platform='大麦')
        result = self.client.get('/api/tickets', query_string={
            'type': '其他', 'province': '浙江省', 'city': '杭州市', 'platform': '12306',
            'date_from': '2024-01-01', 'date_to': '2024-01-31', 'q': '音乐节', 'page': 2, 'per_page': 2,
        }).json
        self.assertEqual(result['total'], 6)
        self.assertEqual(result['pages'], 3)
        self.assertEqual([r['id'] for r in result['data']], list(reversed(ids))[2:4])
        self.assertEqual(self.client.get('/api/tickets?page=invalid').status_code, 400)
        self.assertEqual(self.client.get('/api/tickets?date_from=2025-01-01&date_to=2024-01-01').status_code, 400)

    def test_city_aggregation_uses_province_and_counts_province_only(self):
        self.upload(city='同名城', province='甲省')
        self.upload(city='同名城', province='乙省')
        self.upload(city='', province='浙江省')
        result = self.client.get('/api/stats/cities').json['data']
        self.assertEqual(result['total_cities'], 2)
        self.assertEqual(result['total_provinces'], 3)
        self.assertEqual(result['total_tickets'], 3)

    def test_soft_delete_hides_ticket_everywhere_and_restore_keeps_original(self):
        tid = self.upload(picture()).json['id']
        original = self.get_record(tid)['image_path']
        self.assertEqual(self.client.delete(f'/api/tickets/{tid}').status_code, 200)
        self.assertEqual(self.client.get('/api/tickets').json['total'], 0)
        self.assertEqual(self.client.get('/api/stats/overview').json['data']['total'], 0)
        self.assertEqual(self.client.get('/api/stats/yearly?year=2024').json['data']['total_tickets'], 0)
        self.assertEqual(self.client.get('/api/stats/cities').json['data']['total_cities'], 0)
        self.assertEqual(self.client.get('/api/tickets/map').json['data'], [])
        self.assertIsNone(self.client.get('/api/memory/reminder').json['data']['first_ticket'])
        self.assertEqual(self.client.get(f'/api/tickets/{tid}').status_code, 404)
        self.assertEqual(self.upload(picture()).status_code, 409)
        self.assertEqual(self.client.get('/api/trash').json['data'][0]['id'], tid)
        self.assertEqual(self.client.post(f'/api/trash/{tid}/restore').status_code, 200)
        self.assertEqual(self.client.get('/api/tickets').json['total'], 1)
        self.assertEqual(self.get_record(tid)['image_path'], original)

    def test_expiry_and_user_isolation_for_recycle_bin(self):
        tid = self.upload(picture()).json['id']
        self.client.delete(f'/api/tickets/{tid}')
        self.login(self.other)
        self.assertEqual(self.client.get('/api/trash').json['data'], [])
        self.assertEqual(self.client.post(f'/api/trash/{tid}/restore').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/trash/{tid}').status_code, 404)
        self.login(self.uid)
        with database.get_db() as conn:
            conn.execute("UPDATE tickets SET deleted_at=datetime('now','-31 days') WHERE id=?", (tid,))
        self.assertFalse(self.client.get('/api/trash').json['data'][0]['can_restore'])
        self.assertEqual(self.client.post(f'/api/trash/{tid}/restore').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/trash/{tid}').status_code, 200)
        self.assertEqual(list((self.uploads / str(self.uid)).iterdir()), [])

    def test_edit_replaces_media_without_leaving_old_files(self):
        tid = self.upload(picture()).json['id']
        response = self.client.put(f'/api/tickets/{tid}', data={'type': '车票', 'time': '2025-01-01', 'image': (io.BytesIO(picture('blue')), 'new.png')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(list((self.uploads / str(self.uid)).iterdir())), 2)

    def test_backup_round_trip_is_portable_and_idempotent(self):
        original = picture()
        self.upload(original, notes='值得珍藏的回忆')
        self.upload(type='证书', city='', province='', notes='无图片记录')
        backup = self.export()
        with zipfile.ZipFile(io.BytesIO(backup)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(len(manifest['tickets']), 2)
            self.assertNotIn('user_id', manifest['tickets'][0])
        self.login(self.other)
        result = self.restore(backup)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['imported'], 2)
        self.assertEqual(self.restore(backup).json['skipped'], 2)
        self.assertEqual(self.client.get('/api/tickets').json['total'], 2)
        with database.get_db() as conn:
            row = conn.execute("SELECT * FROM tickets WHERE user_id=? AND image_path != ''", (self.other,)).fetchone()
        path = collection_routes.local_image(row['image_path'], str(self.uploads))
        self.assertEqual(path.read_bytes(), original)
        self.assertIn(f'/{self.other}/', row['image_path'])

    def test_backup_excludes_trash_and_skips_existing_trash_on_import(self):
        tid = self.upload(picture()).json['id']
        backup = self.export()
        self.client.delete(f'/api/tickets/{tid}')
        self.assertEqual(self.restore(backup).json['skipped'], 1)
        with zipfile.ZipFile(io.BytesIO(self.export())) as archive:
            self.assertEqual(json.loads(archive.read('manifest.json'))['tickets'], [])

    def test_restore_invalid_archive_is_atomic(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('manifest.json', json.dumps({'version': 1, 'tickets': [
                {'type': '车票', 'time': '2024-01-01'},
                {'type': '车票', 'time': 'invalid'},
            ]}))
        self.assertEqual(self.restore(data.getvalue()).status_code, 400)
        self.assertEqual(self.client.get('/api/tickets').json['total'], 0)
        self.assertEqual(self.restore(b'bad zip').status_code, 400)

    def test_restore_rejects_path_traversal(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('manifest.json', json.dumps({'version': 1, 'tickets': [
                {'type': '车票', 'time': '2024-01-01', 'image': 'images/../../escape.png'},
            ]}))
            archive.writestr('images/../../escape.png', picture())
        self.assertEqual(self.restore(data.getvalue()).status_code, 400)
        self.assertFalse((self.root / 'escape.png').exists())

    def test_restore_database_failure_rolls_back_files_and_rows(self):
        self.upload(picture())
        self.upload(picture('blue'))
        backup = self.export()
        self.login(self.other)
        actual = collection_routes.save_ticket_record
        calls = []
        def fail_second(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise sqlite3.OperationalError('simulated disk failure')
            return actual(*args, **kwargs)
        with patch.object(collection_routes, 'save_ticket_record', side_effect=fail_second):
            self.assertEqual(self.restore(backup).status_code, 500)
        self.assertEqual(self.client.get('/api/tickets').json['total'], 0)
        self.assertEqual(list((self.uploads / str(self.other)).iterdir()), [])

    def test_timeline_loads_selected_year_only(self):
        self.upload(time='2024-01-01')
        self.upload(time='2025-01-01')
        response = self.client.get('/api/tickets/timeline?year=2024')
        self.assertEqual([r['time'] for r in response.json['data']], ['2024-01-01'])
        self.assertIn('2025', response.json['years'])

    def test_legacy_image_gets_thumbnail_and_duplicate_hash(self):
        legacy = self.uploads / 'old.png'
        legacy.write_bytes(picture())
        tid = database.add_ticket(self.uid, '车票', '', '2024-01-01', '', '', 'static/uploads/old.png')
        thumb = self.client.get(f'/api/tickets/{tid}/thumbnail')
        self.assertEqual(thumb.status_code, 200)
        thumb.close()
        self.assertTrue(self.get_record(tid)['image_hash'])
        self.assertEqual(self.upload(picture()).status_code, 409)

    def test_migration_is_idempotent_and_normalizes_legacy_locations(self):
        tid = self.upload().json['id']
        with database.get_db() as conn:
            conn.execute("UPDATE tickets SET province='浙江省', city='杭州市' WHERE id=?", (tid,))
        database.migrate_db()
        database.migrate_db()
        self.assertEqual(self.get_record(tid)['province'], '浙江')
        with database.get_db() as conn:
            indexes = {r['name'] for r in conn.execute("PRAGMA index_list('tickets')")}
        self.assertIn('idx_tickets_user_date', indexes)

    def test_new_pages_render(self):
        for url in ['/upload', '/list', '/timeline', '/map', '/memory', '/collection']:
            self.assertEqual(self.client.get(url).status_code, 200)


if __name__ == '__main__':
    unittest.main()
