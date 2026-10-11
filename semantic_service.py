# -*- coding: utf-8 -*-
"""图文语义索引、混合检索与带引用的个人记忆 RAG。"""
import base64
import hashlib
import json
import math
import mimetypes
import re
from pathlib import Path

import requests

import config
from database import (
    get_semantic_source_tickets,
    get_ticket_embedding_records,
    remove_orphaned_embeddings,
    upsert_ticket_embedding,
)
from media_service import local_image


MAX_QUERY_LENGTH = 300
MAX_CONTEXT_TICKETS = 8
MAX_FIELD_CHARS = 900


class SemanticServiceError(RuntimeError):
    """可安全转换为降级提示的外部语义服务异常。"""


def semantic_enabled():
    return bool(config.DASHSCOPE_API_KEY)


def _dashscope_post(url, payload):
    if not semantic_enabled():
        raise SemanticServiceError('未配置 DASHSCOPE_API_KEY')
    try:
        response = requests.post(
            url,
            headers={
                'Authorization': f'Bearer {config.DASHSCOPE_API_KEY}',
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=config.DASHSCOPE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise SemanticServiceError('阿里云百炼服务暂时不可用') from exc


def _chat_completion(messages, *, max_tokens=700):
    payload = _dashscope_post(
        config.DASHSCOPE_COMPATIBLE_API_BASE + '/chat/completions',
        {
            'model': config.DASHSCOPE_RAG_MODEL,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': 0.2,
        },
    )
    choices = payload.get('choices') or []
    if not choices:
        raise SemanticServiceError('阿里云百炼返回内容不完整')
    content = (choices[0].get('message') or {}).get('content')
    if isinstance(content, str) and content.strip():
        return content.strip()
    raise SemanticServiceError('阿里云百炼返回内容不完整')


def _embedding_rows(payload):
    rows = (payload.get('output') or {}).get('embeddings') or []
    return sorted(rows, key=lambda item: item.get('index', 0))


def embed_texts(texts):
    """使用百炼多模态模型批量生成文本向量；顺序与输入保持一致。"""
    if not texts:
        return []
    payload = _dashscope_post(
        config.DASHSCOPE_MULTIMODAL_EMBEDDING_URL,
        {
            'model': config.DASHSCOPE_EMBEDDING_MODEL,
            'input': {'contents': [{'text': text} for text in texts]},
            'parameters': {'dimension': config.DASHSCOPE_EMBEDDING_DIMENSIONS},
        },
    )
    rows = _embedding_rows(payload)
    vectors = [item.get('embedding') or [] for item in rows]
    if len(vectors) != len(texts) or any(not vector for vector in vectors):
        raise SemanticServiceError('阿里云百炼向量服务返回数量不一致')
    return vectors


def embed_multimodal(text, image_data_url):
    """将票券文字和图片融合为一个可用于跨模态检索的向量。"""
    contents = [{'text': text}]
    if image_data_url:
        contents.append({'image': image_data_url})
    payload = _dashscope_post(
        config.DASHSCOPE_MULTIMODAL_EMBEDDING_URL,
        {
            'model': config.DASHSCOPE_EMBEDDING_MODEL,
            'input': {'contents': contents},
            'parameters': {
                'dimension': config.DASHSCOPE_EMBEDDING_DIMENSIONS,
                'enable_fusion': True,
            },
        },
    )
    rows = _embedding_rows(payload)
    vector = rows[0].get('embedding') if len(rows) == 1 else None
    if not vector:
        raise SemanticServiceError('阿里云百炼未返回图文融合向量')
    return vector


def _ticket_source_text(ticket):
    fields = [
        ('票据类型', ticket.get('type')),
        ('日期', ticket.get('time')),
        ('来源平台', ticket.get('platform')),
        ('地点', ticket.get('place')),
        ('省份', ticket.get('province')),
        ('城市', ticket.get('city')),
        ('用户备注', ticket.get('notes')),
        ('票面文字', ticket.get('ocr_text')),
    ]
    return '\n'.join(
        f'{label}：{str(value).strip()[:MAX_FIELD_CHARS]}'
        for label, value in fields if value and str(value).strip()
    )


def _source_hash(ticket):
    raw = '\n'.join([
        _ticket_source_text(ticket),
        '图片指纹：' + str(ticket.get('image_hash') or ''),
    ])
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _image_data_url(ticket, upload_folder):
    stored_path = ticket.get('thumbnail_path') or ticket.get('image_path')
    path = local_image(stored_path, upload_folder)
    if not path or not Path(path).is_file():
        return ''
    data = Path(path).read_bytes()
    if not data or len(data) > 6 * 1024 * 1024:
        return ''
    mime = mimetypes.guess_type(str(path))[0] or 'image/jpeg'
    return f'data:{mime};base64,' + base64.b64encode(data).decode('ascii')


def refresh_user_index(user_id, upload_folder, *, force=False, include_visual=False):
    """增量刷新用户索引；显式重建时由百炼直接融合票券文字和图片。"""
    tickets = get_semantic_source_tickets(user_id)
    existing = get_ticket_embedding_records(user_id)
    remove_orphaned_embeddings(user_id)
    pending = []
    warnings = []

    for ticket in tickets:
        record = existing.get(ticket['id'])
        source_hash = _source_hash(ticket)
        is_current = (
            record
            and record.get('source_hash') == source_hash
            and record.get('model') == config.DASHSCOPE_EMBEDDING_MODEL
            and record.get('dimensions') == config.DASHSCOPE_EMBEDDING_DIMENSIONS
            and record.get('embedding')
        )
        if is_current and not force:
            continue

        content_text = _ticket_source_text(ticket)
        image_data_url = _image_data_url(ticket, upload_folder) if include_visual else ''
        pending.append((ticket, source_hash, content_text, image_data_url))

    indexed = 0
    multimodal = [item for item in pending if item[3]]
    text_only = [item for item in pending if not item[3]]

    for ticket, source_hash, content_text, image_data_url in multimodal:
        try:
            vector = embed_multimodal(content_text, image_data_url)
            visual_text = '图片与票券文字已通过百炼多模态模型融合索引'
        except SemanticServiceError:
            warnings.append(f'票券 #{ticket["id"]} 的图片向量化失败，已使用文字内容建立索引')
            vector = embed_texts([content_text])[0]
            visual_text = ''
        if upsert_ticket_embedding(
            user_id,
            ticket['id'],
            source_hash,
            ticket.get('image_hash') or '',
            content_text,
            visual_text,
            vector,
            config.DASHSCOPE_EMBEDDING_MODEL,
        ):
            indexed += 1

    for offset in range(0, len(text_only), 32):
        batch = text_only[offset:offset + 32]
        vectors = embed_texts([item[2] for item in batch])
        for (ticket, source_hash, content_text, _), vector in zip(batch, vectors):
            if upsert_ticket_embedding(
                user_id,
                ticket['id'],
                source_hash,
                ticket.get('image_hash') or '',
                content_text,
                '',
                vector,
                config.DASHSCOPE_EMBEDDING_MODEL,
            ):
                indexed += 1

    return {
        'total': len(tickets),
        'indexed': indexed,
        'unchanged': len(tickets) - len(pending),
        'warnings': warnings[:10],
    }


def _tokens(text):
    result = set()
    for part in re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', (text or '').lower()):
        result.add(part)
        if re.fullmatch(r'[\u4e00-\u9fff]+', part):
            result.update(part)
            result.update(part[i:i + 2] for i in range(max(0, len(part) - 1)))
    return result


def _lexical_score(query, content):
    query = (query or '').strip().lower()
    content = (content or '').lower()
    if not query:
        return 0.0
    direct = 1.0 if query in content else 0.0
    query_tokens = _tokens(query)
    if not query_tokens:
        return direct
    overlap = len(query_tokens & _tokens(content)) / len(query_tokens)
    return min(1.0, direct * 0.55 + overlap * 0.65)


def _cosine(left, right):
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    norm_left = math.sqrt(sum(float(value) ** 2 for value in left))
    norm_right = math.sqrt(sum(float(value) ** 2 for value in right))
    if not norm_left or not norm_right:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_left * norm_right)))


