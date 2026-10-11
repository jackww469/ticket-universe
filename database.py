# -*- coding: utf-8 -*-
"""数据库操作封装：用户 + 票据（按 user_id 隔离）"""
import sqlite3
import datetime
import re
import json
from contextlib import contextmanager
from werkzeug.security import generate_password_hash, check_password_hash

from config import DATABASE_PATH
from locations import normalize_location

TICKET_FIELDS = ('type', 'platform', 'time', 'place', 'notes', 'ocr_text', 'theme_color', 'province', 'city')


def validate_ticket(data):
    fields = {key: str(data.get(key) or '').strip() for key in TICKET_FIELDS}
    if not fields['type']:
        raise ValueError('请输入票据类型')
    try:
        datetime.date.fromisoformat(fields['time'])
    except ValueError:
        raise ValueError('请填写有效日期，格式为 YYYY-MM-DD')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', fields['time']):
        raise ValueError('日期格式应为 YYYY-MM-DD')
    fields['province'], fields['city'] = normalize_location(fields['province'], fields['city'])
    return fields


def save_ticket_record(user_id, fields, media=None, ticket_id=None, conn=None):
    if conn is None:
        with get_db() as connection:
            return save_ticket_record(user_id, fields, media, ticket_id, connection)
    values = {key: fields.get(key, '') for key in TICKET_FIELDS}
    if media:
        values.update({key: media[key] for key in ('image_path', 'thumbnail_path', 'image_hash')})
    if ticket_id is None:
        values['user_id'] = user_id
        cur = conn.execute(f"INSERT INTO tickets ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
        return cur.lastrowid
    cur = conn.execute(f"UPDATE tickets SET {','.join(key + '=?' for key in values)} WHERE id=? AND user_id=? AND deleted_at IS NULL",
                       (*values.values(), ticket_id, user_id))
    return ticket_id if cur.rowcount else None


def query_tickets(user_id, args):
    try:
        page, per_page = max(1, int(args.get('page', 1))), min(100, max(1, int(args.get('per_page', 24))))
    except (ValueError, TypeError):
        raise ValueError('分页参数无效')
    clauses, params = ['user_id=?'], [user_id]
    type_ = args.get('type', '全部')
    if type_ == '其他':
        clauses.append("type NOT IN ('车票','演出票','景区票','证书')")
    elif type_ and type_ != '全部':
        clauses.append('type=?')
        params.append(type_)
    for key in ('platform', 'province', 'city'):
        value = args.get(key, '').strip()
        if value:
            if key == 'province':
                value = normalize_location(value, '')[0]
            if key == 'city':
                value = normalize_location('', value)[1]
            clauses.append(key + '=?')
            params.append(value)
    for key, op in (('date_from', '>='), ('date_to', '<=')):
        value = args.get(key, '')
        if value:
            try:
                datetime.date.fromisoformat(value)
            except ValueError:
                raise ValueError('筛选日期无效')
            clauses.append('substr(time,1,10)' + op + '?')
            params.append(value)
    if args.get('date_from') and args.get('date_to') and args['date_from'] > args['date_to']:
        raise ValueError('开始日期不能晚于结束日期')
    keyword = args.get('q', '').strip()
    if keyword:
        clauses.append('(' + ' OR '.join(f'{key} LIKE ?' for key in TICKET_FIELDS if key != 'theme_color') + ')')
        params.extend(['%' + keyword + '%'] * (len(TICKET_FIELDS) - 1))
    where = ' AND '.join(clauses)
    with get_db() as conn:
        total = conn.execute('SELECT COUNT(*) FROM active_tickets WHERE ' + where, params).fetchone()[0]
        rows = conn.execute('SELECT * FROM active_tickets WHERE ' + where + ' ORDER BY time DESC, id DESC LIMIT ? OFFSET ?',
                            (*params, per_page, (page - 1) * per_page)).fetchall()
    return {'data': [dict(row) for row in rows], 'total': total, 'page': page,
            'per_page': per_page, 'pages': (total + per_page - 1) // per_page}


def duplicate_image(user_id, digest, exclude_id=0):
    with get_db() as conn:
        row = conn.execute('SELECT id, type, time, deleted_at FROM tickets WHERE user_id=? AND image_hash=? AND id != ? ORDER BY id LIMIT 1',
                           (user_id, digest, exclude_id)).fetchone()
        return dict(row) if row else None


def trash_tickets(user_id):
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT *, datetime(deleted_at, '+30 days') AS expires_at, deleted_at >= datetime('now', '-30 days') AS can_restore FROM tickets WHERE user_id=? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC", (user_id,))]


def restore_ticket(ticket_id, user_id):
    with get_db() as conn:
        return conn.execute("UPDATE tickets SET deleted_at=NULL WHERE id=? AND user_id=? AND deleted_at >= datetime('now', '-30 days')", (ticket_id, user_id)).rowcount > 0


def purge_ticket(ticket_id, user_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM tickets WHERE id=? AND user_id=? AND deleted_at IS NOT NULL', (ticket_id, user_id)).fetchone()
        if row:
            conn.execute('DELETE FROM tickets WHERE id=? AND user_id=?', (ticket_id, user_id))
        return dict(row) if row else None


@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """创建用户表与票据表"""
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                platform TEXT,
                time TEXT NOT NULL,
                place TEXT,
                province TEXT,
                city TEXT,
                notes TEXT,
                image_path TEXT,
                ocr_text TEXT,
                theme_color TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ticket_embeddings (
                ticket_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                source_hash TEXT NOT NULL,
                image_hash TEXT,
                content_text TEXT NOT NULL,
                visual_text TEXT NOT NULL DEFAULT '',
                embedding_json TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                model TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
    migrate_db()


def migrate_db():
    """兼容旧库：补列、补 user_id、补 users"""
    with get_db() as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tickets'"
        )
        if not cur.fetchone():
            return
        cur = conn.execute('PRAGMA table_info(tickets)')
        cols = {row[1] for row in cur.fetchall()}

        if 'ocr_text' not in cols:
            conn.execute('ALTER TABLE tickets ADD COLUMN ocr_text TEXT')
        if 'theme_color' not in cols:
            conn.execute('ALTER TABLE tickets ADD COLUMN theme_color TEXT')
        if 'user_id' not in cols:
            conn.execute('ALTER TABLE tickets ADD COLUMN user_id INTEGER')
        if 'province' not in cols:
            conn.execute('ALTER TABLE tickets ADD COLUMN province TEXT')
        if 'city' not in cols:
            conn.execute('ALTER TABLE tickets ADD COLUMN city TEXT')

        for column in ('thumbnail_path', 'image_hash', 'deleted_at'):
            if column not in cols:
                conn.execute(f'ALTER TABLE tickets ADD COLUMN {column} TEXT')
        conn.execute('CREATE VIEW IF NOT EXISTS active_tickets AS SELECT * FROM tickets WHERE deleted_at IS NULL')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tickets_user_date ON tickets(user_id, deleted_at, time, id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tickets_user_type ON tickets(user_id, deleted_at, type, time)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tickets_user_city ON tickets(user_id, deleted_at, province, city)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tickets_user_hash ON tickets(user_id, image_hash)')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ticket_embeddings (
                ticket_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                source_hash TEXT NOT NULL,
                image_hash TEXT,
                content_text TEXT NOT NULL,
                visual_text TEXT NOT NULL DEFAULT '',
                embedding_json TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                model TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_ticket_embeddings_user ON ticket_embeddings(user_id, ticket_id)')
        for row in conn.execute('SELECT id, province, city FROM tickets').fetchall():
            province, city = normalize_location(row['province'], row['city'])
            if (province, city) != (row['province'] or '', row['city'] or ''):
                conn.execute('UPDATE tickets SET province=?, city=? WHERE id=?', (province, city, row['id']))

        # 仅当存在「无 user_id 的旧票据」时，归并到首个用户（必要时创建 default/123456）
        cur = conn.execute(
            'SELECT COUNT(*) FROM tickets WHERE user_id IS NULL'
        )
        null_ticket_count = cur.fetchone()[0]
        if null_ticket_count > 0:
            cur = conn.execute('SELECT COUNT(*) FROM users')
            n_users = cur.fetchone()[0]
            if n_users == 0:
                h = generate_password_hash('123456')
                conn.execute(
                    'INSERT INTO users (username, password_hash) VALUES (?, ?)',
                    ('default', h),
                )
            cur = conn.execute('SELECT id FROM users ORDER BY id LIMIT 1')
            first_uid = cur.fetchone()[0]
            conn.execute(
                'UPDATE tickets SET user_id = ? WHERE user_id IS NULL',
                (first_uid,),
            )


# ---------- 用户 ----------

def create_user(username: str, password: str):
    """注册：成功返回 user_id，用户名重复返回 None"""
    username = (username or '').strip()
    if not username or len(username) < 2:
        return None
    if len(username) > 32:
        return None
    h = generate_password_hash(password)
    try:
        with get_db() as conn:
            cur = conn.execute(
                'INSERT INTO users (username, password_hash) VALUES (?, ?)',
                (username, h),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def get_user_by_username(username: str):
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM users WHERE username = ?',
            ((username or '').strip(),),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        return dict(row) if row else None


def verify_user(username: str, password: str):
    u = get_user_by_username(username)
    if not u:
        return None
    if check_password_hash(u['password_hash'], password):
        return u
    return None


# ---------- 票据（均需 user_id）----------

def add_ticket(user_id, type_, platform, time_, place, notes, image_path, ocr_text='', theme_color='', province='', city=''):
    province, city = normalize_location(province, city)
    with get_db() as conn:
        cur = conn.execute(
            '''INSERT INTO tickets (user_id, type, platform, time, place, notes, image_path, ocr_text, theme_color, province, city)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                user_id, type_, platform or '', time_, place or '', notes or '',
                image_path or '', ocr_text or '', theme_color or '', province or '', city or '',
            ),
        )
        return cur.lastrowid


def get_ticket_by_id(ticket_id, user_id):
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM active_tickets WHERE id = ? AND user_id = ?',
            (ticket_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def get_tickets_by_type(type_, user_id):
    with get_db() as conn:
        if type_ == '全部' or not type_:
            rows = conn.execute(
                'SELECT * FROM active_tickets WHERE user_id = ? ORDER BY time DESC',
                (user_id,),
            ).fetchall()
        elif type_ == '其他':
            rows = conn.execute(
                """SELECT * FROM active_tickets WHERE user_id = ? AND type NOT IN ('车票','演出票','景区票','证书')
                   ORDER BY time DESC""",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM active_tickets WHERE user_id = ? AND type = ? ORDER BY time DESC',
                (user_id, type_),
            ).fetchall()
        return [dict(r) for r in rows]


def get_tickets_by_time(user_id):
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM active_tickets WHERE user_id = ? ORDER BY time ASC',
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def search_tickets(keyword, user_id, type_='全部'):
    """
    关键词搜索（可选：按类型过滤）。
    type_ 支持：全部 / 车票 / 演出票 / 景区票 / 证书 / 其他
    """
    if not keyword or not keyword.strip():
        return get_tickets_by_type(type_, user_id)

    kw = f'%{keyword.strip()}%'
    sql = """
        SELECT * FROM active_tickets
        WHERE user_id = ?
    """
    params = [user_id]

    if type_ == '其他':
        sql += " AND type NOT IN ('车票','演出票','景区票','证书')"
    elif type_ and type_ != '全部':
        sql += " AND type = ?"
        params.append(type_)

    sql += """
        AND (
            type LIKE ? OR
            platform LIKE ? OR
            time LIKE ? OR
            place LIKE ? OR
            notes LIKE ? OR
            IFNULL(ocr_text,'') LIKE ?
        )
        ORDER BY time DESC
    """
    params.extend([kw, kw, kw, kw, kw, kw])

    with get_db() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]


def update_ticket(ticket_id, user_id, type_, platform, time_, place, notes, image_path=None, ocr_text='', theme_color='', province='', city=''):
    province, city = normalize_location(province, city)
    with get_db() as conn:
        row = conn.execute(
            'SELECT 1 FROM active_tickets WHERE id = ? AND user_id = ?',
            (ticket_id, user_id),
        ).fetchone()
        if not row:
            return False
        if image_path is not None:
            conn.execute(
                '''UPDATE tickets SET type=?, platform=?, time=?, place=?, notes=?, image_path=?,
                   ocr_text=?, theme_color=?, province=?, city=? WHERE id=? AND user_id=?''',
                (
                    type_, platform or '', time_, place or '', notes or '', image_path,
                    ocr_text or '', theme_color or '', province or '', city or '', ticket_id, user_id,
                ),
            )
        else:
            conn.execute(
                '''UPDATE tickets SET type=?, platform=?, time=?, place=?, notes=?,
                   ocr_text=?, theme_color=?, province=?, city=? WHERE id=? AND user_id=?''',
                (
                    type_, platform or '', time_, place or '', notes or '',
                    ocr_text or '', theme_color or '', province or '', city or '', ticket_id, user_id,
                ),
            )
        return True


def update_ticket_notes(ticket_id: int, user_id: int, notes: str) -> bool:
    with get_db() as conn:
        row = conn.execute(
            'SELECT 1 FROM active_tickets WHERE id = ? AND user_id = ?',
            (ticket_id, user_id),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            'UPDATE tickets SET notes = ? WHERE id = ? AND user_id = ?',
            (notes, ticket_id, user_id),
        )
        return True


def delete_ticket(ticket_id, user_id):
    with get_db() as conn:
        cur = conn.execute("UPDATE tickets SET deleted_at = datetime('now') WHERE id = ? AND user_id = ? AND deleted_at IS NULL", (ticket_id, user_id))
        return cur.rowcount > 0


# ---------- 语义索引 ----------

def get_semantic_source_tickets(user_id: int):
    """返回当前用户可参与语义检索的有效票据。"""
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT id, user_id, type, platform, time, place, province, city,
                      notes, ocr_text, image_path, thumbnail_path, image_hash, theme_color
               FROM active_tickets
               WHERE user_id = ?
               ORDER BY time DESC, id DESC''',
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_ticket_embedding_records(user_id: int):
    """按 ticket_id 返回用户已有的向量索引记录。"""
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM ticket_embeddings WHERE user_id = ?',
            (user_id,),
        ).fetchall()
    result = {}
    for row in rows:
        item = dict(row)
        try:
            item['embedding'] = json.loads(item.pop('embedding_json'))
        except (TypeError, ValueError, json.JSONDecodeError):
            item['embedding'] = []
        result[item['ticket_id']] = item
    return result


def upsert_ticket_embedding(user_id: int, ticket_id: int, source_hash: str,
                            image_hash: str, content_text: str, visual_text: str,
                            embedding, model: str):
    """原子写入单张票券的语义索引，并再次校验票券归属。"""
    payload = json.dumps([float(value) for value in embedding], separators=(',', ':'))
    with get_db() as conn:
        owned = conn.execute(
            'SELECT 1 FROM active_tickets WHERE id = ? AND user_id = ?',
            (ticket_id, user_id),
        ).fetchone()
        if not owned:
            return False
        conn.execute(
            '''INSERT INTO ticket_embeddings
               (ticket_id, user_id, source_hash, image_hash, content_text, visual_text,
                embedding_json, dimensions, model, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(ticket_id) DO UPDATE SET
                   user_id=excluded.user_id,
                   source_hash=excluded.source_hash,
                   image_hash=excluded.image_hash,
                   content_text=excluded.content_text,
                   visual_text=excluded.visual_text,
                   embedding_json=excluded.embedding_json,
                   dimensions=excluded.dimensions,
                   model=excluded.model,
                   updated_at=CURRENT_TIMESTAMP''',
            (
                ticket_id, user_id, source_hash, image_hash or '', content_text,
                visual_text or '', payload, len(embedding), model,
            ),
        )
        return True


def remove_ticket_embedding(ticket_id: int, user_id: int):
    with get_db() as conn:
        conn.execute(
            'DELETE FROM ticket_embeddings WHERE ticket_id = ? AND user_id = ?',
            (ticket_id, user_id),
        )


def remove_orphaned_embeddings(user_id: int):
    """清理已彻底删除或不再属于该用户的索引，不影响回收站数据。"""
    with get_db() as conn:
        cur = conn.execute(
            '''DELETE FROM ticket_embeddings
               WHERE user_id = ? AND ticket_id NOT IN (
                   SELECT id FROM tickets WHERE user_id = ?
               )''',
            (user_id, user_id),
        )
        return cur.rowcount


def user_owns_image_path(user_id: int, image_path: str) -> bool:
    """用于访问旧版平铺路径图片时的权限校验"""
    if not image_path:
        return False
    with get_db() as conn:
        row = conn.execute(
            'SELECT 1 FROM active_tickets WHERE user_id = ? AND image_path = ? LIMIT 1',
            (user_id, image_path),
        ).fetchone()
        return row is not None


def get_home_mini_stats(user_id: int):
    """
    首页迷你统计（按入库时间 created_at 统计）：
    - total_count: 票据总数
    - year_count: 本年入库票据数
    - latest_date: 最近入库日期（created_at 最大值）
    """
    with get_db() as conn:
        total_count = conn.execute(
            'SELECT COUNT(*) FROM active_tickets WHERE user_id = ?',
            (user_id,),
        ).fetchone()[0]

        year_count = conn.execute(
            """SELECT COUNT(*) FROM active_tickets
               WHERE user_id = ?
                 AND strftime('%Y', created_at, 'localtime') = strftime('%Y','now','localtime')""",
            (user_id,),
        ).fetchone()[0]

        latest_row = conn.execute(
            "SELECT created_at FROM active_tickets WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()

        latest_date = latest_row['created_at'] if latest_row and latest_row['created_at'] else ''
        return {
            'total_count': int(total_count or 0),
            'year_count': int(year_count or 0),
            'latest_date': latest_date,
        }


# ---------- 地图与足迹统计 ----------

def get_city_stats(user_id: int):
    """Aggregate locations by province + city; province-only records remain visible."""
    with get_db() as conn:
        cities = [dict(row) for row in conn.execute(
            "SELECT province, city, MAX(time) AS time, COUNT(*) AS count FROM active_tickets WHERE user_id=? AND city != '' GROUP BY province, city ORDER BY count DESC", (user_id,))]
        provinces = [dict(row) for row in conn.execute(
            "SELECT province, COUNT(*) AS ticket_count FROM active_tickets WHERE user_id=? AND province != '' GROUP BY province ORDER BY ticket_count DESC", (user_id,))]
        total = conn.execute("SELECT COUNT(*) FROM active_tickets WHERE user_id=? AND (province != '' OR city != '')", (user_id,)).fetchone()[0]
    for province in provinces:
        province['cities'] = [row['city'] for row in cities if row['province'] == province['province']]
        province['city_count'] = len(province['cities'])
    return {'provinces': provinces, 'cities': cities, 'total_cities': len(cities),
            'total_provinces': len(provinces), 'total_tickets': total}


def get_yearly_stats(user_id: int, year=None):
    """
    获取按票据日期统计的年度报告：
    - yearly_counts: 每年票据数量
    - type_counts: 各类型数量
    - monthly_counts: 所选年份每月票据数量
    - top_places: 常去地点 Top 10
    - total_tickets / total_cities / type_counts / top_places: 所选年份的数据
    - cities_current_year: 所选年度去过的城市数
    - cities_last_year: 上一年度去过的城市数
    - years_current / years_last: 截至所选年 / 其上一年有票据的年份数
    - available_years: 有有效日期的年份及今年（去重，倒序）
    年度趋势保留全部有效年份；无效日期的旧数据不参与年度统计。
    """
    current_year = str(datetime.date.today().year)
    selected_year = current_year if year is None else str(year)
    if not re.fullmatch(r'[0-9]{4}', selected_year) or int(selected_year) == 0:
        raise ValueError('年份必须是 0001 至 9999 之间的四位数字')
    previous_year = f'{int(selected_year) - 1:04d}'
    with get_db() as conn:
        yearly_rows = conn.execute(
            '''SELECT strftime('%Y', time) as year, COUNT(*) as count
               FROM active_tickets WHERE user_id = ? AND strftime('%Y', time) IS NOT NULL
               AND strftime('%Y', time) != '0000'
               GROUP BY year ORDER BY year DESC''',
            (user_id,),
        ).fetchall()

        type_rows = conn.execute(
            '''SELECT type, COUNT(*) as count
               FROM active_tickets WHERE user_id = ? AND strftime('%Y', time) = ?
               GROUP BY type ORDER BY count DESC''',
            (user_id, selected_year),
        ).fetchall()

        monthly_rows = conn.execute(
            '''SELECT strftime('%m', time) as month, COUNT(*) as count
               FROM active_tickets
               WHERE user_id = ? AND strftime('%Y', time) = ?
               GROUP BY month ORDER BY month''',
            (user_id, selected_year),
        ).fetchall()

        place_rows = conn.execute(
            '''SELECT place, COUNT(*) as count
               FROM active_tickets
               WHERE user_id = ? AND place IS NOT NULL AND place != ''
               AND strftime('%Y', time) = ?
               GROUP BY place ORDER BY count DESC LIMIT 10''',
            (user_id, selected_year),
        ).fetchall()

        total = conn.execute(
            "SELECT COUNT(*) FROM active_tickets WHERE user_id = ? AND strftime('%Y', time) = ?",
            (user_id, selected_year),
        ).fetchone()[0]

        # 所选年份去过的城市总数（按 city 字段去重）
        total_cities_row = conn.execute(
            '''SELECT COUNT(DISTINCT IFNULL(province, '') || char(0) || city) FROM active_tickets
               WHERE user_id = ? AND city IS NOT NULL AND city != ''
               AND strftime('%Y', time) = ?''',
            (user_id, selected_year),
        ).fetchone()
        total_cities = int(total_cities_row[0] or 0)

        cities_current_year = total_cities

        # 上一年度去过的城市数
        cities_last_year_row = conn.execute(
            '''SELECT COUNT(DISTINCT IFNULL(province, '') || char(0) || city) FROM active_tickets
               WHERE user_id = ? AND city IS NOT NULL AND city != ''
               AND strftime('%Y', time) = ?''',
            (user_id, previous_year),
        ).fetchone()
        cities_last_year = int(cities_last_year_row[0] or 0)

        # 截至所选年份，排除之后年份的票据
        years_current = sum(1 for r in yearly_rows if r['year'] <= selected_year)

        # 截至所选年份的上一年
        years_last = sum(1 for r in yearly_rows if r['year'] <= previous_year)

        # 即使今年暂无票据，也可以从历史年份切回今年
        available_years = sorted({r['year'] for r in yearly_rows} | {current_year}, reverse=True)

        return {
            'total_tickets': int(total or 0),
            'yearly_counts': [{'year': r['year'], 'count': r['count']} for r in yearly_rows],
            'type_counts': [{'type': r['type'], 'count': r['count']} for r in type_rows],
            'monthly_counts': [{'month': r['month'], 'count': r['count']} for r in monthly_rows],
            'current_year': current_year,
            'selected_year': selected_year,
            'top_places': [{'place': r['place'], 'count': r['count']} for r in place_rows],
            'total_cities': total_cities,
            'cities_current_year': cities_current_year,
            'cities_last_year': cities_last_year,
            'years_current': years_current,
            'years_last': years_last,
            'available_years': available_years,
        }


def get_user_stats(user_id: int):
    """
    获取用户首页统计数据
    - total: 总票据数
    - yearly: 今年新增票据数
    - year_change: 较去年的变化
    - cities: 足迹城市数
    - latest_date: 最近收藏日期（与本年新增均按入库时间统计）
    """
    with get_db() as conn:
        # 总票据数
        total = conn.execute(
            'SELECT COUNT(*) FROM active_tickets WHERE user_id = ?',
            (user_id,),
        ).fetchone()[0] or 0

        # 当前年份
        current_year = conn.execute(
            "SELECT strftime('%Y','now','localtime')"
        ).fetchone()[0]

        # 今年新增
        this_year = conn.execute(
            '''SELECT COUNT(*) FROM active_tickets
               WHERE user_id = ? AND strftime('%Y', created_at, 'localtime') = ?''',
            (user_id, current_year),
        ).fetchone()[0] or 0

        # 去年新增
        last_year = conn.execute(
            '''SELECT COUNT(*) FROM active_tickets
               WHERE user_id = ? AND strftime('%Y', created_at, 'localtime') = ?''',
            (user_id, str(int(current_year) - 1)),
        ).fetchone()[0] or 0

        # 计算较去年的变化
        if last_year > 0:
            change = this_year - last_year
            if change > 0:
                year_change = f"较去年 +{change}"
            elif change < 0:
                year_change = f"较去年 {change}"
            else:
                year_change = "与去年持平"
        else:
            year_change = "较去年 --"

        # 足迹城市数
        cities = conn.execute(
            '''SELECT COUNT(DISTINCT IFNULL(province, '') || char(0) || city) FROM active_tickets
               WHERE user_id = ? AND city IS NOT NULL AND city != '' ''',
            (user_id,),
        ).fetchone()[0] or 0

        # 最近收藏时间，与首页迷你统计保持相同口径
        latest = conn.execute(
            '''SELECT date(created_at, 'localtime') AS latest_date FROM active_tickets
               WHERE user_id = ? AND created_at IS NOT NULL
               ORDER BY created_at DESC, id DESC LIMIT 1''',
            (user_id,),
        ).fetchone()

        latest_date = latest['latest_date'] if latest else None

        return {
            'total': int(total),
            'yearly': int(this_year),
            'year_change': year_change,
            'cities': int(cities),
            'latest_date': latest_date,
        }


def get_map_tickets(user_id: int):
    """
    获取用于地图展示的票据数据：
    - 包含地点信息的所有票据
    - 按城市聚合数量
    """
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT t.id, t.type, t.time, t.place, t.province, t.city,
                      t.theme_color, t.image_path, t.notes,
                      COUNT(*) OVER (PARTITION BY t.province, t.city) as city_count
               FROM active_tickets t
               WHERE t.user_id = ? AND (t.city IS NOT NULL AND t.city != '')
               ORDER BY t.time DESC''',
            (user_id,),
        ).fetchall()

        return [dict(row) for row in rows]


def get_featured_tickets(user_id: int, limit: int = 5):
    """
    获取精选票据（最近入库的带图片票据）
    """
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT t.id, t.type, t.time, t.place, t.image_path, t.theme_color
               FROM active_tickets t
               WHERE t.user_id = ? AND t.image_path IS NOT NULL AND t.image_path != ''
               ORDER BY t.created_at DESC
               LIMIT ?''',
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def get_top_places(user_id: int, limit: int = 12):
    """
    获取热门地点（用于首页标签云）
    """
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT place, COUNT(*) as count
               FROM active_tickets
               WHERE user_id = ? AND place IS NOT NULL AND place != ''
               GROUP BY place
               ORDER BY count DESC
               LIMIT ?''',
            (user_id, limit),
        ).fetchall()
        return [{'place': r['place'], 'count': r['count']} for r in rows]


def get_featured_tickets(user_id: int, limit: int = 5):
    """
    获取精选票根：最近入库的 5 张票据
    """
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT id, type, time, place, theme_color, image_path
               FROM active_tickets
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT ?''',
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def get_popular_tags(user_id: int, limit: int = 12):
    """
    获取热门标签：按地点和类型聚合统计
    """
    with get_db() as conn:
        type_tags = conn.execute(
            '''SELECT type as tag, COUNT(*) as count
               FROM active_tickets WHERE user_id = ?
               GROUP BY type
               ORDER BY count DESC LIMIT ?''',
            (user_id, limit),
        ).fetchall()

        place_tags = conn.execute(
            '''SELECT place as tag, COUNT(*) as count
               FROM active_tickets
               WHERE user_id = ? AND place IS NOT NULL AND place != ''
               GROUP BY place
               ORDER BY count DESC LIMIT ?''',
            (user_id, limit),
        ).fetchall()

        tags = []
        seen = set()
        for row in list(type_tags) + list(place_tags):
            if row['tag'] not in seen:
                tags.append({'tag': row['tag'], 'count': row['count']})
                seen.add(row['tag'])
                if len(tags) >= limit:
                    break

        return tags[:limit]


def get_memory_reminder_data(user_id: int, today=None):
    """
    获取记忆提醒数据：
    - days_since_first: 距离第一次收藏的天数
    - first_ticket: 第一张票根信息（用于预览卡片）
    - today_memory: 去年今天的记忆（如果有）
    """
    today = today or datetime.date.today()
    with get_db() as conn:
        # 获取第一张票据
        first_row = conn.execute(
            '''SELECT id, type, platform, time, place, province, city, notes, theme_color, image_path,
                      date(created_at, 'localtime') AS collected_date
               FROM active_tickets
               WHERE user_id = ?
               ORDER BY created_at ASC, id ASC
               LIMIT 1''',
            (user_id,),
        ).fetchone()

        # 获取去年今天同一天的票据
        # 按日历中的去年同月同日匹配；2 月 29 日在上一年不存在时不展示回忆。
        try:
            last_year_date = today.replace(year=today.year - 1).isoformat()
        except ValueError:
            last_year_date = None

        today_rows = conn.execute(
            '''SELECT id, type, platform, time, place, province, city, notes, theme_color, image_path
               FROM active_tickets
               WHERE user_id = ? AND date(time) = ?
               ORDER BY time DESC, id DESC
               LIMIT 1''',
            (user_id, last_year_date),
        ).fetchone()

        result = {
            'days_since_first': 0,
            'first_ticket': None,
            'today_memory': None,
        }

        if first_row:
            first_dict = dict(first_row)
            result['first_ticket'] = {
                'id': first_dict.get('id'),
                'type': first_dict.get('type'),
                'platform': first_dict.get('platform'),
                'time': first_dict.get('time'),
                'place': first_dict.get('place'),
                'province': first_dict.get('province'),
                'city': first_dict.get('city'),
                'notes': first_dict.get('notes'),
                'theme_color': first_dict.get('theme_color'),
                'image_path': first_dict.get('image_path'),
            }

            # 计算天数
            try:
                first_time_str = first_dict.get('collected_date', '')
                if first_time_str:
                    if ' ' in first_time_str:
                        first_date = datetime.datetime.strptime(first_time_str.split(' ')[0], '%Y-%m-%d').date()
                    else:
                        first_date = datetime.datetime.strptime(first_time_str, '%Y-%m-%d').date()
                    result['days_since_first'] = max(0, (today - first_date).days)
            except (ValueError, TypeError):
                pass

        if today_rows:
            today_dict = dict(today_rows)
            # 解析出发地和目的地（从 place 字段，如 "杭州东 → 上海虹桥"）
            place = today_dict.get('place', '')
            from_place = ''
            to_place = ''
            if '→' in place:
                parts = place.split('→')
                from_place = parts[0].strip()
                to_place = parts[1].strip() if len(parts) > 1 else ''

            result['today_memory'] = {
                'id': today_dict.get('id'),
                'type': today_dict.get('type'),
                'time': today_dict.get('time'),
                'place': place,
                'from': from_place,
                'to': to_place,
                'platform': today_dict.get('platform'),
                'theme_color': today_dict.get('theme_color'),
                'image_path': today_dict.get('image_path'),
            }

        return result
