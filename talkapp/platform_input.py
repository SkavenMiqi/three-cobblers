"""Android system photo picker and speech-to-text (no cloud audio API required)."""
from pathlib import Path
import uuid


class AndroidInput:
    IMAGE = 8101
    VOICE = 8102
    DOCUMENT = 8103
    BACKUP = 8104
    CAMERA = 8105

    def __init__(self, on_image, on_voice, on_error, on_document=None, on_backup=None):
        from android import activity
        self.on_image, self.on_voice, self.on_error = on_image, on_voice, on_error
        self.on_document = on_document
        self.on_backup = on_backup
        self.camera_path = None
        self.camera_callback = None
        activity.bind(on_activity_result=self.result)

    def pick_image(self):
        from jnius import autoclass
        intent = autoclass("android.content.Intent")("android.intent.action.GET_CONTENT")
        intent.setType("image/*")
        intent.addCategory("android.intent.category.OPENABLE")
        autoclass("org.kivy.android.PythonActivity").mActivity.startActivityForResult(intent, self.IMAGE)

    def voice(self):
        try:
            from jnius import autoclass
            intent = autoclass("android.content.Intent")("android.speech.action.RECOGNIZE_SPEECH")
            intent.putExtra("android.speech.extra.LANGUAGE_MODEL", "free_form")
            intent.putExtra("android.speech.extra.LANGUAGE", "zh-CN")
            intent.putExtra("android.speech.extra.PROMPT", "说完后可编辑，再发送")
            autoclass("org.kivy.android.PythonActivity").mActivity.startActivityForResult(intent, self.VOICE)
        except Exception:
            self.on_error('此手机未提供系统语音识别，请用键盘语音输入或手动输入')

    def pick_document(self):
        from jnius import autoclass
        intent = autoclass('android.content.Intent')('android.intent.action.GET_CONTENT')
        intent.setType('*/*')
        intent.addCategory('android.intent.category.OPENABLE')
        autoclass('org.kivy.android.PythonActivity').mActivity.startActivityForResult(intent, self.DOCUMENT)

    def pick_backup(self):
        from jnius import autoclass
        intent = autoclass('android.content.Intent')('android.intent.action.GET_CONTENT')
        intent.setType('*/*')
        intent.addCategory('android.intent.category.OPENABLE')
        autoclass('org.kivy.android.PythonActivity').mActivity.startActivityForResult(intent, self.BACKUP)

    def take_photo(self, callback=None):
        # MediaStore URI grants the camera write access without exposing file://.
        if self.camera_path is not None:
            return
        try:
            from jnius import autoclass, cast
            activity = autoclass('org.kivy.android.PythonActivity').mActivity
            if autoclass('android.os.Build$VERSION').SDK_INT < 29:
                self.on_error('此拍照入口需Android 10及以上；可先用系统相机拍摄，再从相册选择')
                return
            values = autoclass('android.content.ContentValues')()
            values.put('_display_name', 'TalkApp-' + uuid.uuid4().hex + '.jpg')
            values.put('mime_type', 'image/jpeg')
            media = autoclass('android.provider.MediaStore$Images$Media')
            self.camera_path = activity.getContentResolver().insert(media.EXTERNAL_CONTENT_URI, values)
            if self.camera_path is None:
                raise ValueError('无法创建照片')
            self.camera_callback = callback
            intent = autoclass('android.content.Intent')('android.media.action.IMAGE_CAPTURE')
            intent.putExtra('output', cast('android.os.Parcelable', self.camera_path))
            intent.setClipData(autoclass('android.content.ClipData').newRawUri('photo', self.camera_path))
            intent.addFlags(3)
            activity.startActivityForResult(intent, self.CAMERA)
        except Exception:
            self.clear_camera()
            self.on_error('无法打开相机，请检查系统相机是否可用，或拍摄后从相册选择')

    def clear_camera(self):
        uri, self.camera_path = self.camera_path, None
        self.camera_callback = None
        if uri is not None:
            try:
                from jnius import autoclass
                activity = autoclass('org.kivy.android.PythonActivity').mActivity
                activity.getContentResolver().delete(uri, None, None)
            except Exception:
                pass

    def result(self, request, status, intent):
        if request not in (self.IMAGE, self.VOICE, self.DOCUMENT, self.BACKUP, self.CAMERA):
            return
        if request == self.CAMERA and status != -1 and self.camera_path:
            self.clear_camera()
        if status != -1 or (intent is None and request != self.CAMERA):
            return
        try:
            if request == self.VOICE:
                values = intent.getStringArrayListExtra("android.speech.extra.RESULTS")
                if values and values.size():
                    self.on_voice(str(values.get(0)))
            else:
                from jnius import autoclass
                from .storage import data_dir
                activity = autoclass("org.kivy.android.PythonActivity").mActivity
                uri = self.camera_path if request == self.CAMERA else intent.getData()
                stream = activity.getContentResolver().openInputStream(uri)
                suffix = '.image'
                if request in (self.DOCUMENT, self.BACKUP):
                    cursor = activity.getContentResolver().query(uri, None, None, None, None)
                    try:
                        if cursor and cursor.moveToFirst():
                            name = str(cursor.getString(cursor.getColumnIndex('_display_name')))
                            suffix = Path(name).suffix.lower()
                    finally:
                        if cursor:
                            cursor.close()
                target = data_dir() / (uuid.uuid4().hex + suffix)
                try:
                    # Keep byte transfer on the Java side: Python bytearray output
                    # parameters are unreliable across some pyjnius versions.
                    source = autoclass("java.nio.channels.Channels").newChannel(stream)
                    output = autoclass("java.io.FileOutputStream")(str(target))
                    channel = output.getChannel()
                    total = 0
                    try:
                        while True:
                            count = channel.transferFrom(source, total, 65536)
                            if count <= 0:
                                break
                            total += count
                            maximum = 512 if request == self.BACKUP else 20
                            if total > maximum * 1024 * 1024:
                                raise ValueError('文件过大')
                    finally:
                        output.close()
                    if request == self.DOCUMENT:
                        self.on_document(str(target))
                    elif request == self.BACKUP:
                        self.on_backup(str(target))
                    elif request == self.CAMERA and self.camera_callback:
                        self.camera_callback(str(target))
                    else:
                        self.on_image(str(target))
                finally:
                    stream.close()
                    target.unlink(missing_ok=True)
                    if request == self.CAMERA and self.camera_path:
                        self.clear_camera()
        except Exception:
            if request == self.CAMERA:
                self.clear_camera()
            self.on_error("无法读取图片或语音结果，请重新选择（图片不超过 20 MB）")

    def close(self):
        from android import activity
        activity.unbind(on_activity_result=self.result)
