"""Web regression tests. All records live in a temporary SQLite database."""
import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from app import app


class WebStatsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_patch = patch.object(database, 'DATABASE_PATH', str(Path(self.temp.name) / 'test.db'))
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        database.init_db()
        self.user = database.create_user('collector', 'test-password')
        self.other = database.create_user('other-user', 'test-password')
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['user_id'] = self.user
        self.year = datetime.date.today().year

    def ticket(self, date, *, owner=None, type_='车票', city='杭州', place='杭州东', created='2024-01-01 12:00:00'):
        tid = database.add_ticket(owner or self.user, type_, '', date, place, '', '', city=city)
        with database.get_db() as conn:
            conn.execute('UPDATE tickets SET created_at = ? WHERE id = ?', (created, tid))
        return tid

    def test_selected_year_filters_every_annual_metric_and_keeps_trend(self):
        self.ticket('2023-01-01', city='南京')
        self.ticket('2024-02-01')
        self.ticket('2024-02-20', type_='演出票')
        self.ticket('2024-12-31', type_='演出票', city='上海', place='剧院')
        self.ticket('2025-06-01', type_='证书', city='北京', place='学校')
        self.ticket('2024-01-01', owner=self.other, city='深圳', place='私有地点')
        response = self.client.get('/api/stats/yearly?year=2024')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()['data']
        self.assertEqual(data['selected_year'], '2024')
        self.assertEqual(data['total_tickets'], 3)
        self.assertEqual(data['total_cities'], 2)
        self.assertEqual(data['cities_last_year'], 1)
        self.assertEqual(data['years_current'], 2)
        self.assertEqual(data['years_last'], 1)
        self.assertEqual(data['monthly_counts'], [{'month': '02', 'count': 2}, {'month': '12', 'count': 1}])
        self.assertEqual({x['type']: x['count'] for x in data['type_counts']}, {'车票': 1, '演出票': 2})
        self.assertEqual({x['place']: x['count'] for x in data['top_places']}, {'杭州东': 2, '剧院': 1})
        self.assertEqual({x['year']: x['count'] for x in data['yearly_counts']}, {'2023': 1, '2024': 3, '2025': 1})

    def test_default_year_and_empty_year(self):
        self.ticket(f'{self.year - 1}-01-01')
        data = self.client.get('/api/stats/yearly').get_json()['data']
        self.assertEqual(data['selected_year'], str(self.year))
        self.assertIn(str(self.year), data['available_years'])
        self.assertEqual(data['total_tickets'], 0)
        self.assertEqual(data['total_cities'], 0)
        self.assertEqual(data['monthly_counts'], [])
        self.assertEqual(data['type_counts'], [])
        self.assertEqual(data['top_places'], [])

    def test_invalid_year_is_a_client_error(self):
        for value in ['', 'all', '2024.0', '24', '0000', '10000', "2024' OR 1=1"]:
            with self.subTest(value=value):
                response = self.client.get('/api/stats/yearly', query_string={'year': value})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.get_json()['success'])

    def test_legacy_invalid_date_does_not_break_stats_page(self):
        self.ticket('not-a-date')
        self.ticket('0000-01-01')
        data = database.get_yearly_stats(self.user)
        self.assertEqual(data['yearly_counts'], [])
        self.assertEqual(data['available_years'], [str(self.year)])
        response = self.client.get('/stats')
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'data-year="{self.year}"', response.get_data(as_text=True))

    def test_stats_api_requires_login(self):
        self.assertEqual(app.test_client().get('/api/stats/yearly?year=2024').status_code, 401)

    def test_home_new_count_uses_collection_date_not_ticket_date(self):
        self.ticket('1998-01-01', created=f'{self.year}-03-01 12:00:00')
        self.ticket('1999-01-01', created=f'{self.year}-04-01 12:00:00')
        self.ticket(f'{self.year}-01-01', created=f'{self.year - 1}-01-01 12:00:00')
        self.ticket('1997-01-01', owner=self.other, created=f'{self.year}-05-01 12:00:00')
        data = self.client.get('/api/stats/overview').get_json()['data']
        mini = self.client.get('/api/stats/mini').get_json()['data']
        self.assertEqual(data['total'], 3)
        self.assertEqual(data['yearly'], 2)
        self.assertEqual(data['yearly'], mini['year_count'])
        self.assertEqual(data['year_change'], '较去年 +1')
        self.assertEqual(data['latest_date'], f'{self.year}-04-01')

    def test_last_year_today_excludes_other_years_and_other_users(self):
        expected = self.ticket('2025-09-27 18:00:00')
        self.ticket('2024-09-27')
        self.ticket('2026-09-27')
        self.ticket('2027-09-27')
        self.ticket('2025-09-27 20:00:00', owner=self.other)
        data = database.get_memory_reminder_data(self.user, datetime.date(2026, 9, 27))
        self.assertEqual(data['today_memory']['id'], expected)

    def test_last_year_today_uses_calendar_year_across_leap_year(self):
        expected = self.ticket('2023-03-01')
        self.ticket('2023-03-02')
        data = database.get_memory_reminder_data(self.user, datetime.date(2024, 3, 1))
        self.assertEqual(data['today_memory']['id'], expected)

    def test_february_29_has_no_false_anniversary(self):
        self.ticket('2023-02-28')
        self.ticket('2023-03-01')
        data = database.get_memory_reminder_data(self.user, datetime.date(2024, 2, 29))
        self.assertIsNone(data['today_memory'])

    def test_collection_age_uses_first_upload_and_never_goes_negative(self):
        first = self.ticket('1990-01-01', created='2024-02-28 12:00:00')
        self.ticket('1980-01-01', created='2024-03-01 12:00:00')
        data = database.get_memory_reminder_data(self.user, datetime.date(2024, 3, 1))
        self.assertEqual(data['first_ticket']['id'], first)
        self.assertEqual(data['days_since_first'], 2)
        self.assertEqual(database.get_memory_reminder_data(self.user, datetime.date(2024, 1, 1))['days_since_first'], 0)

    def test_empty_memory(self):
        data = self.client.get('/api/memory/reminder').get_json()['data']
        self.assertIsNone(data['first_ticket'])
        self.assertIsNone(data['today_memory'])
        self.assertEqual(data['days_since_first'], 0)


if __name__ == '__main__':
    unittest.main()
