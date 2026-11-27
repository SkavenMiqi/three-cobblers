"""Live Android QR preview; frames never leave memory."""
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from .pairing_qr import decode_luminance


def request_camera(ready, denied):
    from android.permissions import Permission, check_permission, request_permissions

    def checked(*_):
        (ready if check_permission(Permission.CAMERA) else denied)()

    if check_permission(Permission.CAMERA):
        ready()
    else:
        request_permissions([Permission.CAMERA], lambda *_: Clock.schedule_once(checked))


def scan_qr(prefix, found, failed):
    from .ui import button, label

    def open_preview():
        from kivy.uix.camera import Camera
        from jnius import autoclass

        try:
            hardware = autoclass('android.hardware.Camera')
            info = autoclass('android.hardware.Camera$CameraInfo')()
            rear = 0
            for index in range(hardware.getNumberOfCameras()):
                hardware.getCameraInfo(index, info)
                if info.facing == info.CAMERA_FACING_BACK:
                    rear = index
                    break
            camera = Camera(index=rear, resolution=(640, 480), play=True)
        except Exception:
            failed('无法启动相机，请确认相机未被其他应用占用。')
            return
        panel = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(8))
        dialog = Popup(title='扫描 Harness 二维码', content=panel, size_hint=(.96, .9))
        panel.add_widget(label('对准电脑上的二维码，识别后自动连接。', size_hint_y=None, height=dp(44)))
        panel.add_widget(camera)
        panel.add_widget(button('取消', dialog.dismiss, size_hint_y=None, height=dp(44)))
        app = App.get_running_app()

        def read(_):
            try:
                backend = camera._camera
                frame = backend.grab_frame()
                if frame is None:
                    return
                width, height = backend.resolution
                code = decode_luminance(frame[:width * height], width, height, prefix=prefix)
            except Exception:
                return
            dialog.dismiss()
            found(code)

        tick = Clock.schedule_interval(read, .3)

        def pause(*_):
            dialog.dismiss()

        def close(*_):
            tick.cancel()
            app.unbind(on_pause=pause)
            try:
                camera.play = False
            finally:
                camera.index = -1

        app.bind(on_pause=pause)
        dialog.bind(on_dismiss=close)
        dialog.open()

    request_camera(open_preview, lambda: failed('请允许相机权限后再扫码。'))