def search_user_tickets(user_id, query, upload_folder, *, limit=12):
    query = (query or '').strip()
    if not query:
        raise ValueError('请输入想查找的记忆')
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f'问题不能超过 {MAX_QUERY_LENGTH} 个字符')
    limit = max(1, min(30, int(limit)))
    tickets = get_semantic_source_tickets(user_id)
    if not tickets:
        return {'mode': 'empty', 'data': [], 'warning': ''}

    warning = ''
    query_vector = None
    records = get_ticket_embedding_records(user_id)
    if semantic_enabled():
        try:
            refresh_user_index(user_id, upload_folder, include_visual=False)
            records = get_ticket_embedding_records(user_id)
            query_vector = embed_texts([query])[0]
        except SemanticServiceError:
            warning = '语义服务暂时不可用，本次已自动切换为关键词检索。'

    ranked = []
    for ticket in tickets:
        record = records.get(ticket['id'])
        content = record.get('content_text', '') if record else _ticket_source_text(ticket)
        lexical = _lexical_score(query, content)
        semantic = _cosine(query_vector, record.get('embedding')) if query_vector and record else 0.0
        if query_vector and record:
            semantic_normalized = (semantic + 1.0) / 2.0
            score = semantic_normalized * 0.78 + lexical * 0.22
            reason = '语义相似' if lexical < 0.35 else '语义与关键词共同匹配'
        else:
            score = lexical
            reason = '关键词匹配'
        if score > 0:
            item = dict(ticket)
            item['score'] = round(score, 4)
            item['match_reason'] = reason
            ranked.append(item)

    ranked.sort(key=lambda item: (item['score'], item.get('time') or '', item['id']), reverse=True)
    return {
        'mode': 'hybrid' if query_vector else 'keyword',
        'data': ranked[:limit],
        'warning': warning,
    }


