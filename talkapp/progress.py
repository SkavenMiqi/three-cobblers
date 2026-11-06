"""Small, persistent task plans extracted from conversation requirements."""
import json
import re


def parse_steps(text):
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    try:
        values = json.loads(text)
    except ValueError:
        return []
    if not isinstance(values, list):
        return []
    result, seen = [], set()
    for item in values[:12]:
        if not isinstance(item, dict):
            continue
        title, detail = item.get('title'), item.get('detail', '')
        if not isinstance(title, str) or not title.strip() or not isinstance(detail, str):
            continue
        title = title.strip()[:60]
        if title in seen:
            continue
        seen.add(title)
        result.append({'title': title, 'detail': detail.strip()[:500]})
    return result


def has_requirements(text):
    return len(text.strip()) >= 10 and any(word in text for word in (
        '我想', '需要', '帮我', '计划', '步骤', '目标', '实现', '做一个', '完成', '安排', '继续', '开发', '学习', '需求'))
