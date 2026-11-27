import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from talkapp.client import image_data
from talkapp.platform_input import AndroidInput


class MobileInputTests(unittest.TestCase):
    def test_camera_uri_uses_parcelable_overload(self):
        camera = AndroidInput.__new__(AndroidInput)
        camera.camera_path = None
        camera.on_error = Mock()
        activity, uri, intent, parcelable = Mock(), Mock(), Mock(), Mock()
        activity.getContentResolver.return_value.insert.return_value = uri
        intent_class = Mock(return_value=intent)
        classes = {
            'org.kivy.android.PythonActivity': Mock(mActivity=activity),
            'android.os.Build$VERSION': Mock(SDK_INT=36),
            'android.content.ContentValues': Mock(),
            'android.provider.MediaStore$Images$Media': Mock(),
            'android.content.Intent': intent_class,
            'android.content.ClipData': Mock(),
        }
        bridge = Mock(autoclass=lambda name: classes[name], cast=Mock(return_value=parcelable))
        with patch.dict('sys.modules', {'jnius': bridge}):
            camera.take_photo()
        bridge.cast.assert_called_once_with('android.os.Parcelable', uri)
        intent.putExtra.assert_called_once_with('output', parcelable)
        activity.startActivityForResult.assert_called_once_with(intent, camera.CAMERA)
        camera.on_error.assert_not_called()

    def test_camera_setup_failure_is_reported(self):
        camera = AndroidInput.__new__(AndroidInput)
        camera.camera_path = None
        camera.on_error = Mock()
        with patch.dict('sys.modules', {'jnius': Mock(autoclass=Mock(side_effect=RuntimeError('camera unavailable')))}):
            camera.take_photo()
        camera.on_error.assert_called_once()

    def test_large_jpeg_is_downsampled_before_orientation_copy(self):
        from PIL import ImageOps
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'photo.jpg'
            Image.new('RGB', (8000, 6000), 'blue').save(path)
            sizes = []
            transpose = ImageOps.exif_transpose
            def inspect(image):
                sizes.append(image.size)
                return transpose(image)
            with patch('talkapp.client.ImageOps.exif_transpose', side_effect=inspect):
                value = image_data(path)
            self.assertLessEqual(max(sizes[0]), 3200)
            import base64
            with Image.open(io.BytesIO(base64.b64decode(value.split(',', 1)[1]))) as result:
                self.assertLessEqual(max(result.size), 1600)


if __name__ == '__main__':
    unittest.main()
