"""Shared location vocabulary. Unknown locations remain editable and are preserved."""
import json
from pathlib import Path

LOCATIONS = json.loads((Path(__file__).parent / 'data' / 'locations.json').read_text(encoding='utf-8'))
ALIASES = {'内蒙古自治区': '内蒙古', '广西壮族自治区': '广西', '西藏自治区': '西藏',
           '宁夏回族自治区': '宁夏', '新疆维吾尔自治区': '新疆',
           '香港特别行政区': '香港', '澳门特别行政区': '澳门'}
for province in LOCATIONS:
    ALIASES[province] = province
    ALIASES[province + ('市' if province in ('北京', '上海', '天津', '重庆') else '省')] = province


def normalize_location(province='', city=''):
    province, city = (province or '').strip(), (city or '').strip()
    province = ALIASES.get(province, province)
    known_cities = {c for cities in LOCATIONS.values() for c in cities}
    if city.endswith('市') and city[:-1] in known_cities:
        city = city[:-1]
    candidates = [p for p, cities in LOCATIONS.items() if city and city in cities]
    if not province and len(candidates) == 1:
        province = candidates[0]
    if not city and province in ('北京', '上海', '天津', '重庆', '香港', '澳门'):
        city = province
    return province, city


def extract_location(text):
    matches = [(p, c) for p, cities in LOCATIONS.items() for c in cities if c in text]
    # Do not mistake a shorter city name inside another city for a second destination.
    matches = [(p, c) for p, c in matches if not any(c != longer and c in longer for _, longer in matches)]
    provinces = {p for alias, p in ALIASES.items() if alias in text} | {p for p in LOCATIONS if p in text}
    if len(provinces) == 1:
        within = [(p, c) for p, c in matches if p in provinces]
        if within:
            matches = within
    matches = sorted(set(matches))
    candidates = [{'province': p, 'city': c} for p, c in matches]
    if len(matches) == 1:
        p, c = matches[0]
        return {'province': p, 'city': c, 'candidates': candidates, 'warning': ''}
    return {'province': next(iter(provinces)) if len(provinces) == 1 else '', 'city': '',
            'candidates': candidates,
            'warning': '识别到多个城市，请选择此次票据对应的地点。' if matches else '未能确定城市，请手动校对。'}
