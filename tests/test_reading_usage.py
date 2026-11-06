import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from talkapp.client import stream_reply
from talkapp.storage import Config, History
from talkapp.reading import read_document, fetch_page, search_web, needs_search, select_passages


class ReadingUsageTests(unittest.TestCase):
    def test_text_docx_pdf_and_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '资料.md'
            path.write_text('# 项目\n我们正在做安卓聊天。', encoding='utf-8')
            self.assertIn('安卓', read_document(path)['content'])
            from docx import Document
            doc = Document()
            doc.add_paragraph('Word内容')
            table = doc.add_table(rows=1, cols=2)
            table.cell(0, 0).text = '表格'
            doc.save(Path(directory) / 'test.docx')
            self.assertIn('表格', read_document(Path(directory) / 'test.docx')['content'])
            from pypdf import PdfWriter
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            writer.write(Path(directory) / 'empty.pdf')
            with self.assertRaisesRegex(ValueError, 'OCR'):
                read_document(Path(directory) / 'empty.pdf')

    def test_web_extraction_and_search_contract(self):
        def handler(request):
            if request.method == 'GET':
                return httpx.Response(200, headers={'content-type': 'text/html'},
                    text='<title>测试网页</title><script>secret</script><main>有效正文</main>')
            self.assertEqual(json.loads(request.content)['query'], '今天新闻')
            return httpx.Response(200, json={'results': [{'title': '新闻', 'url': 'https://example.com', 'content': '事实'}]})
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch('talkapp.reading.httpx.Client', return_value=client), patch('talkapp.reading.public_url', side_effect=lambda value: value):
            page = fetch_page('https://example.com')
            self.assertIn('有效正文', page['text'])
            self.assertNotIn('secret', page['text'])
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch('talkapp.reading.httpx.Client', return_value=client):
            self.assertEqual(search_web('今天新闻', key='test')[0]['title'], '新闻')
        self.assertTrue(needs_search('最新新闻', 'auto'))
        self.assertFalse(needs_search('最新新闻', 'off'))
        self.assertTrue(needs_search('你好', 'on'))

    def test_usage_reported_and_estimated_are_distinct(self):
        class Response(io.BytesIO):
            headers = {'Content-Type': 'text/event-stream'}
        data = b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: {"usage":{"prompt_tokens":100,"completion_tokens":10},"choices":[]}\n\ndata: [DONE]\n'
        records = []
        with patch('urllib.request.urlopen', return_value=Response(data)):
            stream_reply(Config(api_key='test', input_price=2, output_price=4), [('user', 'hello', None)],
                         lambda _: None, threading.Event(), task='title', on_usage=records.append)
        self.assertEqual(records[0]['input_tokens'], 100)
        self.assertEqual(records[0]['reported'], 1)
        self.assertAlmostEqual(records[0]['cost'], .00024)
        with patch('urllib.request.urlopen', return_value=Response(b'data: [DONE]\n')):
            stream_reply(Config(api_key='test'), [('user', 'hello', None)], lambda _: None,
                         threading.Event(), on_usage=records.append)
        self.assertEqual(records[-1]['reported'], 0)
        self.assertIsNone(records[-1]['cost'])

    def test_attachments_follow_branch_and_delete_with_message(self):
        h = History(':memory:')
        try:
            chat = h.create()
            original = h.append(chat, 'user', 'first')
            h.attach(original, [{'name': 'note.txt', 'content': 'important'}])
            h.append(chat, 'user', 'edited', parent=None)
            self.assertEqual(h.files(original)[0]['content'], 'important')
            self.assertEqual(h.matching_message(chat, 'first')['id'], original)
            h.remove_branch(original)
            self.assertEqual(h.files(original), [])
        finally:
            h.close()

    def test_passages_contain_relevant_section(self):
        value = '普通内容' * 1000 + '目标Python方案' * 200 + '无关内容' * 1000
        self.assertIn('Python', select_passages(value, 'Python方案', 3500))
