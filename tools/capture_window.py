import ctypes
from pathlib import Path
from PIL import ImageGrab

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
hwnd = user32.FindWindowW(None, 'TalkApp')
if not hwnd:
    raise SystemExit('TalkApp window not found')
user32.ShowWindow(hwnd, 9)
user32.SetForegroundWindow(hwnd)
import time
time.sleep(.5)
rect = (ctypes.c_long * 4)()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
target = Path(__file__).resolve().parents[1] / 'window-preview.png'
ImageGrab.grab(bbox=tuple(rect)).save(target)
print(target)
