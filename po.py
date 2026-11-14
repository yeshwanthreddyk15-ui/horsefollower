import ctypes
import json
import math
import os
import queue
import sys
import threading
from pathlib import Path
from ctypes import wintypes

import pygame
import tkinter as tk

if sys.platform != "win32":
    raise RuntimeError("The desktop overlay currently requires Windows.")

FRAME_WIDTH, FRAME_HEIGHT = 300, 240
BASE_SPRITE_WIDTH, BASE_SPRITE_HEIGHT = 120, 96
MIN_SIZE_PERCENT, MAX_SIZE_PERCENT = 50, 200
DEFAULT_SIZE_PERCENT = 100
DEFAULT_FOLLOW_SPEED = 360
settings_directory = Path(
    os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
) / "HorsePointerOverlay"
settings_path = settings_directory / "settings.json"


def load_settings():
    settings = {
        "size_percent": DEFAULT_SIZE_PERCENT,
        "follow_speed": DEFAULT_FOLLOW_SPEED,
    }
    try:
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return settings
    except (OSError, json.JSONDecodeError) as error:
        print(f"Could not load overlay settings: {error}", file=sys.stderr)
        return settings

    if not isinstance(saved, dict):
        print("Could not load overlay settings: expected a JSON object.", file=sys.stderr)
        return settings

    size_percent = saved.get("size_percent", DEFAULT_SIZE_PERCENT)
    if type(size_percent) is int:
        size_percent = min(
            MAX_SIZE_PERCENT,
            max(MIN_SIZE_PERCENT, round(size_percent / 5) * 5),
        )
        settings["size_percent"] = size_percent
    else:
        print("Ignoring invalid saved sticker size.", file=sys.stderr)

    follow_speed = saved.get("follow_speed", DEFAULT_FOLLOW_SPEED)
    if type(follow_speed) is int:
        follow_speed = min(900, max(60, round((follow_speed - 60) / 30) * 30 + 60))
        settings["follow_speed"] = follow_speed
    else:
        print("Ignoring invalid saved follow speed.", file=sys.stderr)
    return settings


saved_settings = load_settings()
SPRITE_WIDTH = round(
    BASE_SPRITE_WIDTH * saved_settings["size_percent"] / 100
)
SPRITE_HEIGHT = round(
    BASE_SPRITE_HEIGHT * saved_settings["size_percent"] / 100
)
OVERLAY_SIZE = math.ceil(
    math.hypot(
        BASE_SPRITE_WIDTH * MAX_SIZE_PERCENT / 100,
        BASE_SPRITE_HEIGHT * MAX_SIZE_PERCENT / 100,
    )
)
FOLLOW_SPEED = saved_settings["follow_speed"]
ANIMATION_FPS = 24
ANIMATION_FRAME_COUNT = 48
ATLAS_COLUMNS = 8

WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
GWL_EXSTYLE = -20
HWND_TOPMOST = ctypes.c_void_p(-1)
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
SPI_GETWORKAREA = 0x0030


class Size(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class BlendFunction(ctypes.Structure):
    _fields_ = [
        ("BlendOp", wintypes.BYTE),
        ("BlendFlags", wintypes.BYTE),
        ("SourceConstantAlpha", wintypes.BYTE),
        ("AlphaFormat", wintypes.BYTE),
    ]


class BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class RGBQuad(ctypes.Structure):
    _fields_ = [
        ("rgbBlue", wintypes.BYTE),
        ("rgbGreen", wintypes.BYTE),
        ("rgbRed", wintypes.BYTE),
        ("rgbReserved", wintypes.BYTE),
    ]


class BitmapInfo(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BitmapInfoHeader),
        ("bmiColors", RGBQuad * 1),
    ]


