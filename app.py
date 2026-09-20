"""Korean Windows-friendly desktop interface for MP3 compression."""
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from compressor import Cancelled, compress, find_ffmpeg


def size(value):
    return f"{value / 1024 / 1024:.2f} MB" if value >= 1024 * 1024 else f"{value / 1024:.1f} KB"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MP3 용량 줄이기")
        self.geometry("840x590")
        self.minsize(720, 520)
        self.files = []
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.running = False
        self.closing = False
        self.output = tk.StringVar()
        self.bitrate = tk.StringVar(value="48")
        self.mono = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="MP3 파일을 추가해 주세요.")
        self.controls = []
        self.configure(padx=24, pady=20)
        ttk.Label(self, text="MP3 용량 줄이기", font=("맑은 고딕", 21, "bold")).pack(anchor="w")
        ttk.Label(self, text="기본 48kbps · 여러 파일 한 번에 · 원본 보존", padding=(0, 5, 0, 16)).pack(anchor="w")
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        self.button(toolbar, "파일 추가", self.add_files).pack(side="left")
        self.button(toolbar, "목록 비우기", self.clear).pack(side="left", padx=8)
        ttk.Label(toolbar, text="음질 (kbps)").pack(side="left", padx=(18, 5))
        combo = ttk.Combobox(toolbar, textvariable=self.bitrate, values=(32, 48, 64, 96, 128), width=5, state="readonly")
        combo.pack(side="left")
        self.controls.append((combo, "readonly"))
        check = ttk.Checkbutton(toolbar, text="모노 (음성에 적합)", variable=self.mono)
        check.pack(side="left", padx=16)
        self.controls.append((check, "normal"))
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, pady=14)
        self.table = ttk.Treeview(frame, columns=("name", "before", "after", "state"), show="headings", selectmode="none")
        for key, title, width in (("name", "파일", 290), ("before", "원본", 95), ("after", "결과", 95), ("state", "상태", 215)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=70)
        self.table.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(frame, command=self.table.yview)
        scroll.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scroll.set)
        dest = ttk.Frame(self)
        dest.pack(fill="x")
        ttk.Label(dest, text="저장 폴더").pack(side="left", padx=(0, 8))
        entry = ttk.Entry(dest, textvariable=self.output)
        entry.pack(side="left", fill="x", expand=True)
        self.controls.append((entry, "normal"))
        self.button(dest, "선택", self.choose_output).pack(side="left", padx=(8, 0))
        ttk.Label(self, text="48kbps는 1분에 약 360KB입니다. 음질은 낮아지며, 앨범 사진과 태그는 제거됩니다.", wraplength=740).pack(anchor="w", pady=(12, 8))
        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x")
        ttk.Label(self, textvariable=self.status, wraplength=740).pack(anchor="w", pady=8)
        actions = ttk.Frame(self)
        actions.pack(fill="x")
        self.button(actions, "압축 시작", self.start).pack(side="right")
        self.stop_button = ttk.Button(actions, text="취소", command=self.stop, state="disabled")
        self.stop_button.pack(side="right", padx=8)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self.poll)

    def button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=command)
        self.controls.append((button, "normal"))
        return button

    def add_files(self):
        selected = filedialog.askopenfilenames(title="MP3 파일 선택", filetypes=[("MP3", "*.mp3")])
        for item in selected:
            path = Path(item).resolve()
            if path not in self.files:
                try:
                    original = size(path.stat().st_size)
                except OSError as exc:
                    messagebox.showerror("파일 오류", str(exc))
                    continue
                self.table.insert("", "end", iid=str(len(self.files)), values=(path.name, original, "—", "대기"))
                self.files.append(path)
        if self.files and not self.output.get():
            self.output.set(str(self.files[0].parent / "compressed"))
        self.status.set(f"{len(self.files)}개 파일 선택됨")

    def clear(self):
        self.files.clear()
        self.table.delete(*self.table.get_children())
        self.status.set("MP3 파일을 추가해 주세요.")
        self.progress["value"] = 0

    def choose_output(self):
        folder = filedialog.askdirectory(title="압축 파일 저장 폴더")
        if folder:
            self.output.set(folder)

    def start(self):
        if not self.files or not self.output.get().strip():
            messagebox.showinfo("선택 필요", "MP3 파일과 저장 폴더를 선택해 주세요.")
            return
        try:
            find_ffmpeg()
        except Exception as exc:
            messagebox.showerror("실행 준비", str(exc))
            return
        self.running = True
        self.cancel.clear()
        for widget, _ in self.controls:
            widget.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress.configure(value=0, maximum=len(self.files))
        for row in self.table.get_children():
            self.table.set(row, "after", "—")
            self.table.set(row, "state", "대기")
        args = (list(self.files), Path(self.output.get().strip()), int(self.bitrate.get()), self.mono.get())
        threading.Thread(target=self.worker, args=args, daemon=True).start()

    def worker(self, files, output, bitrate, mono):
        success = skipped = errors = saved = 0
        try:
            for index, path in enumerate(files):
                if self.cancel.is_set():
                    break
                self.events.put(("start", index, path.name))
                try:
                    result = compress(path, output, bitrate=bitrate, mono=mono, cancel=self.cancel,
                                      on_progress=lambda seconds, i=index: self.events.put(("seconds", i, seconds)))
                    if result.output:
                        success += 1
                        saved += result.original_bytes - result.compressed_bytes
                        self.events.put(("result", index, size(result.compressed_bytes), "완료"))
                    else:
                        skipped += 1
                        self.events.put(("result", index, "—", "원본이 더 작음 · 생략"))
                except Cancelled:
                    self.events.put(("result", index, "—", "취소됨"))
                    break
                except Exception as exc:
                    errors += 1
                    self.events.put(("error", index, path.name, str(exc)))
        finally:
            prefix = "취소됨" if self.cancel.is_set() else "작업 완료"
            self.events.put(("done", f"{prefix} · 성공 {success}개 · 생략 {skipped}개 · 오류 {errors}개 · {size(saved)} 절약"))

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "start":
                    self.table.set(str(event[1]), "state", "압축 중")
                    self.status.set(f"{event[1] + 1}/{len(self.files)} · {event[2]} 압축 중…")
                elif kind == "seconds":
                    self.table.set(str(event[1]), "state", f"압축 중 · {event[2]:.0f}초 처리")
                elif kind in ("result", "error"):
                    index = str(event[1])
                    self.table.set(index, "after", event[2] if kind == "result" else "—")
                    self.table.set(index, "state", event[3] if kind == "result" else "오류")
                    self.progress["value"] = event[1] + 1
                    if kind == "error" and not self.closing:
                        messagebox.showerror(f"변환 오류 · {event[2]}", event[3])
                elif kind == "done":
                    self.running = False
                    for widget, state in self.controls:
                        widget.configure(state=state)
                    self.stop_button.configure(state="disabled")
                    self.status.set(event[1])
                    if self.closing:
                        self.destroy()
                        return
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def stop(self):
        self.cancel.set()
        self.stop_button.configure(state="disabled")
        self.status.set("취소 중…")

    def close(self):
        if self.running:
            self.closing = True
            self.stop()
        else:
            self.destroy()


if __name__ == "__main__":
    App().mainloop()
