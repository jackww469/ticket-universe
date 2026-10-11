# -*- coding: utf-8 -*-
"""
OCR 服务封装（百度通用文字识别）+ 简单规则抽取票据关键信息
"""
import base64
import re
import time
from typing import Dict, Any, List, Tuple

import requests

from config import BAIDU_OCR_API_KEY, BAIDU_OCR_SECRET_KEY, BAIDU_OCR_ENABLED
from theme_rules import match_theme_from_text
from locations import extract_location

_access_token_cache: Dict[str, Any] = {
    "token": "",
    "expire_at": 0,
}


def _get_access_token() -> str:
    if not BAIDU_OCR_ENABLED:
        raise RuntimeError("百度 OCR 未配置，请设置环境变量 BAIDU_OCR_API_KEY / BAIDU_OCR_SECRET_KEY")
    now = time.time()
    if _access_token_cache["token"] and now < _access_token_cache["expire_at"]:
        return _access_token_cache["token"]
    url = (
        "https://aip.baidubce.com/oauth/2.0/token"
        f"?grant_type=client_credentials&client_id={BAIDU_OCR_API_KEY}"
        f"&client_secret={BAIDU_OCR_SECRET_KEY}"
    )
    resp = requests.get(url, timeout=8)
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError("获取百度 OCR access_token 失败，请检查 API Key / Secret Key")
    # 官方默认有效期 30 天，这里简单缓存 25 天
    _access_token_cache["token"] = token
    _access_token_cache["expire_at"] = now + 25 * 24 * 60 * 60
    return token


def ocr_image_to_text(image_bytes: bytes) -> List[str]:
    """
    调用百度通用文字识别，返回识别出的每一行文字列表。
    """
    token = _get_access_token()
    ocr_url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token={token}"
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {"image": img_b64}
    resp = requests.post(ocr_url, headers=headers, data=data, timeout=10)
    resp.raise_for_status()
    j = resp.json()
    if "words_result" not in j:
        raise RuntimeError("OCR 返回结果异常")
    return [item.get("words", "") for item in j.get("words_result", [])]


def _extract_date(text: str) -> str:
    """
    从文本中提取日期，返回 yyyy-mm-dd 格式（简单规则）。
    """
    # 匹配 2025-10-08 / 2025/10/8 / 2025.10.08 / 2025年10月8日
    patterns = [
        r"(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})",
        r"(\d{4})年(\d{1,2})月(\d{1,2})日?",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            y, mth, d = m.group(1), int(m.group(2)), int(m.group(3))
            return f"{y}-{mth:02d}-{d:02d}"
    return ""


def _guess_type(text: str) -> str:
    """
    根据关键字粗略猜测票据类型。
    """
    t = text
    if any(k in t for k in ["车票", "火车票", "动车", "高铁", "站", "Railway"]):
        return "车票"
    if any(k in t for k in ["演唱会", "音乐会", "音乐剧", "话剧", "演出票", "剧场", "剧院"]):
        return "演出票"
    if any(k in t for k in ["景区", "公园", "景点", "门票", "山", "湖", "园", "博物馆"]):
        return "景区票"
    if any(k in t for k in ["证书", "奖状", "荣誉", "资格证", "证件"]):
        return "证书"
    return ""


def _guess_place(lines: List[str]) -> str:
    """
    从多行文本中尝试提取地点信息。
    """
    full = " ".join(lines)
    # 简单规则：包含“站 / 剧院 / 公园 / 景区 / 馆”等关键字的整行
    place_keywords = ["站", "剧院", "大剧院", "音乐厅", "公园", "景区", "广场", "博物馆", "体育馆", "影城"]
    for line in lines:
        if any(k in line for k in place_keywords):
            return line.strip()
    # 退化：如果整段里有“北京 / 上海 / 广州 / 深圳 / 成都 / 杭州 / 南京 / 西安 / 重庆 / 武汉”
    cities = ["北京", "上海", "广州", "深圳", "成都", "杭州", "南京", "西安", "重庆", "武汉", "青岛"]
    for c in cities:
        if c in full:
            return c
    return ""


def extract_ticket_fields(image_bytes: bytes) -> Dict[str, str]:
    """
    OCR + 规则抽取，返回可用于自动填充表单的字段：
    - type: 建议票据类型（规则库优先，其次关键字启发）
    - time: 日期（yyyy-mm-dd，可能为空）
    - place: 地点（可能为空）
    - province: 省份（可能为空）
    - city: 城市（可能为空）
    - raw_text: 完整识别文本（供独立编辑区展示）
    - theme_color / theme_label: 规则库匹配的主题色与名称
    - matched_keyword: 命中的关键词（若有）
    """
    lines = ocr_image_to_text(image_bytes)
    full_text = "\n".join(lines)
    date = _extract_date(full_text)
    place = _guess_place(lines)
    location = extract_location(full_text)
    province, city = location['province'], location['city']
    theme_color, theme_label, rule_type, matched_kw = match_theme_from_text(full_text)
    heuristic_type = _guess_type(full_text)
    ticket_type = (rule_type or "").strip() or heuristic_type
    return {
        "type": ticket_type,
        "time": date,
        "place": place,
        "province": province,
        "city": city,
        "raw_text": full_text,
        "location_candidates": location["candidates"],
        "location_warning": location["warning"],
        "theme_color": theme_color,
        "theme_label": theme_label,
        "matched_keyword": matched_kw or "",
    }

