"""语义检索与个人记忆 RAG 的回归测试。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import config
import database
import semantic_service
from app import app


def fake_embeddings(texts):
    """稳定的小向量模型：让测试只验证检索流程，不访问外部服务。"""
    keywords = ('上海', '演出', '杭州', '车票', '星空')
    return [
        [float(text.count(keyword)) for keyword in keywords] + [1.0]
        for text in texts
    ]


class DashScopeAdapterTests(unittest.TestCase):
    def test_text_embedding_uses_dashscope_multimodal_endpoint(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            'output': {'embeddings': [
                {'index': 1, 'embedding': [0.0, 1.0], 'type': 'vl'},
                {'index': 0, 'embedding': [1.0, 0.0], 'type': 'vl'},
            ]},
        }
        with patch.object(config, 'DASHSCOPE_API_KEY', 'test-key'), \
                patch.object(config, 'DASHSCOPE_EMBEDDING_DIMENSIONS', 512), \
                patch.object(semantic_service.requests, 'post', return_value=response) as post:
            vectors = semantic_service.embed_texts(['第一张', '第二张'])

        self.assertEqual(vectors, [[1.0, 0.0], [0.0, 1.0]])
        _, kwargs = post.call_args
        self.assertEqual(kwargs['json']['model'], 'qwen3-vl-embedding')
        self.assertEqual(
            kwargs['json']['input']['contents'],
            [{'text': '第一张'}, {'text': '第二张'}],
        )
        self.assertEqual(kwargs['json']['parameters']['dimension'], 512)
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer test-key')

    def test_multimodal_embedding_enables_text_image_fusion(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            'output': {'embeddings': [
                {'index': 0, 'embedding': [0.25, 0.75], 'type': 'fusion'},
            ]},
        }
        image = 'data:image/png;base64,ZmFrZQ=='
        with patch.object(config, 'DASHSCOPE_API_KEY', 'test-key'), \
                patch.object(semantic_service.requests, 'post', return_value=response) as post:
            vector = semantic_service.embed_multimodal('一张演出票', image)

        self.assertEqual(vector, [0.25, 0.75])
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['input']['contents'], [
            {'text': '一张演出票'},
            {'image': image},
        ])
        self.assertTrue(payload['parameters']['enable_fusion'])

    def test_qwen_json_answer_accepts_code_fence(self):
        content = '```json\n{"title":"记忆","answer":"回答","citations":[1],"follow_up_questions":[]}\n```'
        with patch.object(semantic_service, '_chat_completion', return_value=content):
            answer = semantic_service.generate_grounded_answer(
                '我去过哪里？',
                [{'id': 1, 'city': '杭州'}],
            )
        self.assertEqual(answer['citations'], [1])


class SemanticMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.uploads = self.root / 'uploads'
        self.uploads.mkdir()

        db_patch = patch.object(database, 'DATABASE_PATH', str(self.root / 'test.db'))
        db_patch.start()
        self.addCleanup(db_patch.stop)
        app_config = patch.dict(app.config, UPLOAD_FOLDER=str(self.uploads), TESTING=True)
        app_config.start()
        self.addCleanup(app_config.stop)
        key_patch = patch.object(config, 'DASHSCOPE_API_KEY', 'test-key')
        key_patch.start()
        self.addCleanup(key_patch.stop)
        dim_patch = patch.object(config, 'DASHSCOPE_EMBEDDING_DIMENSIONS', 6)
        dim_patch.start()
        self.addCleanup(dim_patch.stop)
        embed_patch = patch.object(semantic_service, 'embed_texts', side_effect=fake_embeddings)
        embed_patch.start()
        self.addCleanup(embed_patch.stop)

        database.init_db()
        self.user = database.create_user('memory-owner', 'testing-password')
        self.other = database.create_user('memory-other', 'testing-password')
        self.shanghai = database.add_ticket(
            self.user, '演出票', '大麦', '2025-07-20', '上海大剧院',
            '夏天看的音乐剧', '', province='上海', city='上海',
        )
        self.hangzhou = database.add_ticket(
            self.user, '车票', '12306', '2024-01-02', '杭州东站',
            '回家过年', '', province='浙江', city='杭州',
        )
        self.private = database.add_ticket(
            self.other, '演出票', '私有平台', '2025-07-20', '上海秘密场馆',
            '不应被看到', '', province='上海', city='上海',
        )
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['user_id'] = self.user

    def test_memory_page_and_embedding_migration_are_available(self):
        self.assertEqual(self.client.get('/memory').status_code, 200)
        database.migrate_db()
        database.migrate_db()
        with database.get_db() as conn:
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ticket_embeddings'"
            ).fetchone()
        self.assertIsNotNone(table)

    def test_hybrid_search_ranks_relevant_ticket_and_isolates_users(self):
        result = semantic_service.search_user_tickets(
            self.user, '上海的演出', str(self.uploads), limit=10,
        )
        self.assertEqual(result['mode'], 'hybrid')
        self.assertEqual(result['data'][0]['id'], self.shanghai)
        self.assertNotIn(self.private, [ticket['id'] for ticket in result['data']])
        with database.get_db() as conn:
            owners = {row['user_id'] for row in conn.execute('SELECT user_id FROM ticket_embeddings')}
        self.assertEqual(owners, {self.user})

    def test_changed_ticket_invalidates_and_rebuilds_embedding(self):
        semantic_service.refresh_user_index(self.user, str(self.uploads))
        before = database.get_ticket_embedding_records(self.user)[self.hangzhou]['source_hash']
        self.assertTrue(database.update_ticket_notes(self.hangzhou, self.user, '星空主题车票'))
        result = semantic_service.search_user_tickets(
            self.user, '星空', str(self.uploads), limit=10,
        )
        after = database.get_ticket_embedding_records(self.user)[self.hangzhou]['source_hash']
        self.assertNotEqual(before, after)
        self.assertEqual(result['data'][0]['id'], self.hangzhou)

    def test_explicit_reindex_fuses_local_image_with_ticket_text(self):
        image_dir = self.uploads / str(self.user)
        image_dir.mkdir()
        image_file = image_dir / 'ticket.png'
        image_file.write_bytes(b'fake-png-for-request-payload')
        ticket_id = database.add_ticket(
            self.user, '景区票', '现场窗口', '2025-08-01', '西湖',
            '湖边风景', f'static/uploads/{self.user}/ticket.png',
            province='浙江', city='杭州',
        )
        with patch.object(
            semantic_service,
            'embed_multimodal',
            return_value=[1.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        ) as fusion:
            result = semantic_service.refresh_user_index(
                self.user,
                str(self.uploads),
                force=True,
                include_visual=True,
            )

        self.assertEqual(result['indexed'], 3)
        text, image_data_url = fusion.call_args.args
        self.assertIn('西湖', text)
        self.assertTrue(image_data_url.startswith('data:image/png;base64,'))
        record = database.get_ticket_embedding_records(self.user)[ticket_id]
        self.assertIn('百炼多模态模型', record['visual_text'])

    def test_missing_api_key_degrades_to_keyword_search(self):
        with patch.object(config, 'DASHSCOPE_API_KEY', ''):
            result = semantic_service.search_user_tickets(
                self.user, '杭州', str(self.uploads), limit=10,
            )
        self.assertEqual(result['mode'], 'keyword')
        self.assertEqual(result['data'][0]['id'], self.hangzhou)

    def test_embedding_outage_degrades_without_breaking_search(self):
        with patch.object(
            semantic_service,
            'embed_texts',
            side_effect=semantic_service.SemanticServiceError('simulated outage'),
        ):
            result = semantic_service.search_user_tickets(
                self.user, '杭州', str(self.uploads), limit=10,
            )
        self.assertEqual(result['mode'], 'keyword')
        self.assertEqual(result['data'][0]['id'], self.hangzhou)
        self.assertIn('自动切换', result['warning'])

    def test_rag_citations_are_restricted_to_retrieved_user_tickets(self):
        generated = {
            'title': '上海记忆',
            'answer': '你在上海看过一场演出。',
            'citations': [self.shanghai, self.private, 999999, 'bad'],
            'follow_up_questions': ['还去过哪里？'],
        }
        with patch.object(semantic_service, 'generate_grounded_answer', return_value=generated):
            response = self.client.post('/api/memory/query', json={'query': '上海的演出'})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['answer']['citations'], [self.shanghai])
        self.assertNotIn(self.private, [ticket['id'] for ticket in data['results']])

    def test_generation_outage_returns_local_grounded_summary(self):
        with patch.object(
            semantic_service,
            'generate_grounded_answer',
            side_effect=semantic_service.SemanticServiceError('simulated outage'),
        ):
            response = self.client.post('/api/memory/query', json={'query': '上海的演出'})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['mode'], 'local')
        self.assertIn(self.shanghai, data['answer']['citations'])
        self.assertNotIn(self.private, data['answer']['citations'])
        self.assertIn('本地可解释摘要', data['warning'])

    def test_query_validation_and_login_protection(self):
        self.assertEqual(
            self.client.post('/api/memory/query', json={'query': 'x' * 301}).status_code,
            400,
        )
        anonymous = app.test_client()
        self.assertEqual(anonymous.post('/api/memory/query', json={'query': '上海'}).status_code, 401)
        self.assertEqual(anonymous.get('/api/semantic/search?q=上海').status_code, 401)


if __name__ == '__main__':
    unittest.main()
