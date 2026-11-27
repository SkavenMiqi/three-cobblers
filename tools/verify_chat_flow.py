"""Exercise real Kivy actions with a deterministic provider, isolated from user data."""
import os
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fake_reply(config, rows, on_delta, cancel, **kwargs):
    from talkapp import diagram
    from talkapp.photo_annotations import MARKER
    if kwargs.get('task') == 'engineering_route':
        return 'CHAT'
    if kwargs.get('prompt', '').startswith('从用户原话提取可跨会话'):
        return '[]'
    if kwargs.get('task') == 'progress':
        return '[{"title":"准备环境","detail":"安装所需依赖"}]'
    if rows and rows[-1][1] == '已经在 IDE 里编译通过了，还没烧录。帮我确认进度。' and kwargs.get('api_messages'):
        messages = kwargs['api_messages']
        assert '将已确认完成的步骤勾选' in messages[0]['content']
        results = [json.loads(item['content']) for item in messages if item['role'] == 'tool']
        if len(results) < 2:
            name, arguments = 'get_progress', {}
            if results:
                step = next(step for step in results[0]['steps'] if step['title'] == '编译程序')
                name, arguments = 'update_step', {'id': step['id'], 'done': True, 'note': 'IDE 编译通过，尚未烧录。'}
            kwargs['on_tools']([{'id': f'progress-{len(results)}', 'type': 'function',
                                 'function': {'name': name, 'arguments': json.dumps(arguments)}}])
            return ''
        assert results[-1]['saved']
        return '已勾选编译程序，烧录仍未完成。'
    if kwargs.get('tools') and rows and '你好，测试基础聊天' in rows[-1][1]:
        messages = kwargs.get('api_messages') or []
        assert '当前对话的输出模式：精简' in messages[0]['content']
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
    messages = kwargs.get('api_messages') or [{}]
    if rows and rows[-1][1] == '画个接线示意图':
        assert diagram.MARKER in messages[0].get('content', '')
        assert not any(isinstance(msg.get('content'), list) for msg in messages), 'diagram request needs no input image'
        text = '示意说明\n' + diagram.MARKER + '\n{"nodes":[{"id":"a","label":"电源"},{"id":"b","label":"电阻"}],"links":[{"from":"a","to":"b","label":"正极接电阻"}]}'
        on_delta(text)
        return text
    if rows and rows[-1][1] == '图给我标一下':
        assert MARKER in messages[0].get('content', ''), 'photo follow-up lacks annotation instructions'
        assert sum(part['type'] == 'image_url' for part in messages[-1]['content']) == 2
        assert not any(isinstance(msg.get('content'), list) for msg in messages[:-1]), 'originals were duplicated'
    if MARKER in messages[0].get('content', ''):
        on_delta(text + '\n<<<PHOTO_')
        text += '\n' + MARKER + '\n{"image":2,"marks":[{"kind":"circle","box":[100,100,600,600],"label":"检查这里"}]}'
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
            if view.busy or view.lan_routing:
                return
            if stage[0] == 0:
                from types import SimpleNamespace
                slider = view.output_slider
                assert slider.status_label.text == '正等'
                touch = SimpleNamespace(x=slider.right - 1, is_mouse_scrolling=False, grab_current=None)
                touch.pos = (touch.x, slider.center_y)
                touch.grab = lambda widget: setattr(touch, 'grab_current', widget)
                touch.ungrab = lambda _: setattr(touch, 'grab_current', None)
                assert slider.on_touch_down(touch)
                assert slider.status_label.text == '详细'
                touch.x = slider.x + slider.width * .3
                assert slider.on_touch_move(touch)
                assert slider.status_label.text == '适度'
                touch.x = slider.x + 1
                assert slider.on_touch_up(touch)
                assert slider.status_label.text == '精简'
                assert tuple(slider.status_label.color) == slider.COLORS[0]
                assert view.history.output_mode(view.chat_id) == 0
                from talkapp import theme
                indicator = view.harness_indicator
                view.harness_indicator = view.icon_button('⋮', lambda: None)
                view.status.text = '同步暂不可用，将自动重试'
                view.set_harness_status(True)
                assert view.status.text == '连接成功'
                assert tuple(view.status.color) == theme.LED_GREEN
                view.set_harness_status(False)
                assert tuple(view.status.color) == theme.DANGER
                view.set_harness_status(None)
                assert tuple(view.status.color) == theme.TEXT_MUTED
                view.harness_indicator = indicator
                with patch.object(view, 'action_sheet') as sheet:
                    view.conversation_menu()
                    assert not {'连接 Harness', '项目与进度'} & {name for name, _ in sheet.call_args.args[1]}
                for widget in (view.status, view.progress_button):
                    original = widget.text
                    widget.text = '很长的状态文字' * 100
                    widget.caption.texture_update()
                    assert widget.overflow > 0
                    widget._restart()
                    from kivy.animation import Animation
                    assert any(widget.uid in motion._widgets for motion in Animation._instances)
                    widget.text = '短'
                    widget.caption.texture_update()
                    widget._restart()
                    assert widget.overflow == widget.offset == 0
                    assert not any(widget.uid in motion._widgets for motion in Animation._instances)
                    widget.text = original
                draft, height = view.input.text, view.input.parent.height
                view.input.text = ('多行测试聊天输入' * 30 + '\n') * 8
                assert view.input.parent.height == height, 'multiline input stretched the bottom bar'
                view.input.text = draft
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
                assert len(image_list(path[-1]['image'])) == 1
                assert '本次第 2 张图' in path[-1]['text'] and '检查这里' in path[-1]['text']
                assert 'PHOTO_MARKS' not in path[-1]['text']
                assert view.history.files(path[0]['id'])[0]['name'] == 'demo.txt'
                assert view.history.steps(view.chat_id)[0]['title'] == '验证软件操作'
                view.history.save_library(view.chat_id, '项目资料.md', '[第1页]\nPython学习计划')
                view.regenerate(path[-1])
            elif stage[0] == 2:
                from talkapp.collaboration import CollaborationConfig
                CollaborationConfig().save()
                path = view.history.path(view.chat_id)
                assert len(view.history.siblings(path[-1])) == 2
                view.input.text = '图给我标一下'
                view.send()
            elif stage[0] == 3:
                path = view.history.path(view.chat_id)
                assert path[-2]['image'] is None and len(image_list(path[-1]['image'])) == 1, path[-1]['error']
                assert '上一组照片的第 2 张图' in path[-1]['text']
                view.editing = None
                view.input.text = 'failure'
                view.send(edit=True)
            elif stage[0] == 4:
                assert view.history.path(view.chat_id)[-1]['state'] == 'failed'
                from talkapp.collaboration import CollaborationConfig
                CollaborationConfig().save()
                view.new_chat()
                assert view.output_slider.status_label.text == '正等'
                view.input.text = 'cancel-me'
                view.send()
            elif stage[0] == 5:
                assert view.history.path(view.chat_id)[-1]['state'] == 'cancelled'
                assert view.history.path(view.chat_id)[-1]['text']
                view.new_chat()
                view.config.context_tokens = 8000
                for i in range(8):
                    view.history.append(view.chat_id, 'user', '之前的讨论' * 180)
                    view.history.append(view.chat_id, 'assistant', '回答' * 180)
                view.input.text = '继续'
                view.send()
            elif stage[0] == 6:
                if view.busy:
                    return
                path = view.history.path(view.chat_id)
                assert path[-1]['state'] == 'complete', path[-1]['error']
                assert view.history.summary(view.chat_id, path)
                view.new_chat()
                view.config.context_tokens = 16000
                view.input.text = '画个接线示意图'
                view.send()
            elif stage[0] == 7:
                reply = view.history.path(view.chat_id)[-1]
                assert reply['state'] == 'complete' and len(image_list(reply['image'])) == 1, reply['error']
                assert reply['text'] == '示意说明'
                view.switch_model()
                view.show_summary()
                view.speech_settings()
                view.text_options()
                view.usage_view()
                view.preview_files()
                view.backup_settings()
                view.view_image(image_data(Path(folder) / 'example.png'))
                view.export_chat()
                for n in range(13):
                    view.history.merge_steps(view.chat_id, view.history.path(view.chat_id)[0]['id'],
                                             [{'title': f'折叠测试 {n}', 'detail': ''}])
                    item = next(item for item in view.history.steps(view.chat_id) if item['title'] == f'折叠测试 {n}')
                    view.history.step_state(item['id'], done=True)
                long_goal = '完成装置并记录每一个实验结果。' * 30
                view.history.set_goals(view.chat_id, [long_goal, '制作演示原型'])
                view.open_progress()
                from kivy.uix.popup import Popup
                progress = next(w for w in Window.children if isinstance(w, Popup) and w.title == '当前对话 · 完成步骤')
                goal = next(w for w in progress.walk() if getattr(w, 'text', '') == f'1. {long_goal}')
                goal.width = 280
                goal.texture_update()
                assert goal.texture_size[0] < goal.width and goal.height > goal.texture_size[1] > 48
                assert any(getattr(w, 'text', '') == '2. 制作演示原型' for w in progress.walk())
                assert any('折叠测试 0' in getattr(w, 'text', '') for w in progress.walk())
                progress.dismiss(animation=False)
                members = [[s['id'], s['title'], s['detail']] for s in view.history.steps(view.chat_id) if s['title'].startswith('折叠测试 ')]
                assert view.history.save_step_fold(view.chat_id, '完成十三项测试', members)
                view.open_progress()
                progress = next(w for w in Window.children if isinstance(w, Popup) and w.title == '当前对话 · 完成步骤')
                fold = next(w for w in progress.walk() if getattr(w, 'text', '') == '已完成 13 项 · 展开明细')
                assert any(getattr(w, 'text', '') == '完成十三项测试' for w in progress.walk())
                assert not any('折叠测试 0' in getattr(w, 'text', '') for w in progress.walk())
                fold.dispatch('on_release')
                assert any('折叠测试 0' in getattr(w, 'text', '') for w in progress.walk())
                step = next(w for w in progress.walk() if getattr(w, 'text', '') == '1. 折叠测试 0')
                step.dispatch('on_release')
                detail = next(w for w in Window.children if isinstance(w, Popup) and w.title == '步骤详情')
                assert any(getattr(w, 'text', '') == '折叠测试 0' for w in detail.walk())
                detail.dismiss(animation=False)
                progress.dismiss(animation=False)
                top = next(row for row in view.children if view.status in row.children)
                pairing = next(control for control in top.children if getattr(control, 'text', '') == '配对')
                history = next(control for control in top.children if '☰' in getattr(control, 'text', ''))
                assert top.children.index(pairing) == top.children.index(history) + 1
                with patch('talkapp.pairing_view.open_pairing') as open_pairing:
                    pairing.dispatch('on_release')
                    open_pairing.assert_called_once_with(view)
                from kivy.uix.popup import Popup
                from talkapp import lan_pairing
                with patch.object(lan_pairing, 'local_address', return_value='192.168.1.2'), \
                        patch.object(view, 'start_lan_host') as start_host:
                    host = start_host.return_value
                    host.paired.return_value = False
                    host.invitation.return_value = 'TALKAPP1-smoke-test'
                    pairing.dispatch('on_release')
                    pair_popup = next(w for w in Window.children if isinstance(w, Popup) and w.title == '局域网设备配对')
                    controls = {w.text: w for w in pair_popup.content.children[0].children if hasattr(w, 'text')}
                    assert '启动时自动同步：关' in controls
                    controls['显示配对二维码'].dispatch('on_release')
                    qr = next(w for w in Window.children if isinstance(w, Popup) and w.title == '请在手机 TalkApp 中拍摄此二维码')
                    qr.dismiss(animation=False)
                    pair_popup.dismiss(animation=False)
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
                for widget in list(Window.children):
                    if isinstance(widget, Popup):
                        widget.dismiss(animation=False)
                view.new_chat()
                source = view.history.append(view.chat_id, 'user', '先编译，再烧录。')
                view.history.append(view.chat_id, 'assistant', '按这两步操作。')
                view.history.merge_steps(view.chat_id, source, [
                    {'title': '编译程序', 'detail': '在 IDE 中验证'},
                    {'title': '烧录程序', 'detail': '上传到开发板'},
                ])
                view.input.text = '已经在 IDE 里编译通过了，还没烧录。帮我确认进度。'
                view.send()
            elif stage[0] == 8:
                assert [step['done'] for step in view.history.steps(view.chat_id)] == [1, 0]
                assert view.progress_button.text.startswith('进度 1/2')
                assert view.history.progress_notes(view.chat_id, '编译')[0]['text'] == 'IDE 编译通过，尚未烧录。'
                stage[0] += 1
                app.stop()
                print('CHAT_FLOW_OK: stream, branches, photo follow-up, local diagram, failure, cancellation, summary, Markdown, sidebar')
                return False
            if stage[0] == 4:
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
    if errors or stage[0] < 9:
        raise SystemExit('Chat flow did not complete')
