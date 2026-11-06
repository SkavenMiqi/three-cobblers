"""OpenAI-compatible SSE client; retains fitness's MiMo authentication support."""
import base64
import io
import json
import ssl
import urllib.error
import urllib.request

import certifi
from PIL import Image, ImageOps


def image_data(path):
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original)
        image.thumbnail((1600, 1600))
        output = io.BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def image_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.startswith('['):
        try:
            values = json.loads(value)
            return [item for item in values if isinstance(item, str) and item.startswith('data:image/')]
        except ValueError:
            return []
    return [value] if isinstance(value, str) and value.startswith('data:image/') else []


def audio_input(value):
    if isinstance(value, str) and value.startswith('{'):
        try:
            result = json.loads(value).get('audio')
            if isinstance(result, dict) and result.get('format') in ('wav', 'm4a', 'mp3') and isinstance(result.get('data'), str):
                return result
        except (ValueError, AttributeError):
            pass
    return None


def messages_for_api(rows, prompt, *, prepared=False):
    # Retain whole recent turns, with a bounded text budget. Disk history is never truncated.
    selected, budget = list(rows) if prepared else [], 0
    if not prepared:
        for row in reversed(rows):
            budget += len(row[1])
            if selected and (budget > 48000 or len(selected) >= 40):
                break
            selected.append(row)
        selected.reverse()
    while selected and selected[0][0] != "user":
        selected.pop(0)
    messages = [{"role": "system", "content": prompt}] if prompt else []
    for role, text, image in selected:
        content = text
        audio = audio_input(image)
        if audio:
            content = [{'type': 'input_audio', 'input_audio': audio},
                       {'type': 'text', 'text': '请直接听这段语音并理解用户的请求，用文字回复。' if text == '（语音消息）' else text}]
        elif image_list(image):
            content = [{"type": "text", "text": text or "请描述这些图片"}] + [
                {"type": "image_url", "image_url": {"url": value}} for value in image_list(image)]
        messages.append({"role": role, "content": content})
    return messages


def stream_reply(config, rows, on_delta, cancel, *, prompt=None, prepared=False, task='chat', on_usage=None,
                 tools=None, on_tools=None, api_messages=None):
    config.validate()
    base = config.api_base_url.rstrip("/")
    # A versioned or provider-specific base is preserved (e.g. /zen/go).
    if not base.endswith("/chat/completions"):
        if base.count("/") == 2:
            base += "/v1"
        base += "/chat/completions"
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if "xiaomimimo" in urllib.parse.urlparse(base).hostname.lower():
        headers["api-key"] = config.api_key
    else:
        headers["Authorization"] = "Bearer " + config.api_key
    body = {"model": config.model, "messages": api_messages if api_messages is not None else messages_for_api(rows, config.system_prompt if prompt is None else prompt,
                                                             prepared=prepared), "stream": True}
    if tools:
        body['tools'] = tools
        body['tool_choice'] = 'auto'
    from .context import request_budget
    request_budget(config, body['messages'], tools)
    body['max_completion_tokens'] = config.max_output_tokens
    if task == 'audio_parse' and 'xiaomimimo' in (urllib.parse.urlparse(base).hostname or '').lower():
        # Transcription is a direct perception task. Reasoning-only streams may
        # consume the completion budget without emitting a usable transcript.
        body['thinking'] = {'type': 'disabled'}
    request = urllib.request.Request(base, data=json.dumps(body).encode(), headers=headers)
    text = ""
    finished = False
    usage = {}
    tool_calls = {}
    try:
        with urllib.request.urlopen(request, timeout=60, context=ssl.create_default_context(cafile=certifi.where())) as response:
            if "text/event-stream" not in response.headers.get("Content-Type", ""):
                payload = json.load(response)
                usage = payload.get('usage') or {}
                text = payload["choices"][0]["message"].get("content") or ""
                if on_tools:
                    on_tools(payload['choices'][0]['message'].get('tool_calls') or [])
                if not cancel.is_set():
                    on_delta(text)
                return text
            for raw in response:
                if cancel.is_set():
                    break
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    finished = True
                    break
                payload = json.loads(data)
                if payload.get('usage'):
                    usage = payload['usage']
                if "error" in payload:
                    raise ValueError("服务商返回流式错误，请检查模型与账户状态")
                choices = payload.get("choices") or []
                if choices and choices[0].get('finish_reason'):
                    finished = True
                event_delta = (choices[0].get('delta') or {}) if choices else {}
                delta = event_delta.get('content')
                for call in event_delta.get('tool_calls') or []:
                    index = call.get('index', 0)
                    current = tool_calls.setdefault(index, {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                    if call.get('id'):
                        current['id'] = call['id']
                    function = call.get('function') or {}
                    current['function']['name'] += function.get('name') or ''
                    current['function']['arguments'] += function.get('arguments') or ''
                if isinstance(delta, str):
                    text += delta
                    on_delta(text)
    except urllib.error.HTTPError as exc:
        if exc.code == 400:
            try:
                error = json.loads(exc.read(8192)).get('error', {})
                message = error.get('message', '') if isinstance(error, dict) else ''
                if 'audio input is not available' in message.lower():
                    raise ValueError('当前模型服务接口未开放音频输入，请换用支持音频的模型/服务商；未进行文字转写') from None
            except (json.JSONDecodeError, AttributeError):
                pass
        hints = {401: "密钥无效", 403: "无访问权限", 404: "接口地址或模型不存在",
                 429: "额度不足或请求过于频繁", 400: "请求不被支持，请确认模型支持图片及当前接口"}
        raise ValueError(f"API {exc.code}：{hints.get(exc.code, '服务暂不可用')}") from None
    except urllib.error.URLError:
        raise ValueError("网络连接失败，请检查网络及 API 地址") from None
    finally:
        if on_usage:
            from .context import estimate
            reported = 'prompt_tokens' in usage or 'input_tokens' in usage
            incoming = int(usage.get('prompt_tokens', usage.get('input_tokens', 0))) if reported else int(sum(estimate(r[1]) + 2400 * len(image_list(r[2])) for r in rows) + estimate(config.system_prompt if prompt is None else prompt))
            outgoing = int(usage.get('completion_tokens', usage.get('output_tokens', 0))) if reported else int(estimate(text)) if text else 0
            cost = (incoming * config.input_price + outgoing * config.output_price) / 1000000 if reported and (config.input_price or config.output_price) else None
            on_usage(dict(task=task, model=config.model, provider=urllib.parse.urlparse(base).hostname,
                          input_tokens=incoming, output_tokens=outgoing, reported=int(reported), cost=cost))
    if not cancel.is_set() and not finished:
        raise ValueError('连接提前结束，已保存部分回答，可重试')
    if on_tools and not cancel.is_set():
        on_tools([tool_calls[index] for index in sorted(tool_calls)])
    return text