def _memory_context(tickets):
    blocks = []
    for ticket in tickets[:MAX_CONTEXT_TICKETS]:
        blocks.append(
            '\n'.join([
                f'[票券 #{ticket["id"]}]',
                _ticket_source_text(ticket),
            ])
        )
    return '\n\n'.join(blocks)


def _parse_json_object(text):
    """容忍模型偶尔附带 Markdown 代码围栏，但只接受 JSON 对象。"""
    candidate = (text or '').strip()
    if candidate.startswith('```'):
        candidate = re.sub(r'^```(?:json)?\s*', '', candidate, flags=re.IGNORECASE)
        candidate = re.sub(r'\s*```$', '', candidate)
    start = candidate.find('{')
    end = candidate.rfind('}')
    if start < 0 or end < start:
        raise SemanticServiceError('阿里云百炼返回格式无效')
    try:
        result = json.loads(candidate[start:end + 1])
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SemanticServiceError('阿里云百炼返回格式无效') from exc
    if not isinstance(result, dict):
        raise SemanticServiceError('阿里云百炼返回格式无效')
    return result


def generate_grounded_answer(query, tickets):
    response_text = _chat_completion(
        [
            {
                'role': 'system',
                'content': (
                    '你是私人票券博物馆的记忆讲述助手。只能使用用户提供的票券上下文回答。'
                    '不得补充上下文中没有的事实；信息不足时明确说明。'
                    '回答简洁、温暖但不夸张。只输出一个合法 JSON 对象，不要输出 Markdown。'
                    'JSON 必须包含 title、answer、citations、follow_up_questions 四个字段；'
                    'citations 是实际使用的票券数字编号数组，follow_up_questions 是字符串数组。'
                ),
            },
            {
                'role': 'user',
                'content': f'用户问题：{query}\n\n可用票券上下文：\n{_memory_context(tickets)}',
            },
        ],
        max_tokens=700,
    )
    return _parse_json_object(response_text)


def _fallback_memory(query, tickets):
    if not tickets:
        return {
            'title': '还没有找到相关记忆',
            'answer': '当前票夹中没有与这个问题直接匹配的记录。可以换一个地点、年份、票据类型或活动名称再试一次。',
            'citations': [],
            'follow_up_questions': ['我去过哪些城市？', '最近收藏了哪些票券？'],
        }
    summaries = []
    for ticket in tickets[:3]:
        description = ' · '.join(filter(None, [
            ticket.get('time'), ticket.get('type'), ticket.get('city'), ticket.get('place'),
        ]))
        summaries.append(f'票券 #{ticket["id"]}：{description}')
    return {
        'title': '与你的问题相关的收藏',
        'answer': '我在票夹中找到了这些可能相关的记录：\n' + '\n'.join(summaries),
        'citations': [ticket['id'] for ticket in tickets[:3]],
        'follow_up_questions': ['按时间顺序整理这些记忆', '这些票券涉及哪些城市？'],
    }


def answer_memory_query(user_id, query, upload_folder):
    search = search_user_tickets(user_id, query, upload_folder, limit=MAX_CONTEXT_TICKETS)
    tickets = search['data']
    warning = search.get('warning', '')
    answer_mode = 'local'
    if semantic_enabled() and tickets:
        try:
            answer = generate_grounded_answer(query, tickets)
            answer_mode = 'rag'
        except SemanticServiceError:
            answer = _fallback_memory(query, tickets)
            warning = warning or '记忆生成服务暂时不可用，已展示本地可解释摘要。'
    else:
        answer = _fallback_memory(query, tickets)

    allowed_ids = {ticket['id'] for ticket in tickets}
    clean_citations = []
    for value in answer.get('citations') or []:
        try:
            ticket_id = int(value)
        except (TypeError, ValueError):
            continue
        if ticket_id in allowed_ids and ticket_id not in clean_citations:
            clean_citations.append(ticket_id)
    answer['citations'] = clean_citations
    answer['follow_up_questions'] = [
        str(item).strip()[:100]
        for item in (answer.get('follow_up_questions') or [])
        if str(item).strip()
    ][:3]
    answer['title'] = str(answer.get('title') or '个人记忆').strip()[:100]
    answer['answer'] = str(answer.get('answer') or '').strip()[:5000]

    return {
        'mode': answer_mode,
        'search_mode': search['mode'],
        'warning': warning,
        'answer': answer,
        'results': tickets,
    }
