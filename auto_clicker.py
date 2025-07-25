import tkinter as tk
import sys
import os
import time
import ctypes
import pyautogui
from tkinter import colorchooser
import mss
from PIL import Image

# Enable DPI awareness so multi-monitor coordinates are correct
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
        self.panel_width = 250
        self.interval = 0.1    # seconds between scans
        self.tolerance = 40    # ± per channel
        self.running = False

        self._make_title_bar(title)
        self._make_canvas()
        self._make_control_panel()

        # Bind keys: END = 좌표, HOME = 스포이드 색상
        self.bind_all('<End>', self._capture_mouse_position)
        self.bind_all('<Home>', self._capture_color_from_mouse)

    def _make_title_bar(self, title):
        bar = tk.Frame(self, bg="#444")
        bar.pack(fill="x")
        bar.bind("<ButtonPress-1>", self.start_move)
        bar.bind("<B1-Motion>", self.on_move)
        tk.Label(
            bar,
            text=title,
            bg="#444",
            fg="white",
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
        # 구분선
        sep = tk.Frame(self.panel, height=2)
        sep.pack(fill="x", pady=(12, 6), padx=4)
        # Start/Stop 버튼
        self.btn_frame = tk.Frame(self.panel, bg="#f6f7fa")
        self.btn_frame.pack(pady=(0,0), padx=10)
        self.start_btn = tk.Button(self.btn_frame, text="Start", command=self.start_monitor, bg="#42d784", fg="white", bd=0, relief="ridge", width=7)
        self.stop_btn  = tk.Button(self.btn_frame, text="Stop",  command=self.stop_monitor,  bg="#dddddd", fg="#888888", bd=0, relief="ridge", width=7)
        self.start_btn.pack(side="left", padx=(0, 5))
        self.stop_btn.pack(side="left")
        self._update_btn_colors()   # 초기 버튼 색상/상태 셋업
        # 구분선
        sep = tk.Frame(self.panel, height=2, bg="#e1e2e3")
        sep.pack(fill="x", pady=(12, 6), padx=4)
        # 색상 영역
        color_frame = tk.Frame(self.panel, bg="#f6f7fa")
        color_frame.pack(pady=(16,8), padx=10, fill="x")
        tk.Label(color_frame, text="색상", bg="#f6f7fa", anchor="w").pack(side="left")
        self.preview = tk.Label(color_frame, bg=self._hex(), width=2, height=1, relief="solid", bd=1)
        self.preview.pack(side="left", padx=(8,3))
        self.hex_var = tk.StringVar(value=self._hex())
        self.hex_var.trace_add('write', self._on_hex_change)
        tk.Entry(color_frame, width=8, textvariable=self.hex_var, justify="center", font=("Consolas", 10)).pack(side="left", padx=(0, 3))
        tk.Button(color_frame, text="🎨", width=2, command=self._pick_color, bg="#eaf0fa", bd=0, relief="ridge").pack(side="left")
        tk.Label(color_frame, text="(HOME)", bg="#f6f7fa", fg="#2167ce", font=("Segoe UI",8,"bold")).pack(side="left", padx=(6,0))
        # 좌표 영역
        coord_frame = tk.Frame(self.panel, bg="#f6f7fa")
        coord_frame.pack(pady=8, padx=10, fill="x", )
        tk.Label(coord_frame, text="좌표", bg="#f6f7fa", anchor="w").pack(side="left")
        self.x_var = tk.IntVar(value=self.second_click_pos[0])
        self.y_var = tk.IntVar(value=self.second_click_pos[1])
        self.x_var.trace_add('write', lambda *a: self._update_second_click())
        self.y_var.trace_add('write', lambda *a: self._update_second_click())
        tk.Label(coord_frame, text="X", bg="#f6f7fa").pack(side="left", padx=(8,0))
        tk.Entry(coord_frame, width=6, textvariable=self.x_var, justify="center").pack(side="left", padx=(0, 3))
        tk.Label(coord_frame, text="Y", bg="#f6f7fa").pack(side="left")
        tk.Entry(coord_frame, width=6, textvariable=self.y_var, justify="center").pack(side="left", padx=(0, 3))
        tk.Label(coord_frame, text="(END)", bg="#f6f7fa", fg="#2167ce", font=("Segoe UI",8,"bold")).pack(side="left", padx=(2,0))
        # 간격 영역
        interval_frame = tk.Frame(self.panel, bg="#f6f7fa")
        interval_frame.pack(pady=8, padx=10, fill="x")
        tk.Label(interval_frame, text="간격(초)", bg="#f6f7fa", anchor="w").pack(side="left")
        self.int_var = tk.DoubleVar(value=self.interval)
        self.int_var.trace_add('write', lambda *a: self._update_interval())
        tk.Entry(interval_frame, width=6, textvariable=self.int_var, justify="center").pack(side="left", padx=(8,0))
        # 허용오차 영역
        tol_frame = tk.Frame(self.panel, bg="#f6f7fa")
        tol_frame.pack(pady=8, padx=10, fill="x")

        # 허용오차 + 입력란 (가로)
        row = tk.Frame(tol_frame, bg="#f6f7fa")
        row.pack(fill="x")
        tk.Label(row, text="허용오차", bg="#f6f7fa", anchor="w").pack(side="left")
        self.tol_var = tk.IntVar(value=self.tolerance)
        self.tol_var.trace_add('write', lambda *a: self._update_tolerance())
        tk.Entry(row, width=6, textvariable=self.tol_var, justify="center").pack(side="left", padx=(8,0))

        # 안내문구 (아래 한 줄로)
        tk.Label(tol_frame,text="80까지 정도만 추천",bg="#f6f7fa",anchor="w",fg="#2167ce").pack(anchor="w", pady=(2,0))
        # 안내문구 (아래 한 줄로)
        tk.Label(tol_frame,text="배경이 투명이라 설정 바꿀 때\n숫자만 클릭 잘 해야함",bg="#f6f7fa",anchor="w",fg="#000000",justify="left").pack(anchor="w", pady=(2,0))

    def _update_btn_colors(self):
        if self.running:
            self.start_btn.config(bg="#dddddd", fg="#888888", state="disabled", text="Start")
            self.stop_btn.config(bg="#fc4141", fg="white", state="normal", text="Stop")
        else:
            self.start_btn.config(bg="#42d784", fg="white", state="normal", text="Start")
            self.stop_btn.config(bg="#dddddd", fg="#888888", state="disabled", text="Stop")



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

    # --- Home 키 스포이드(색상 추출) 기능 ---
    def _capture_color_from_mouse(self, e):
        x, y = pyautogui.position()
        with mss.mss() as sct:
            mon = {"left": x, "top": y, "width": 1, "height": 1}
            sct_img = sct.grab(mon)
            img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
            r, g, b = img.getpixel((0, 0))
        color_hex = '#%02x%02x%02x' % (r, g, b)
        self.hex_var.set(color_hex)
    # ----------------------------------------

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
    # ---- Blob 인식 끝 ----

    def monitor(self):
        if not self.running:
            return
        pos = self.find_color_inside(self.target_color, tol=self.tolerance)
        if pos:
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
                print(f"스크린샷 저장됨: macro_capture_{timestamp}.png")
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

    def stop_monitor(self):
        if self.running:
            self.running = False
            self._update_btn_colors()
            print("=== 스또푸 ===")

    def close_app(self):
        self.running = False
        self.destroy()
        sys.exit()

if __name__ == "__main__":
    app = Overlay(500, 500, 700, 500)
    app.mainloop()
