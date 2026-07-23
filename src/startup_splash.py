from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional


_DISABLED_VALUES = {"1", "true", "yes", "on"}


def should_show_startup_splash(shell: str) -> bool:
    if str(shell or "").strip().lower() == "none":
        return False
    return str(os.environ.get("VTS_DISABLE_SPLASH", "")).strip().lower() not in _DISABLED_VALUES


class StartupSplash:
    """Small native startup window that remains responsive before the web UI exists."""

    PHASES = (
        "啟動應用程式",
        "準備本機 AI 服務",
        "檢查硬體與專案資料",
        "開啟工作區",
    )

    def __init__(self, enabled: bool = True):
        self.enabled = False
        self.error: Optional[str] = None
        self._dismissed = False
        self._root = None
        self._tk = None
        self._progress_canvas = None
        self._progress_fill = None
        self._status_label = None
        self._detail_label = None
        self._elapsed_label = None
        self._phase_dots = []
        self._phase_labels = []
        self._close_button = None

        if not enabled:
            return

        try:
            import tkinter as tk

            self._tk = tk
            self._build_window()
            self.enabled = True
            self._pump()
        except Exception as exc:  # pragma: no cover - depends on desktop availability
            self.error = str(exc)
            self.close()

    def _build_window(self) -> None:
        tk = self._tk
        root = tk.Tk()
        self._root = root
        root.withdraw()
        root.title("Vision Training Studio")
        root.overrideredirect(True)
        root.configure(bg="#0b1220")
        try:
            root.attributes("-topmost", True)
            root.attributes("-alpha", 0.98)
        except Exception:
            pass

        width, height = 580, 356
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        root.geometry(f"{width}x{height}+{x}+{y}")

        border = tk.Frame(root, bg="#253247")
        border.pack(fill="both", expand=True)
        panel = tk.Frame(border, bg="#111925")
        panel.pack(fill="both", expand=True, padx=1, pady=1)

        header = tk.Frame(panel, bg="#111925")
        header.pack(fill="x", padx=28, pady=(24, 8))

        mark = tk.Canvas(header, width=42, height=42, bg="#111925", highlightthickness=0)
        mark.pack(side="left", padx=(0, 14))
        mark.create_rectangle(2, 2, 40, 40, fill="#1f4f9d", outline="#2f75db", width=1)
        mark.create_oval(11, 10, 17, 16, fill="#dbeafe", outline="")
        mark.create_oval(25, 10, 31, 16, fill="#dbeafe", outline="")
        mark.create_oval(18, 25, 24, 31, fill="#dbeafe", outline="")
        mark.create_line(14, 15, 21, 27, 28, 15, fill="#93c5fd", width=2)

        title_box = tk.Frame(header, bg="#111925")
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_box,
            text="Vision Training Studio",
            bg="#111925",
            fg="#f8fafc",
            font=("Segoe UI Semibold", 18),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            title_box,
            text="資料集控制中心 · 正在啟動",
            bg="#111925",
            fg="#8fa0b7",
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        self._status_label = tk.Label(
            panel,
            text="正在準備應用程式",
            bg="#111925",
            fg="#e5edf7",
            font=("Segoe UI Semibold", 12),
            anchor="w",
        )
        self._status_label.pack(fill="x", padx=30, pady=(12, 2))

        self._detail_label = tk.Label(
            panel,
            text="請稍候，程式正在建立安全的本機工作環境。",
            bg="#111925",
            fg="#9bacbf",
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=510,
        )
        self._detail_label.pack(fill="x", padx=30)

        self._progress_canvas = tk.Canvas(
            panel,
            height=6,
            bg="#263244",
            highlightthickness=0,
        )
        self._progress_canvas.pack(fill="x", padx=30, pady=(16, 12))
        self._progress_fill = self._progress_canvas.create_rectangle(0, 0, 1, 6, fill="#3b82f6", outline="")

        phase_box = tk.Frame(panel, bg="#111925")
        phase_box.pack(fill="x", padx=30)
        for index, phase in enumerate(self.PHASES):
            row = tk.Frame(phase_box, bg="#111925")
            row.pack(fill="x", pady=2)
            dot = tk.Label(
                row,
                text="●",
                bg="#111925",
                fg="#42516a",
                font=("Segoe UI", 8),
                width=2,
                anchor="w",
            )
            dot.pack(side="left")
            label = tk.Label(
                row,
                text=phase,
                bg="#111925",
                fg="#687991",
                font=("Segoe UI", 9),
                anchor="w",
            )
            label.pack(side="left", fill="x", expand=True)
            self._phase_dots.append(dot)
            self._phase_labels.append(label)

        footer = tk.Frame(panel, bg="#111925")
        footer.pack(side="bottom", fill="x", padx=30, pady=(8, 20))
        self._elapsed_label = tk.Label(
            footer,
            text="啟動時間通常少於 30 秒",
            bg="#111925",
            fg="#6f8199",
            font=("Segoe UI", 8),
            anchor="w",
        )
        self._elapsed_label.pack(side="left", fill="x", expand=True)
        self._close_button = tk.Button(
            footer,
            text="關閉",
            command=self._dismiss,
            bg="#263244",
            fg="#e5edf7",
            activebackground="#334155",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=16,
            pady=5,
            font=("Segoe UI Semibold", 9),
            cursor="hand2",
        )

        root.deiconify()
        root.lift()

    def update_status(
        self,
        phase_index: int,
        status: str,
        detail: str,
        progress: float,
        elapsed_seconds: Optional[float] = None,
    ) -> None:
        if not self.enabled:
            return
        phase_index = max(0, min(int(phase_index), len(self.PHASES) - 1))
        progress = max(0.0, min(float(progress), 1.0))
        self._status_label.configure(text=status, fg="#e5edf7")
        self._detail_label.configure(text=detail, fg="#9bacbf")

        for index, (dot, label) in enumerate(zip(self._phase_dots, self._phase_labels)):
            if index < phase_index:
                dot.configure(fg="#22c55e")
                label.configure(fg="#9fb0c5")
            elif index == phase_index:
                dot.configure(fg="#60a5fa")
                label.configure(fg="#e5edf7")
            else:
                dot.configure(fg="#42516a")
                label.configure(fg="#687991")

        self._pump()
        width = max(1, self._progress_canvas.winfo_width())
        self._progress_canvas.coords(self._progress_fill, 0, 0, max(3, width * progress), 6)

        if elapsed_seconds is not None and elapsed_seconds >= 5:
            seconds = max(1, int(elapsed_seconds))
            self._elapsed_label.configure(
                text=f"已等待 {seconds} 秒 · AI 元件首次載入可能需要較長時間"
            )
        self._pump()

    def complete(self) -> None:
        if not self.enabled:
            return
        self.update_status(
            3,
            "主畫面已就緒",
            "正在切換至 Vision Training Studio 工作區。",
            1.0,
        )
        self._sleep_with_pump(0.18)
        self.close()

    def show_error(self, message: str, log_path: Optional[Path] = None) -> None:
        if not self.enabled:
            return
        detail = message.strip() or "啟動程序未完成。"
        if log_path:
            detail = f"{detail}\n詳細資訊：{log_path}"
        self._status_label.configure(text="無法完成啟動", fg="#fca5a5")
        self._detail_label.configure(text=detail, fg="#fda4af")
        self._progress_canvas.itemconfigure(self._progress_fill, fill="#ef4444")
        self._elapsed_label.configure(text="請關閉後重新啟動；若持續發生，請提供啟動日誌。")
        self._close_button.pack(side="right")
        self._pump()

    def wait_for_dismiss(self, timeout_seconds: float = 12.0) -> None:
        if not self.enabled:
            return
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while self.enabled and not self._dismissed and time.monotonic() < deadline:
            self._pump()
            time.sleep(0.05)

    def _dismiss(self) -> None:
        self._dismissed = True
        self.close()

    def _sleep_with_pump(self, duration: float) -> None:
        deadline = time.monotonic() + max(0.0, duration)
        while self.enabled and time.monotonic() < deadline:
            self._pump()
            time.sleep(0.02)

    def _pump(self) -> None:
        if not self.enabled and self._root is None:
            return
        try:
            self._root.update_idletasks()
            self._root.update()
        except Exception:
            self.close()

    def close(self) -> None:
        root, self._root = self._root, None
        self.enabled = False
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass

