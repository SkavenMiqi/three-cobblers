"""Verify the loaded SDL instance has native IME candidate UI enabled."""
import ctypes
import os
import sys
from pathlib import Path

if sys.platform != 'win32':
    raise SystemExit('Windows only')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop('SDL_IME_SHOW_UI', None)
import main

kernel = ctypes.WinDLL('kernel32')
kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
kernel.GetModuleHandleW.restype = ctypes.c_void_p
module = kernel.GetModuleHandleW('SDL2.dll')
assert module, 'Kivy did not load SDL2'
sdl = ctypes.CDLL('SDL2.dll', handle=module)
sdl.SDL_GetHint.argtypes = [ctypes.c_char_p]
sdl.SDL_GetHint.restype = ctypes.c_char_p
hint = sdl.SDL_GetHint(b'SDL_IME_SHOW_UI')
assert hint == b'1', f'Native Windows IME UI is not enabled: {hint!r}'
print('WINDOWS_IME_HINT_OK')