class Message(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.SystemParametersInfoW.argtypes = [
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(Rect),
    wintypes.UINT,
]
user32.SystemParametersInfoW.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND,
    wintypes.HDC,
    ctypes.POINTER(wintypes.POINT),
    ctypes.POINTER(Size),
    wintypes.HDC,
    ctypes.POINTER(wintypes.POINT),
    wintypes.COLORREF,
    ctypes.POINTER(BlendFunction),
    wintypes.DWORD,
]
user32.UpdateLayeredWindow.restype = wintypes.BOOL
user32.RegisterHotKey.argtypes = [
    wintypes.HWND,
    ctypes.c_int,
    wintypes.UINT,
    wintypes.UINT,
]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [
    ctypes.POINTER(Message),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
user32.GetMessageW.restype = ctypes.c_int
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.PostThreadMessageW.argtypes = [
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.PostThreadMessageW.restype = wintypes.BOOL

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC,
    ctypes.POINTER(BitmapInfo),
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.HANDLE,
    wintypes.DWORD,
]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL


pygame.init()
atlas_path = Path(__file__).with_name("horse_gallop.png")
gallop_atlas = pygame.image.load(str(atlas_path))
rider_source_frames = [
    gallop_atlas.subsurface(
        (
            (index % ATLAS_COLUMNS) * FRAME_WIDTH,
            (index // ATLAS_COLUMNS) * FRAME_HEIGHT,
            FRAME_WIDTH,
            FRAME_HEIGHT,
        )
    ).copy()
    for index in range(ANIMATION_FRAME_COUNT)
]
rider_frames = [
    pygame.transform.smoothscale(
        frame, (SPRITE_WIDTH, SPRITE_HEIGHT)
    )
    for frame in rider_source_frames
]

root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
root.geometry(f"{OVERLAY_SIZE}x{OVERLAY_SIZE}+0+0")
root.configure(bg="black")
root.deiconify()
root.update_idletasks()
window_handle = user32.GetParent(wintypes.HWND(root.winfo_id()))
if not window_handle:
    window_handle = wintypes.HWND(root.winfo_id())

extended_style = user32.GetWindowLongW(window_handle, GWL_EXSTYLE)
ctypes.set_last_error(0)
previous_style = user32.SetWindowLongW(
    window_handle,
    GWL_EXSTYLE,
    extended_style
    | WS_EX_LAYERED
    | WS_EX_TRANSPARENT
    | WS_EX_TOOLWINDOW
    | WS_EX_NOACTIVATE,
)
if not previous_style and ctypes.get_last_error():
    raise ctypes.WinError(ctypes.get_last_error())
if not user32.SetWindowPos(
    window_handle,
    HWND_TOPMOST,
    0,
    0,
    OVERLAY_SIZE,
    OVERLAY_SIZE,
    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
):
    raise ctypes.WinError(ctypes.get_last_error())

screen_dc = user32.GetDC(None)
if not screen_dc:
    raise ctypes.WinError(ctypes.get_last_error())

memory_dc = gdi32.CreateCompatibleDC(screen_dc)
if not memory_dc:
    user32.ReleaseDC(None, screen_dc)
    raise ctypes.WinError(ctypes.get_last_error())

bitmap_info = BitmapInfo()
bitmap_info.bmiHeader.biSize = ctypes.sizeof(BitmapInfoHeader)
bitmap_info.bmiHeader.biWidth = OVERLAY_SIZE
bitmap_info.bmiHeader.biHeight = -OVERLAY_SIZE
bitmap_info.bmiHeader.biPlanes = 1
bitmap_info.bmiHeader.biBitCount = 32
bitmap_info.bmiHeader.biCompression = 0
pixel_bits = ctypes.c_void_p()
dib_bitmap = gdi32.CreateDIBSection(
    screen_dc,
    ctypes.byref(bitmap_info),
    0,
    ctypes.byref(pixel_bits),
    None,
    0,
)
if not dib_bitmap or not pixel_bits.value:
    gdi32.DeleteDC(memory_dc)
    user32.ReleaseDC(None, screen_dc)
    raise ctypes.WinError(ctypes.get_last_error())
previous_bitmap = gdi32.SelectObject(memory_dc, dib_bitmap)
if not previous_bitmap:
    gdi32.DeleteObject(dib_bitmap)
    gdi32.DeleteDC(memory_dc)
    user32.ReleaseDC(None, screen_dc)
    raise ctypes.WinError(ctypes.get_last_error())

overlay_surface = pygame.Surface(
    (OVERLAY_SIZE, OVERLAY_SIZE), pygame.SRCALPHA, 32
)
overlay_size = Size(OVERLAY_SIZE, OVERLAY_SIZE)
source_point = wintypes.POINT(0, 0)
blend_function = BlendFunction(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
following = True
going_home = False
at_home = False
closing = False
facing_angle = 0.0
gallop_time = 0.0
last_cursor = wintypes.POINT()
if not user32.GetCursorPos(ctypes.byref(last_cursor)):
    raise ctypes.WinError(ctypes.get_last_error())
follower_x = float(last_cursor.x)
follower_y = float(last_cursor.y)
previous_tick = pygame.time.get_ticks()


def update_overlay(center_x, center_y, frame_index, angle, visible=True):
    overlay_surface.fill((0, 0, 0, 0))
    if visible:
        rotated_frame = pygame.transform.rotate(
            rider_frames[frame_index], -math.degrees(angle)
        )
        overlay_surface.blit(
            rotated_frame,
            rotated_frame.get_rect(
                center=(OVERLAY_SIZE // 2, OVERLAY_SIZE // 2)
            ),
        )

    pixels = pygame.image.tobytes(
        overlay_surface.premul_alpha(), "BGRA", False
    )
    ctypes.memmove(pixel_bits, bytes(pixels), len(pixels))

    destination = wintypes.POINT(
        round(center_x - OVERLAY_SIZE / 2),
        round(center_y - OVERLAY_SIZE / 2),
    )
    if not user32.UpdateLayeredWindow(
        window_handle,
        screen_dc,
        ctypes.byref(destination),
        ctypes.byref(overlay_size),
        memory_dc,
        ctypes.byref(source_point),
        0,
        ctypes.byref(blend_function),
        ULW_ALPHA,
    ):
        raise ctypes.WinError(ctypes.get_last_error())


hotkey_events = queue.Queue()
hotkey_thread_id = 0


def listen_for_hotkeys():
    global hotkey_thread_id
    hotkey_thread_id = kernel32.GetCurrentThreadId()
    registered_ids = []
    hotkeys = ((1, ord("A")), (2, ord("F")), (3, ord("Q")))
    for hotkey_id, key in hotkeys:
        if not user32.RegisterHotKey(
            None,
            hotkey_id,
            MOD_CONTROL | MOD_ALT | MOD_NOREPEAT,
            key,
        ):
            hotkey_events.put(("error", ctypes.WinError(ctypes.get_last_error())))
        else:
            registered_ids.append(hotkey_id)
    if registered_ids:
        hotkey_events.put(("ready", None))
        message = Message()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == WM_HOTKEY:
                hotkey_events.put(("hotkey", message.wParam))

    for hotkey_id in registered_ids:
        user32.UnregisterHotKey(None, hotkey_id)


hotkey_thread = threading.Thread(target=listen_for_hotkeys, daemon=True)
hotkey_thread.start()


def update_follow_status():
    if going_home:
        state = "Going to stable"
    elif at_home:
        state = "At stable"
    else:
        state = "Following" if following else "Stopped"
    follow_status_label.configure(text=state)


def set_following(enabled):
    global following, going_home, at_home
    following = enabled
    going_home = False
    if enabled:
        at_home = False
    update_follow_status()


def send_horse_home():
    global following, going_home, at_home
    following = False
    going_home = True
    at_home = False
    update_follow_status()


def set_rider_size(value):
    global SPRITE_WIDTH, SPRITE_HEIGHT
    size_percent = int(float(value))
    SPRITE_WIDTH = round(BASE_SPRITE_WIDTH * size_percent / 100)
    SPRITE_HEIGHT = round(BASE_SPRITE_HEIGHT * size_percent / 100)
    rider_frames[:] = [
        pygame.transform.smoothscale(
            frame, (SPRITE_WIDTH, SPRITE_HEIGHT)
        )
        for frame in rider_source_frames
    ]
    size_value_label.configure(text=f"Sticker size: {size_percent}%")
    schedule_settings_save()


def set_follow_speed(value):
    global FOLLOW_SPEED
    FOLLOW_SPEED = int(float(value))
    speed_value_label.configure(text=f"Follow speed: {FOLLOW_SPEED} px/s")
    schedule_settings_save()


pending_settings_save = None


def save_settings():
    global pending_settings_save
    pending_settings_save = None
    temporary_path = settings_path.with_suffix(".tmp")
    try:
        settings_directory.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps(
                {
                    "size_percent": round(SPRITE_WIDTH * 100 / BASE_SPRITE_WIDTH),
                    "follow_speed": FOLLOW_SPEED,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary_path.replace(settings_path)
    except OSError as error:
        print(f"Could not save overlay settings: {error}", file=sys.stderr)


def schedule_settings_save():
    global pending_settings_save
    if pending_settings_save is not None:
        root.after_cancel(pending_settings_save)
    pending_settings_save = root.after(300, save_settings)


def flush_settings():
    global pending_settings_save
    if pending_settings_save is not None:
        root.after_cancel(pending_settings_save)
        pending_settings_save = None
    save_settings()


controls = tk.Toplevel(root)
controls.title("Horse Pointer Controls")
controls.attributes("-topmost", True)
controls.resizable(False, False)
controls.configure(bg="#20252b")

panel = tk.Frame(controls, bg="#20252b", padx=12, pady=8)
panel.pack(fill="both", expand=True)
tk.Label(
    panel,
    text="Horse Pointer",
    fg="white",
    bg="#20252b",
    font=("Segoe UI", 11, "bold"),
).pack(anchor="w")
follow_status_label = tk.Label(panel, text="Following", fg="#9fe3a5", bg="#20252b")
follow_status_label.pack(anchor="w")

size_value_label = tk.Label(
    panel,
    text=f"Sticker size: {saved_settings['size_percent']}%",
    fg="white",
    bg="#20252b",
)
size_value_label.pack(anchor="w", pady=(6, 0))
size_slider = tk.Scale(
    panel,
    from_=MIN_SIZE_PERCENT,
    to=MAX_SIZE_PERCENT,
    orient="horizontal",
    resolution=5,
    showvalue=False,
    command=set_rider_size,
    bg="#20252b",
    fg="white",
    troughcolor="#46515c",
    highlightthickness=0,
    length=270,
)
size_slider.set(saved_settings["size_percent"])
size_slider.pack(fill="x")

speed_value_label = tk.Label(
    panel, text=f"Follow speed: {FOLLOW_SPEED} px/s", fg="white", bg="#20252b"
)
speed_value_label.pack(anchor="w", pady=(4, 0))
speed_slider = tk.Scale(
    panel,
    from_=60,
    to=900,
    orient="horizontal",
    resolution=30,
    showvalue=False,
    command=set_follow_speed,
    bg="#20252b",
    fg="white",
    troughcolor="#46515c",
    highlightthickness=0,
    length=270,
)
speed_slider.set(FOLLOW_SPEED)
speed_slider.pack(fill="x")

button_row = tk.Frame(panel, bg="#20252b")
button_row.pack(fill="x", pady=(8, 2))
tk.Button(
    button_row,
    text="Start",
    command=lambda: set_following(True),
    width=10,
).pack(side="left", padx=(0, 6))
tk.Button(
    button_row,
    text="Stop",
    command=lambda: set_following(False),
    width=10,
).pack(side="left", padx=(0, 6))
tk.Button(
    button_row,
    text="Home",
    command=send_horse_home,
    width=10,
).pack(side="left")
tk.Button(
    panel,
    text="Quit Horse Pointer",
    command=lambda: stop_overlay(),
    width=18,
).pack(anchor="w", pady=(6, 0))
tk.Label(
    panel,
    text="Ctrl+Alt+A: stop   Ctrl+Alt+F: start   Ctrl+Alt+Q: quit",
    fg="#c7cbd1",
    bg="#20252b",
    font=("Segoe UI", 8),
).pack(anchor="w", pady=(6, 0))
controls.update_idletasks()
screen_height = user32.GetSystemMetrics(1)
controls.geometry(
    f"+12+{max(0, screen_height - controls.winfo_height() - 48)}"
)
controls.protocol("WM_DELETE_WINDOW", lambda: stop_overlay())

work_area = Rect()
if not user32.SystemParametersInfoW(
    SPI_GETWORKAREA, 0, ctypes.byref(work_area), 0
):
    raise ctypes.WinError(ctypes.get_last_error())
stable_width, stable_height = 108, 88
stable_x = max(work_area.left, work_area.right - stable_width - 18)
stable_y = max(work_area.top, work_area.bottom - stable_height - 18)
home_x = stable_x + 54
home_y = stable_y + 61
stable = tk.Toplevel(root)
stable.overrideredirect(True)
stable.attributes("-topmost", True)
stable.attributes("-transparentcolor", "#00ff00")
stable.geometry(
    f"{stable_width}x{stable_height}+{stable_x}+{stable_y}"
)
stable_canvas = tk.Canvas(
    stable,
    width=stable_width,
    height=stable_height,
    bg="#00ff00",
    highlightthickness=0,
)
stable_canvas.pack()
stable_canvas.create_polygon(
    11, 37, 54, 6, 97, 37,
    fill="#9b4935",
    outline="#542b25",
    width=2,
)
stable_canvas.create_rectangle(
    20, 36, 89, 80,
    fill="#dfbd83",
    outline="#704f37",
    width=2,
)
stable_canvas.create_rectangle(
    39, 43, 69, 80,
    fill="#573b2d",
    outline="#35271f",
    width=2,
)
stable_canvas.create_line(
    54, 44, 54, 79,
    fill="#c39b68",
    width=2,
)
stable_canvas.create_rectangle(
    37, 33, 71, 42,
    fill="#f3e5c7",
    outline="#704f37",
    width=1,
)
stable_canvas.create_text(
    54, 37,
    text="STABLE",
    fill="#35271f",
    font=("Segoe UI", 7, "bold"),
)
stable_handle = user32.GetParent(wintypes.HWND(stable.winfo_id()))
if not stable_handle:
    stable_handle = wintypes.HWND(stable.winfo_id())
stable_style = user32.GetWindowLongW(stable_handle, GWL_EXSTYLE)
user32.SetWindowLongW(
    stable_handle,
    GWL_EXSTYLE,
    stable_style | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
)
if not user32.SetWindowPos(
    stable_handle,
    HWND_TOPMOST,
    stable_x,
    stable_y,
    stable_width,
    stable_height,
    SWP_NOACTIVATE | SWP_SHOWWINDOW,
):
    raise ctypes.WinError(ctypes.get_last_error())
if not user32.SetWindowPos(
    window_handle,
    HWND_TOPMOST,
    0,
    0,
    OVERLAY_SIZE,
    OVERLAY_SIZE,
    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
):
    raise ctypes.WinError(ctypes.get_last_error())


def stop_overlay():
    global closing
    if closing:
        return
    closing = True
    flush_settings()
    if stable.winfo_exists():
        stable.destroy()
    if controls.winfo_exists():
        controls.destroy()
    root.quit()
    if root.winfo_exists():
        root.destroy()


def poll_hotkeys():
    global following, going_home, at_home, facing_angle, follower_x, follower_y
    global gallop_time
    global previous_tick
    while True:
        try:
            event_type, value = hotkey_events.get_nowait()
        except queue.Empty:
            break
        if event_type == "hotkey":
            if value == 1:
                set_following(False)
            elif value == 2:
                set_following(True)
            elif value == 3:
                stop_overlay()
                return
        elif event_type == "error":
            print(f"Could not register desktop hotkeys: {value}", file=sys.stderr)

    cursor = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(cursor)):
        raise ctypes.WinError(ctypes.get_last_error())
    now = pygame.time.get_ticks()
    delta_time = min((now - previous_tick) / 1000, 0.05)
    target_x = home_x if going_home else cursor.x
    target_y = home_y if going_home else cursor.y
    dx = target_x - follower_x
    dy = target_y - follower_y
    distance = math.hypot(dx, dy)
    distance_moved = 0.0
    if (following or going_home) and distance > 0:
        facing_angle = math.atan2(dy, dx)
        max_step = FOLLOW_SPEED * delta_time
        distance_moved = min(distance, max_step)
        if distance <= max_step:
            follower_x = float(target_x)
            follower_y = float(target_y)
            if going_home:
                going_home = False
                at_home = True
                update_follow_status()
        else:
            follower_x += dx / distance * max_step
            follower_y += dy / distance * max_step

    is_moving = (following or going_home) and distance_moved > 0.01
    if is_moving:
        gallop_time = (gallop_time + delta_time) % (
            ANIMATION_FRAME_COUNT / ANIMATION_FPS
        )
    else:
        gallop_time = 0.0
    frame_index = int(gallop_time * ANIMATION_FPS) % ANIMATION_FRAME_COUNT
    update_overlay(
        follower_x,
        follower_y,
        frame_index,
        facing_angle,
        visible=not at_home,
    )
    previous_tick = now
    root.after(16, poll_hotkeys)


def cleanup():
    flush_settings()
    if hotkey_thread_id:
        user32.PostThreadMessageW(hotkey_thread_id, WM_QUIT, 0, 0)
        hotkey_thread.join(timeout=1)
    gdi32.SelectObject(memory_dc, previous_bitmap)
    gdi32.DeleteObject(dib_bitmap)
    gdi32.DeleteDC(memory_dc)
    user32.ReleaseDC(None, screen_dc)
    pygame.quit()


try:
    update_overlay(last_cursor.x, last_cursor.y, 0, facing_angle)
    root.after(16, poll_hotkeys)
    root.mainloop()
finally:
    cleanup()
