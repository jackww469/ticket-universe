# -*- coding: utf-8 -*-
"""数据库操作封装：用户 + 票据（按 user_id 隔离）"""
import sqlite3
from contextlib import contextmanager
from werkzeug.security import generate_password_hash, check_password_hash

from config import DATABASE_PATH


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
            'SELECT * FROM tickets WHERE id = ? AND user_id = ?',
            (ticket_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def get_tickets_by_type(type_, user_id):
    with get_db() as conn:
        if type_ == '全部' or not type_:
            rows = conn.execute(
                'SELECT * FROM tickets WHERE user_id = ? ORDER BY time DESC',
                (user_id,),
            ).fetchall()
        elif type_ == '其他':
            rows = conn.execute(
                """SELECT * FROM tickets WHERE user_id = ? AND type NOT IN ('车票','演出票','景区票','证书')
                   ORDER BY time DESC""",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM tickets WHERE user_id = ? AND type = ? ORDER BY time DESC',
                (user_id, type_),
            ).fetchall()
        return [dict(r) for r in rows]


def get_tickets_by_time(user_id):
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM tickets WHERE user_id = ? ORDER BY time ASC',
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
        SELECT * FROM tickets
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
    with get_db() as conn:
        row = conn.execute(
            'SELECT 1 FROM tickets WHERE id = ? AND user_id = ?',
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
            'SELECT 1 FROM tickets WHERE id = ? AND user_id = ?',
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
        row = conn.execute(
            'SELECT image_path FROM tickets WHERE id = ? AND user_id = ?',
            (ticket_id, user_id),
        ).fetchone()
        if not row:
            return None
        conn.execute('DELETE FROM tickets WHERE id = ? AND user_id = ?', (ticket_id, user_id))
        return dict(row)['image_path'] if row['image_path'] else None


def user_owns_image_path(user_id: int, image_path: str) -> bool:
    """用于访问旧版平铺路径图片时的权限校验"""
    if not image_path:
        return False
    with get_db() as conn:
        row = conn.execute(
            'SELECT 1 FROM tickets WHERE user_id = ? AND image_path = ? LIMIT 1',
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
            'SELECT COUNT(*) FROM tickets WHERE user_id = ?',
            (user_id,),
        ).fetchone()[0]

        year_count = conn.execute(
            """SELECT COUNT(*) FROM tickets
               WHERE user_id = ?
                 AND strftime('%Y', created_at, 'localtime') = strftime('%Y','now','localtime')""",
            (user_id,),
        ).fetchone()[0]

        latest_row = conn.execute(
            "SELECT created_at FROM tickets WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
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
    """
    获取足迹城市统计：
    - provinces: 各省份统计（含城市列表）
    - cities: 所有城市列表（去重）
    - total_cities: 去过城市总数
    - total_provinces: 去过省份总数
    """
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT province, city, place, type, time, COUNT(*) as count
               FROM tickets
               WHERE user_id = ? AND (city IS NOT NULL AND city != '')
               GROUP BY city
               ORDER BY count DESC''',
            (user_id,),
        ).fetchall()

        provinces_dict = {}
        cities_list = []

        for row in rows:
            prov = (row['province'] or '').strip()
            city = (row['city'] or '').strip()
            if city:
                cities_list.append({
                    'province': prov,
                    'city': city,
                    'place': row['place'] or '',
                    'type': row['type'] or '',
                    'time': row['time'] or '',
                    'count': row['count'],
                })
                if prov:
                    if prov not in provinces_dict:
                        provinces_dict[prov] = {'count': 0, 'cities': []}
                    provinces_dict[prov]['count'] += row['count']
                    if city not in provinces_dict[prov]['cities']:
                        provinces_dict[prov]['cities'].append(city)

        provinces_list = [
            {'province': p, 'city_count': len(v['cities']), 'ticket_count': v['count'], 'cities': v['cities']}
            for p, v in provinces_dict.items()
        ]
        provinces_list.sort(key=lambda x: x['ticket_count'], reverse=True)

        return {
            'provinces': provinces_list,
            'cities': cities_list,
            'total_cities': len(cities_list),
            'total_provinces': len(provinces_list),
        }


def get_yearly_stats(user_id: int):
    """
    获取年度统计：
    - yearly_counts: 每年票据数量
    - type_counts: 各类型数量
    - monthly_counts: 今年每月票据数量
    - top_places: 常去地点 Top 10
    - total_tickets: 总票据数
    """
    with get_db() as conn:
        yearly_rows = conn.execute(
            '''SELECT strftime('%Y', time) as year, COUNT(*) as count
               FROM tickets WHERE user_id = ? AND time IS NOT NULL
               GROUP BY year ORDER BY year DESC''',
            (user_id,),
        ).fetchall()

        type_rows = conn.execute(
            '''SELECT type, COUNT(*) as count
               FROM tickets WHERE user_id = ?
               GROUP BY type ORDER BY count DESC''',
            (user_id,),
        ).fetchall()

        current_year = conn.execute(
            "SELECT strftime('%Y','now','localtime')"
        ).fetchone()[0]

        monthly_rows = conn.execute(
            '''SELECT strftime('%m', time) as month, COUNT(*) as count
               FROM tickets
               WHERE user_id = ? AND strftime('%Y', time) = ?
               GROUP BY month ORDER BY month''',
            (user_id, current_year),
        ).fetchall()

        place_rows = conn.execute(
            '''SELECT place, COUNT(*) as count
               FROM tickets
               WHERE user_id = ? AND place IS NOT NULL AND place != ''
               GROUP BY place ORDER BY count DESC LIMIT 10''',
            (user_id,),
        ).fetchall()

        total = conn.execute(
            'SELECT COUNT(*) FROM tickets WHERE user_id = ?',
            (user_id,),
        ).fetchone()[0]

        return {
            'total_tickets': int(total or 0),
            'yearly_counts': [{'year': r['year'], 'count': r['count']} for r in yearly_rows],
            'type_counts': [{'type': r['type'], 'count': r['count']} for r in type_rows],
            'monthly_counts': [{'month': r['month'], 'count': r['count']} for r in monthly_rows],
            'current_year': current_year,
            'top_places': [{'place': r['place'], 'count': r['count']} for r in place_rows],
        }


def get_user_stats(user_id: int):
    """
    获取用户首页统计数据
    - total: 总票据数
    - yearly: 今年新增票据数
    - year_change: 较去年的变化
    - cities: 足迹城市数
    - latest_date: 最近更新日期
    """
    with get_db() as conn:
        # 总票据数
        total = conn.execute(
            'SELECT COUNT(*) FROM tickets WHERE user_id = ?',
            (user_id,),
        ).fetchone()[0] or 0

        # 当前年份
        current_year = conn.execute(
            "SELECT strftime('%Y','now','localtime')"
        ).fetchone()[0]

        # 今年新增
        this_year = conn.execute(
            '''SELECT COUNT(*) FROM tickets
               WHERE user_id = ? AND strftime('%Y', time) = ?''',
            (user_id, current_year),
        ).fetchone()[0] or 0

        # 去年新增
        last_year = conn.execute(
            '''SELECT COUNT(*) FROM tickets
               WHERE user_id = ? AND strftime('%Y', time) = ?''',
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
            '''SELECT COUNT(DISTINCT city) FROM tickets
               WHERE user_id = ? AND city IS NOT NULL AND city != '' ''',
            (user_id,),
        ).fetchone()[0] or 0

        # 最近更新时间
        latest = conn.execute(
            '''SELECT time FROM tickets
               WHERE user_id = ? AND time IS NOT NULL
               ORDER BY time DESC LIMIT 1''',
            (user_id,),
        ).fetchone()

        latest_date = latest['time'] if latest else None

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
                      COUNT(*) OVER (PARTITION BY t.city) as city_count
               FROM tickets t
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
               FROM tickets t
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
               FROM tickets
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
               FROM tickets
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
               FROM tickets WHERE user_id = ?
               GROUP BY type
               ORDER BY count DESC LIMIT ?''',
            (user_id, limit),
        ).fetchall()

        place_tags = conn.execute(
            '''SELECT place as tag, COUNT(*) as count
               FROM tickets
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


def get_memory_reminder_data(user_id: int):
    """
    获取记忆提醒数据：
    - days_since_first: 距离第一次收藏的天数
    - first_ticket: 第一张票根信息（用于预览卡片）
    - today_memory: 去年今天的记忆（如果有）
    """
    import datetime

    with get_db() as conn:
        # 获取第一张票据
        first_row = conn.execute(
            '''SELECT id, type, platform, time, place, province, city, notes, theme_color, image_path
               FROM tickets
               WHERE user_id = ?
               ORDER BY created_at ASC
               LIMIT 1''',
            (user_id,),
        ).fetchone()

        # 获取去年今天同一天的票据
        today = datetime.date.today()
        last_year_date = (today - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
        today_str = today.strftime('%m-%d')

        today_rows = conn.execute(
            '''SELECT id, type, platform, time, place, province, city, notes, theme_color, image_path
               FROM tickets
               WHERE user_id = ? AND time LIKE ? AND time != ?
               ORDER BY time DESC
               LIMIT 1''',
            (user_id, f'%{today_str}', last_year_date),
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
                first_time_str = first_dict.get('time', '')
                if first_time_str:
                    if ' ' in first_time_str:
                        first_date = datetime.datetime.strptime(first_time_str.split(' ')[0], '%Y-%m-%d').date()
                    else:
                        first_date = datetime.datetime.strptime(first_time_str, '%Y-%m-%d').date()
                    result['days_since_first'] = (today - first_date).days
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

