import base64
import io
import json
import unittest

from PIL import Image
from talkapp.photo_annotations import MARKER, annotated_photo, reuse_previous_photo, split_reply


def photo(color):
    with io.BytesIO() as output:
        Image.new('RGB', (320, 240), color).save(output, format='JPEG')
        return 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode('ascii')


class PhotoAnnotationTests(unittest.TestCase):
    def test_follow_up_uses_latest_original_without_changing_history(self):
        original = photo('blue')
        path = [{'role': 'user', 'text': '', 'image': photo('red')},
                {'role': 'user', 'text': '', 'image': original},
                {'role': 'assistant', 'text': '说明', 'image': photo('green')},
                {'role': 'user', 'text': '图给我标一下', 'image': None}]
        result, reused = reuse_previous_photo(path)
        self.assertTrue(reused)
        self.assertEqual(result[-1]['image'], original)
        self.assertIsNone(result[1]['image'])
        self.assertEqual(path[1]['image'], original)
        self.assertIsNone(path[-1]['image'])
        path[-1]['text'] = '你再解释一下'
        self.assertEqual(reuse_previous_photo(path), (path, False))

    def test_machine_output_never_shown_in_photo_reply(self):
        self.assertEqual(split_reply('判断\n<<<', streaming=True), ('判断', ''))
        self.assertEqual(split_reply('判断\n' + MARKER + '\n{'), ('判断', '{'))
        self.assertEqual(split_reply('判断'), ('判断', ''))

    def test_draws_on_selected_copy_and_ignores_invalid_marks(self):
        photos = [photo('red'), photo('blue')]
        spec = {'image': 2, 'marks': [
            {'kind': 'circle', 'box': [200, 200, 600, 600], 'label': '接口'},
            {'kind': 'arrow', 'points': [800, 800, 620, 650], 'label': '补拍'},
            {'kind': 'arrow', 'points': [True, 200, 300, 400], 'label': '无效'},
        ]}
        data, legend = annotated_photo(json.dumps(spec), photos)
        self.assertNotEqual(data, photos[1])
        self.assertIn('本次第 2 张图', legend)
        self.assertIn('2. 补拍', legend)
        self.assertNotIn('无效', legend)
        with Image.open(io.BytesIO(base64.b64decode(data.split(',', 1)[1]))) as result:
            self.assertEqual(result.size, (320, 240))
            self.assertGreater(result.getpixel((0, 0))[2], 240)
        spec['image'] = 3
        self.assertIsNone(annotated_photo(json.dumps(spec), photos))
        self.assertIsNone(annotated_photo('{', photos))
