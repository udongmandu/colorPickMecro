import tkinter as tk
import sys
import os
import time
import ctypes
import threading
import pyautogui
from tkinter import colorchooser
import mss
from PIL import Image
import keyboard  # pip install keyboard

ctypes.windll.user32.SetProcessDPIAware()

class Overlay(tk.Tk):
    def __init__(self, x, y, width, height,
                 border_color="blue", border_width=4,
                 transparency_color="white", title="이길 수 없다면 합류하라"):
        super().__init__()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.config(bg=transparency_color)
        self.attributes("-transparentcolor", transparency_color)
        self.geometry(f"{width}x{height}+{x}+{y}")

        self.width, self.height = width, height
        self.title_bar_height = 40
        self.border_color = border_color
        self.border_width = border_width
        self.resize_border = 8

        self.target_color = (255, 0, 0)
        self.second_click_pos = (x + width // 2, y + height // 2)
        self.panel_width = 275
        self.interval = 0.1
        self.tolerance = 40
        self.running = False

        # 반복 클릭 관련 변수
        self.repeat_pos = (x + width // 2, y + height // 2)
        self.repeat_on = False
        self.repeat_interval = 1.0
        self._repeat_job = None

        self._make_title_bar(title)
        self._make_canvas()
        self._make_control_panel()

        # 전역 키 핸들러 (tk window용)
        self.bind_all('<Key>', self.global_key_handler)

        # 시스템 전역 단축키 (PageUp/CTRL+Q) - 별도 스레드에서 등록
        threading.Thread(target=self._register_global_hotkeys, daemon=True).start()

    # =========================== HOTKEYS 등록 ============================
    def _register_global_hotkeys(self):
        keyboard.add_hotkey('page up', self._toggle_repeat_from_global)
        keyboard.add_hotkey('ctrl+q', self._emergency_stop_from_global)

    def _toggle_repeat_from_global(self):
        # tkinter 루프 안전 호출
        self.after(0, self._toggle_repeat_noevent)

    def _toggle_repeat_noevent(self):
        if not self.running:
            self.repeat_on = False
            self._stop_repeat_click()
            self._update_btn_colors()
            return
        self.repeat_on = not self.repeat_on
        self._update_btn_colors()
        if self.repeat_on:
            self._start_repeat_click()
        else:
            self._stop_repeat_click()

    def _emergency_stop_from_global(self):
        # 색감지 멈추고 반복 멈춤
        self.after(0, self._emergency_stop)

    def _emergency_stop(self):
        self.running = False
        self.repeat_on = False
        self._stop_repeat_click()
        self._update_btn_colors()
        print("<< 전체 중지 (Ctrl+Q)>>")

    # =========================== 컨트롤 패널, UI 부분 ============================
    def _make_title_bar(self, title):
        bar = tk.Frame(self, bg="#444")
        bar.pack(fill="x")
        bar.bind("<ButtonPress-1>", self.start_move)
        bar.bind("<B1-Motion>", self.on_move)
        tk.Label(
            bar,
            text=title,
            bg="#444",
            fg="#ffffff",
            font=("맑은 고딕", 12, "bold"),
            pady=4
        ).pack(side="left", padx=8)
        tk.Button(bar, text="✕", bg="#444", fg="white", bd=0,
                font=("맑은 고딕", 12),
                command=self.close_app)\
            .pack(side="right", padx=8)

    def _make_canvas(self):
        cw = self.width - self.panel_width
        ch = self.height - self.title_bar_height
        self.canvas = tk.Canvas(self,
                                width=cw,
                                height=ch,
                                bg="white",
                                highlightthickness=0)
        self.canvas.place(x=0, y=self.title_bar_height)
        self._draw_border()
        self.canvas.bind("<ButtonPress-1>", self.check_resize)
        self.canvas.bind("<B1-Motion>", self.perform_resize)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Leave>", lambda e: self.canvas.config(cursor="arrow"))

    def _make_control_panel(self):
        pw, ph = self.panel_width, self.height - self.title_bar_height
        self.panel = tk.Frame(self, bg="#f6f7fa", width=pw, height=ph, highlightbackground="#e1e2e3", highlightthickness=1)
        self.panel.place(x=self.width - pw, y=self.title_bar_height)

        # ── 버튼 프레임 (반복상태+start/stop) ──────────────────
        self.btn_frame = tk.Frame(self.panel, bg="#f6f7fa")
        self.btn_frame.pack(pady=(0,0), padx=10, fill="x")

        self.repeat_label = tk.Label(self.btn_frame, text="반복", width=4, font=("맑은 고딕", 10, "bold"),
                                    fg="white", bg="#fc4141")
        self.repeat_label.pack(side="left", padx=(0,7))

        self.start_btn = tk.Button(self.btn_frame, text="Start", command=self.start_monitor,
                                   bg="#42d784", fg="white", bd=0, relief="ridge", width=7)
        self.stop_btn  = tk.Button(self.btn_frame, text="Stop",  command=self.stop_monitor,
                                   bg="#dddddd", fg="#888888", bd=0, relief="ridge", width=7)
        self.start_btn.pack(side="left", padx=(0, 5))
        self.stop_btn.pack(side="left")
        self._update_btn_colors()

        # ── 반복 클릭 구간: 한 줄 (X Y 주기) ────────────────────────
        repeat_frame = tk.Frame(self.panel, bg="#f6f7fa")
        repeat_frame.pack(pady=(4, 0), padx=10, fill="x")
        tk.Label(repeat_frame, text="X", bg="#f6f7fa").grid(row=0, column=0)
        self.rep_x_var = tk.IntVar(value=self.repeat_pos[0])
        tk.Entry(repeat_frame, textvariable=self.rep_x_var, width=6, justify="center", bg="white").grid(row=0, column=1, padx=(0,3))
        tk.Label(repeat_frame, text="Y", bg="#f6f7fa").grid(row=0, column=2)
        self.rep_y_var = tk.IntVar(value=self.repeat_pos[1])
        tk.Entry(repeat_frame, textvariable=self.rep_y_var, width=6, justify="center", bg="white").grid(row=0, column=3, padx=(0,5))
        tk.Label(repeat_frame, text="주기(초)", bg="#f6f7fa").grid(row=0, column=4)
        self.repeat_interval_var = tk.DoubleVar(value=self.repeat_interval)
        tk.Entry(repeat_frame, textvariable=self.repeat_interval_var, width=6, justify="center", bg="white").grid(row=0, column=5)
        tk.Label(repeat_frame, text="(PageDown: 좌표, PageUp: On/Off)", bg="#f6f7fa", fg="#2167ce", font=("Segoe UI",8,"bold")).grid(row=1, column=0, columnspan=6, sticky="w", pady=(2,0))

        #------------ 중지 설명
        tol_frame = tk.Frame(self.panel, bg="#f6f7fa")
        tol_frame.pack(pady=8, padx=10, fill="x")
        row = tk.Frame(tol_frame, bg="#f6f7fa")
        row.pack(fill="x")
        tk.Label(tol_frame, text="반복은 시작 시에 ON 가능", bg="#f6f7fa", anchor="w", fg="#2167ce", font=("Segoe UI",8,"bold")).pack(anchor="w", pady=(2,0))
        tk.Label(tol_frame, text="Ctrl + Q : 강제 중지", bg="#f6f7fa", anchor="w", fg="#ff2a00").pack(anchor="w", pady=(2,0))

        # ── 나머지(구분선/색상/좌표/간격/허용오차 등) ────────────
        sep = tk.Frame(self.panel, height=2, bg="#e1e2e3")
        sep.pack(fill="x", pady=(12, 6), padx=4)
        color_frame = tk.Frame(self.panel, bg="#f6f7fa")
        color_frame.pack(pady=(16,8), padx=10, fill="x")
        tk.Label(color_frame, text="색상", bg="#f6f7fa", anchor="w").pack(side="left")
        self.preview = tk.Label(color_frame, bg=self._hex(), width=2, height=1, relief="solid", bd=1)
        self.preview.pack(side="left", padx=(8,3))
        self.hex_var = tk.StringVar(value=self._hex())
        self.hex_var.trace_add('write', self._on_hex_change)
        tk.Entry(color_frame, width=8, textvariable=self.hex_var, justify="center", font=("Consolas", 10), bg="white").pack(side="left", padx=(0, 3))
        tk.Button(color_frame, text="🎨", width=2, command=self._pick_color, bg="#eaf0fa", bd=0, relief="ridge").pack(side="left")
        tk.Label(color_frame, text="(HOME)", bg="#f6f7fa", fg="#2167ce", font=("Segoe UI",8,"bold")).pack(side="left", padx=(6,0))

        coord_frame = tk.Frame(self.panel, bg="#f6f7fa")
        coord_frame.pack(pady=8, padx=10, fill="x", )
        tk.Label(coord_frame, text="좌표", bg="#f6f7fa", anchor="w").pack(side="left")
        self.x_var = tk.IntVar(value=self.second_click_pos[0])
        self.y_var = tk.IntVar(value=self.second_click_pos[1])
        self.x_var.trace_add('write', lambda *a: self._update_second_click())
        self.y_var.trace_add('write', lambda *a: self._update_second_click())
        tk.Label(coord_frame, text="X", bg="#f6f7fa").pack(side="left", padx=(8,0))
        tk.Entry(coord_frame, width=6, textvariable=self.x_var, justify="center", bg="white").pack(side="left", padx=(0, 3))
        tk.Label(coord_frame, text="Y", bg="#f6f7fa").pack(side="left")
        tk.Entry(coord_frame, width=6, textvariable=self.y_var, justify="center", bg="white").pack(side="left", padx=(0, 3))
        tk.Label(coord_frame, text="(END)", bg="#f6f7fa", fg="#2167ce", font=("Segoe UI",8,"bold")).pack(side="left", padx=(2,0))

        interval_frame = tk.Frame(self.panel, bg="#f6f7fa")
        interval_frame.pack(pady=8, padx=10, fill="x")
        tk.Label(interval_frame, text="간격(초)", bg="#f6f7fa", anchor="w").pack(side="left")
        self.int_var = tk.DoubleVar(value=self.interval)
        self.int_var.trace_add('write', lambda *a: self._update_interval())
        tk.Entry(interval_frame, width=6, textvariable=self.int_var, justify="center", bg="white").pack(side="left", padx=(8,0))

        tol_frame = tk.Frame(self.panel, bg="#f6f7fa")
        tol_frame.pack(pady=8, padx=10, fill="x")
        row = tk.Frame(tol_frame, bg="#f6f7fa")
        row.pack(fill="x")
        tk.Label(row, text="허용오차", bg="#f6f7fa", anchor="w").pack(side="left")
        self.tol_var = tk.IntVar(value=self.tolerance)
        self.tol_var.trace_add('write', lambda *a: self._update_tolerance())
        tk.Entry(row, width=6, textvariable=self.tol_var, justify="center", bg="white").pack(side="left", padx=(8,0))
        tk.Label(tol_frame, text="80까지 정도만 추천", bg="#f6f7fa", anchor="w", fg="#2167ce").pack(anchor="w", pady=(2,0))
        tk.Label(tol_frame, text="배경이 투명이라 설정 바꿀 때\n숫자만 클릭 잘 해야함", bg="#f6f7fa", anchor="w", fg="#000000", justify="left").pack(anchor="w", pady=(2,0))

        # 바인딩 변수 연결
        self.rep_x_var.trace_add('write', lambda *a: self._update_repeat_pos())
        self.rep_y_var.trace_add('write', lambda *a: self._update_repeat_pos())
        self.repeat_interval_var.trace_add('write', lambda *a: self._update_repeat_interval())

    # =========== 기존 단축키 (윈도 내에서만 동작) ==========
    def global_key_handler(self, event):
        if event.keysym == 'End':
            self._capture_mouse_position(event)
            return "break"
        elif event.keysym == 'Home':
            self._capture_color_from_mouse(event)
            return "break"
        elif event.keysym == 'Next':
            self._set_repeat_pos(event)
            return "break"
        # elif event.keysym == 'Prior':
        #     self._toggle_repeat_by_key(event)
        #     return "break"

    # ========== UI 색 등 상태 업데이트 =============
    def _update_btn_colors(self):
        if self.running:
            self.start_btn.config(bg="#dddddd", fg="#888888", state="disabled", text="Start")
            self.stop_btn.config(bg="#fc4141", fg="white", state="normal", text="Stop")
        else:
            self.start_btn.config(bg="#42d784", fg="white", state="normal", text="Start")
            self.stop_btn.config(bg="#dddddd", fg="#888888", state="disabled", text="Stop")
        # 반복상태 색
        if self.repeat_on:
            self.repeat_label.config(bg="#42d784", fg="white", text="반복")
        else:
            self.repeat_label.config(bg="#fc4141", fg="white", text="반복")

    def _hex(self):
        return '#%02x%02x%02x' % self.target_color

    def _on_hex_change(self, *args):
        h = self.hex_var.get().lstrip('#')
        if len(h) == 6:
            try:
                r,g,b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
                self.target_color = (r,g,b)
                self.preview.config(bg=self._hex())
            except ValueError:
                pass

    def _update_tolerance(self):
        try:    self.tolerance = self.tol_var.get()
        except: pass

    def _update_second_click(self):
        try:    self.second_click_pos = (self.x_var.get(), self.y_var.get())
        except: pass

    def _update_interval(self):
        try:    self.interval = self.int_var.get()
        except: pass

    def _pick_color(self):
        try:
            c = colorchooser.askcolor(color=self._hex(), title="Choose...")[1]
            if c: self.hex_var.set(c)
        except: pass

    def _capture_mouse_position(self, e):
        x,y = pyautogui.position()
        self.x_var.set(x); self.y_var.set(y)

    def _capture_color_from_mouse(self, e):
        x, y = pyautogui.position()
        with mss.mss() as sct:
            mon = {"left": x, "top": y, "width": 1, "height": 1}
            sct_img = sct.grab(mon)
            img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
            r, g, b = img.getpixel((0, 0))
        color_hex = '#%02x%02x%02x' % (r, g, b)
        self.hex_var.set(color_hex)

    def _set_repeat_pos(self, e):
        x, y = pyautogui.position()
        self.rep_x_var.set(x)
        self.rep_y_var.set(y)
        self.repeat_pos = (x, y)

    # -------- PageUp 핫키로만 반복 on/off --------
    # 기존 tkinter 내 이벤트는 사용하지 않음

    def _update_repeat_pos(self, *args):
        try:
            self.repeat_pos = (self.rep_x_var.get(), self.rep_y_var.get())
        except: pass

    def _update_repeat_interval(self, *args):
        try:
            self.repeat_interval = self.repeat_interval_var.get()
        except: pass

    def _start_repeat_click(self):
        if not self.repeat_on or not self.running:
            return
        pyautogui.click(self.repeat_pos)
        self._repeat_job = self.after(int(self.repeat_interval * 1000), self._start_repeat_click)

    def _stop_repeat_click(self):
        if self._repeat_job:
            self.after_cancel(self._repeat_job)
            self._repeat_job = None

    def _draw_border(self):
        self.canvas.delete("all")
        cw = self.width - self.panel_width
        ch = self.height - self.title_bar_height
        self.canvas.create_rectangle(
            self.border_width//2,
            self.border_width//2,
            cw - self.border_width//2,
            ch - self.border_width//2,
            outline=self.border_color,
            width=self.border_width
        )

    def start_move(self, e):
        self._drag_x, self._drag_y = e.x, e.y
        self._resizing = False

    def on_move(self, e):
        if not getattr(self, "_resizing", False):
            self.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")
            if hasattr(self, "panel"):
                self.panel.place(x=self.width - self.panel_width, y=self.title_bar_height)

    def check_resize(self, e):
        x,y = e.x, e.y
        cw = self.width - self.panel_width
        ch = self.height - self.title_bar_height
        if x >= cw - self.resize_border and y >= ch - self.resize_border:
            self._resizing = True
            self._start_w, self._start_h = self.width, self.height
            self._start_x, self._start_y = e.x_root, e.y_root

    def perform_resize(self, e):
        if getattr(self, "_resizing", False):
            dx,dy = e.x_root - self._start_x, e.y_root - self._start_y
            nw = max(300, self._start_w + dx)
            nh = max(self.title_bar_height + 100, self._start_h + dy)
            self.width, self.height = nw, nh
            x0, y0 = self.winfo_rootx(), self.winfo_rooty()
            self.geometry(f"{nw}x{nh}+{x0}+{y0}")
            self.canvas.config(width=nw-self.panel_width,
                               height=nh-self.title_bar_height)
            self._draw_border()
            if hasattr(self, "panel"):
                self.panel.place(x=self.width - self.panel_width, y=self.title_bar_height)

    def on_motion(self, e):
        x,y = e.x, e.y
        cw = self.width - self.panel_width
        ch = self.height - self.title_bar_height
        if   x>=cw-self.resize_border and y>=ch-self.resize_border: c="size_nw_se"
        elif x>=cw-self.resize_border:                              c="size_we"
        elif y>=ch-self.resize_border:                              c="size_ns"
        else:                                                       c="arrow"
        self.canvas.config(cursor=c)

    # ---- 덩어리별 Blob 인식 & 중앙 클릭 ----
    def find_color_inside(self, color, tol=0):
        from collections import deque

        cx = self.canvas.winfo_rootx()
        cy = self.canvas.winfo_rooty()
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()

        with mss.mss() as sct:
            mon = {"left": cx, "top": cy, "width": cw, "height": ch}
            sct_img = sct.grab(mon)
            img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)

        pix = img.load()
        visited = [[False]*ch for _ in range(cw)]
        blobs = []

        border = self.border_width

        # 모든 색상 픽셀 방문, 그룹화(BFS)
        for i in range(border, cw - border):
            for j in range(border, ch - border):
                if visited[i][j]:
                    continue
                r, g, b = pix[i, j]
                if (abs(r - color[0]) <= tol and
                    abs(g - color[1]) <= tol and
                    abs(b - color[2]) <= tol):
                    queue = deque()
                    queue.append((i, j))
                    group = []
                    visited[i][j] = True
                    while queue:
                        x, y = queue.popleft()
                        group.append((x, y))
                        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                            nx, ny = x+dx, y+dy
                            if 0 <= nx < cw and 0 <= ny < ch and not visited[nx][ny]:
                                rr, gg, bb = pix[nx, ny]
                                if (abs(rr - color[0]) <= tol and
                                    abs(gg - color[1]) <= tol and
                                    abs(bb - color[2]) <= tol):
                                    queue.append((nx, ny))
                                    visited[nx][ny] = True
                    blobs.append(group)

        if not blobs:
            return None

        # 각 blob의 top-left(가장 위, 왼쪽)와 중앙좌표 구하기
        blob_infos = []
        for group in blobs:
            min_y = min(p[1] for p in group)
            lefts_in_min_y = [p[0] for p in group if p[1]==min_y]
            min_x = min(lefts_in_min_y)
            xs = [p[0] for p in group]
            ys = [p[1] for p in group]
            center_x = (min(xs) + max(xs)) // 2
            center_y = (min(ys) + max(ys)) // 2
            blob_infos.append({
                'group': group,
                'top_left': (min_x, min_y),
                'center': (center_x, center_y)
            })

        # 가장 위, 왼쪽에 있는 blob 선택 (y→x순)
        blob_infos.sort(key=lambda b: (b['top_left'][1], b['top_left'][0]))
        target_blob = blob_infos[0]
        center_x, center_y = target_blob['center']

        return (cx + center_x, cy + center_y)

    def monitor(self):
        if not self.running:
            return
        pos = self.find_color_inside(self.target_color, tol=self.tolerance)
        if pos:
            self.repeat_on = False
            self._stop_repeat_click()
            self._update_btn_colors()

            with mss.mss() as sct:
                mon = {
                    "left": self.canvas.winfo_rootx(),
                    "top": self.canvas.winfo_rooty(),
                    "width": self.canvas.winfo_width(),
                    "height": self.canvas.winfo_height()
                }
                sct_img = sct.grab(mon)
                img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                img.save(f"찰칵_{timestamp}.png")
                print(f"스크린샷 저장됨: 찰칵_{timestamp}.png")
            print(f"Detected at {pos}, clicking…")
            pyautogui.click(pos)
            self.after(int(self.interval),
                    lambda: pyautogui.click(*self.second_click_pos))
            self.running = False
            self._update_btn_colors()
            return
        self.after(int(self.interval*1000), self.monitor)

    def start_monitor(self):
        if not self.running:
            self.running = True
            self._update_btn_colors()
            print("=== 스타또 ===")
            self.monitor()
            # 반복 on상태면 반복도 같이 시작
            if self.repeat_on:
                self._start_repeat_click()

    def stop_monitor(self):
        if self.running:
            self.running = False
            self._update_btn_colors()
            self._stop_repeat_click()
            print("=== 스또푸 ===")

    def close_app(self):
        self.running = False
        self._stop_repeat_click()
        self.destroy()
        sys.exit()

if __name__ == "__main__":
    app = Overlay(500, 500, 700, 500)
    app.mainloop()
