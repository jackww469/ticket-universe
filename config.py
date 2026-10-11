# -*- coding: utf-8 -*-
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'ticket_universe.db')
# 会话加密密钥（生产环境务必通过环境变量设置）
SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-ticket-universe-change-me')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB

# 票据类型枚举（与前端一致）
# 说明：业务上仍以具体类型字段为准，"其他" 只是列表筛选用的汇总分类
TICKET_TYPES = ['全部', '车票', '演出票', '景区票', '证书', '其他']

# OCR 配置（使用百度通用文字识别）
# 为避免泄露密钥，推荐通过环境变量设置：
#   BAIDU_OCR_API_KEY
#   BAIDU_OCR_SECRET_KEY
BAIDU_OCR_API_KEY = os.getenv('BAIDU_OCR_API_KEY', '')
BAIDU_OCR_SECRET_KEY = os.getenv('BAIDU_OCR_SECRET_KEY', '')
BAIDU_OCR_ENABLED = bool(BAIDU_OCR_API_KEY and BAIDU_OCR_SECRET_KEY)

# 图文语义搜索与个人记忆 RAG（阿里云百炼 / DashScope）
# 未配置 DASHSCOPE_API_KEY 时，页面和接口仍可用，并自动降级为本地关键词检索与模板化摘要。
DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY', '')
DASHSCOPE_COMPATIBLE_API_BASE = os.getenv(
    'DASHSCOPE_COMPATIBLE_API_BASE',
    'https://dashscope.aliyuncs.com/compatible-mode/v1',
).rstrip('/')
DASHSCOPE_MULTIMODAL_EMBEDDING_URL = os.getenv(
    'DASHSCOPE_MULTIMODAL_EMBEDDING_URL',
    'https://dashscope.aliyuncs.com/api/v1/services/embeddings/'
    'multimodal-embedding/multimodal-embedding',
)
DASHSCOPE_EMBEDDING_MODEL = os.getenv('DASHSCOPE_EMBEDDING_MODEL', 'qwen3-vl-embedding')
DASHSCOPE_RAG_MODEL = os.getenv('DASHSCOPE_RAG_MODEL', 'qwen-plus')

_DASHSCOPE_SUPPORTED_DIMENSIONS = {256, 512, 768, 1024, 1536, 2048, 2560}
try:
    DASHSCOPE_EMBEDDING_DIMENSIONS = int(os.getenv('DASHSCOPE_EMBEDDING_DIMENSIONS', '512'))
except ValueError:
    DASHSCOPE_EMBEDDING_DIMENSIONS = 512
if DASHSCOPE_EMBEDDING_DIMENSIONS not in _DASHSCOPE_SUPPORTED_DIMENSIONS:
    DASHSCOPE_EMBEDDING_DIMENSIONS = 512

try:
    DASHSCOPE_TIMEOUT_SECONDS = max(5, min(120, int(os.getenv('DASHSCOPE_TIMEOUT_SECONDS', '30'))))
except ValueError:
    DASHSCOPE_TIMEOUT_SECONDS = 30

SEMANTIC_SEARCH_ENABLED = bool(DASHSCOPE_API_KEY)
