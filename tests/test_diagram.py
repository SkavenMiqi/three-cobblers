import base64
import io
import json
import unittest

from PIL import Image

from talkapp import diagram
from talkapp.photo_annotations import split_reply


class DiagramTests(unittest.TestCase):
    def test_request_and_hidden_payload(self):
        self.assertIsNotNone(diagram.REQUEST.search('画个接线示意图'))
        self.assertIsNotNone(diagram.REQUEST.search('画一张面包板接线图给我'))
        self.assertIsNone(diagram.REQUEST.search('这个电阻怎么接？'))
        self.assertEqual(split_reply('说明\n<<<LOCAL_', streaming=True, marker=diagram.MARKER), ('说明', ''))
        self.assertEqual(split_reply('说明\n' + diagram.MARKER + '\n{}', marker=diagram.MARKER), ('说明', '{}'))

    def test_draws_chinese_nodes_with_links(self):
        spec = {'title': '接线示意图', 'nodes': [{'id': 'a', 'label': '电源'}, {'id': 'b', 'label': '电阻'}],
                'links': [{'from': 'a', 'to': 'b', 'label': '正极接电阻'}]}
        url = diagram.render(json.dumps(spec, ensure_ascii=False))
        with Image.open(io.BytesIO(base64.b64decode(url.split(',', 1)[1]))) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertEqual(image.width, 1024)
            self.assertGreater(len(image.getcolors(1024 * 1024)), 10)
        spec['links'][0]['to'] = 'unknown'
        self.assertIsNone(diagram.render(json.dumps(spec)))
        self.assertIsNone(diagram.render('{'))
        self.assertIsNone(diagram.render('x' * 7000))
