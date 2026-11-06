"""Exercise real Kivy actions with a deterministic provider, isolated from user data."""
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fake_reply(config, rows, on_delta, cancel, **kwargs):
    if kwargs.get('prompt', '').startswith('从用户原话提取可跨会话'):
        return '[]'
    if kwargs.get('task') == 'progress':
        return '[{"title":"准备环境","detail":"安装所需依赖"}]'
    if kwargs.get('tools') and rows and '你好，测试基础聊天' in rows[-1][1]:
        messages = kwargs.get('api_messages') or []
        if not any(item['role'] == 'tool' for item in messages):
            kwargs['on_tools']([{'id': 'test-step-call', 'type': 'function', 'function': {
                'name': 'add_steps', 'arguments': '{"steps":[{"title":"验证软件操作","detail":"工具真正写入步骤"}]}'}}])
            return ''
    if kwargs.get('prompt', '').startswith('维护长期记忆'):
        return 'SKIP'
    if kwargs.get('prompt', '').startswith('从用户原话'):
        return '["用户喜欢结合例子学习Python"]'
    if kwargs.get('prompt', '').startswith('为这段'):
        return '测试对话'
    if kwargs.get('prompt', '').startswith('请压缩'):
        return '用户正在测试聊天，保留已确认信息。'
    if any('failure' in row[1] for row in rows):
        on_delta('已收到的一部分')
        raise ValueError('模拟网络中断')
    if any('cancel-me' in row[1] for row in rows):
        for i in range(30):
            if cancel.is_set():
                break
            on_delta('部分回答' * (i + 1))
            time.sleep(.015)
        return '部分回答'
    text = '# 测试标题\n\n**粗体** 与列表：\n- 第一项\n- 第二项\n\n| 项目 | 内容 |\n| --- | --- |\n| A | 中文表格 |\n\n```python\nprint("hello")\n```'
    on_delta(text)
    return text


with tempfile.TemporaryDirectory() as folder:
    os.environ['TALKAPP_DATA_DIR'] = folder
    from kivy.clock import Clock
    from main import TalkApp
    from talkapp.storage import Config
    from kivy.core.window import Window
    Config(api_key='fake', api_base_url='https://example.com/v1').save()
    app = TalkApp()
    errors = []
    stage = [0]

    def step(_):
        try:
            from talkapp.client import image_data, image_list
            view = app.chat
            if view.busy and stage[0] != 5:
                return
            if stage[0] == 0:
                from talkapp.collaboration import CollaborationConfig, identity
                from dataclasses import asdict
                profile = asdict(Config.load())
                CollaborationConfig(enabled=True, members=[identity(profile)], review=True).save()
                from PIL import Image
                image_path = Path(folder) / 'example.png'
                Image.new('RGB', (32, 32), 'blue').save(image_path)
                view.set_image(image_data(image_path))
                view.set_image(image_data(image_path))
                view.pending_files = [{'name': 'demo.txt', 'content': '文件的测试内容：Python学习计划。'}]
                view.input.text = '你好，测试基础聊天'
                view.send()
            elif stage[0] == 1:
                path = view.history.path(view.chat_id)
                assert path[-1]['state'] == 'complete'
                assert len(image_list(path[0]['image'])) == 2
                assert view.history.files(path[0]['id'])[0]['name'] == 'demo.txt'
                assert view.history.steps(view.chat_id)[0]['title'] == '验证软件操作'
                view.history.save_library(view.chat_id, '项目资料.md', '[第1页]\nPython学习计划')
                view.regenerate(path[-1])
            elif stage[0] == 2:
                path = view.history.path(view.chat_id)
                assert len(view.history.siblings(path[-1])) == 2
                view.editing = None
                view.input.text = 'failure'
                view.send(edit=True)
            elif stage[0] == 3:
                assert view.history.path(view.chat_id)[-1]['state'] == 'failed'
                from talkapp.collaboration import CollaborationConfig
                CollaborationConfig().save()
                view.new_chat()
                view.input.text = 'cancel-me'
                view.send()
            elif stage[0] == 4:
                # Stage 4 is reached when the request has completed; cancellation
                # itself is scheduled separately below at the beginning of stage 3.
                assert view.history.path(view.chat_id)[-1]['state'] == 'cancelled'
                assert view.history.path(view.chat_id)[-1]['text']
                view.new_chat()
                view.config.context_tokens = 4000
                for i in range(8):
                    view.history.append(view.chat_id, 'user', '之前的讨论' * 180)
                    view.history.append(view.chat_id, 'assistant', '回答' * 180)
                view.input.text = '继续'
                view.send()
            elif stage[0] == 5:
                if view.busy:
                    return
                assert view.history.summary(view.chat_id, view.history.path(view.chat_id))
                view.switch_model()
                view.show_summary()
                view.speech_settings()
                view.text_options()
                view.usage_view()
                view.preview_files()
                view.backup_settings()
                view.view_image(image_data(Path(folder) / 'example.png'))
                view.export_chat()
                view.open_progress()
                view.find_in_chat()
                view.prompt_library()
                view.project_manager()
                view.library_view()
                view.context_view()
                original = view.history.db.execute('SELECT reply_id FROM action_log LIMIT 1').fetchone()
                if original:
                    view.action_details(original[0])
                view.pause()
                view.resume()
                view.open_history()
                Window.screenshot(name=str(Path(folder) / 'history.png'))
                app.stop()
                print('CHAT_FLOW_OK: stream, branches, failure, cancellation, summary, Markdown, sidebar')
                return False
            if stage[0] == 3:
                def stop_after_delta(_):
                    if view.busy and not view.reply_pending and not view.latest:
                        Clock.schedule_once(stop_after_delta, .02)
                    elif view.busy:
                        view.send()
                Clock.schedule_once(stop_after_delta, .02)
            stage[0] += 1
        except Exception as exc:
            errors.append(exc)
            app.stop()
            raise

    with patch('talkapp.ui.stream_reply', side_effect=fake_reply):
        Clock.schedule_interval(step, .18)
        Clock.schedule_once(lambda _: app.stop(), 15)
        try:
            app.run()
        finally:
            if hasattr(app, 'chat') and not app.chat.closed:
                app.chat.shutdown()
    if errors or stage[0] < 5:
        raise SystemExit('Chat flow did not complete')
