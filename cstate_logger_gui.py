#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cstate_logger_gui.py  (Albert Style)
v1.1.3 — 2025-10-16 (Zh-TW UI)

變更重點
- 全面中文介面字樣（含提示與預設情境）
- 移除 emoji，避免 Tk/Tcl UCS-2 版本崩潰
- 新增 tk_safe()：過濾所有 > U+FFFF 的字元
- 輸出根目錄：/root/Documents/cstate_logs/<os>-<ver>/<timestamp>/
"""

import os
import sys
import time
import shlex
import atexit
import threading
import subprocess
from datetime import datetime
from pathlib import Path

VERSION = "1.1.3"

# ----------------- 基本日誌 -----------------
def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

SESSION_LOG_PATH = None

def _log(level: str, msg: str):
    line = f"[{ts()}] [{level}] {msg}"
    print(line)
    if SESSION_LOG_PATH:
        with open(SESSION_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")

def INFO(m): _log("INFO", m)
def WARN(m): _log("WARN", m)
def FAIL(m): _log("FAIL", m)
def PASS(m): _log("PASS", m)

# ----------------- OS 偵測 -----------------
def detect_os():
    os_id, os_ver, os_pretty = "linux", "unknown", "Linux"
    try:
        kv = {}
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                kv[k.strip()] = v.strip().strip('"')
        os_id = kv.get("ID", os_id)
        os_ver = kv.get("VERSION_ID", os_ver)
        os_pretty = kv.get("PRETTY_NAME", f"{os_id} {os_ver}")
    except Exception:
        os_ver = os.uname().release
        os_pretty = f"Linux {os_ver}"
    return os_id, os_ver, os_pretty

OS_ID, OS_VER, OS_PRETTY = detect_os()

# ----------------- 輸出路徑（依需求） -----------------
OUTPUT_ROOT = Path("/root/Documents/cstate_logs")
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
SESSION_DIR = OUTPUT_ROOT / f"{OS_ID}-{OS_VER}" / STAMP
SESSION_DIR.mkdir(parents=True, exist_ok=True)
SESSION_LOG_PATH = SESSION_DIR / "Albert_Run.log"

IS_ROOT = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
SUDO = [] if IS_ROOT else ["sudo", "-n"]

# ----------------- 共用工具 -----------------
def which(cmd):
    from shutil import which as _w
    return _w(cmd)

def run(cmd, capture=True):
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    try:
        r = subprocess.run(cmd, capture_output=capture, text=True)
        return r.returncode, (r.stdout if capture else ""), (r.stderr if capture else "")
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"

def need_tool(bin_name: str):
    if which(bin_name):
        return True, ""
    # 發行版提示
    if OS_ID in ("rhel", "centos", "rocky", "almalinux"):
        hints = {
            "turbostat": "sudo dnf install -y kernel-tools",
            "stress-ng": "sudo dnf install -y stress-ng",
            "zenity":     "sudo dnf install -y zenity",
        }
        return False, hints.get(bin_name, "請用套件管理器安裝")
    if OS_ID in ("sles", "sle", "suse", "opensuse-leap", "opensuse"):
        hints = {
            "turbostat": "sudo zypper install -y linux-tools   # 或離線 PackageHub ISO",
            "stress-ng": "sudo zypper install -y stress-ng     # 或離線 PackageHub ISO",
            "zenity":     "sudo zypper install -y zenity",
        }
        return False, hints.get(bin_name, "請用套件管理器安裝")
    return False, f"請安裝 {bin_name}"

# Tk/Tcl 安全字串（移除所有非 BMP 字元）
def tk_safe(s: str) -> str:
    return "".join(ch for ch in s if ord(ch) <= 0xFFFF)

# ----------------- 核心紀錄器 -----------------
class CStateLogger:
    def __init__(self, mode: str, interval: int, repeats: int, hide_cols: str = "PKG_% RAM_%"):
        self.mode = mode
        self.interval = int(interval)
        self.repeats = int(repeats)
        self.total = self.interval * self.repeats
        self.hide_cols = hide_cols

        self.raw  = SESSION_DIR / f"{OS_ID}{OS_VER}_cstate_{self.mode}_{STAMP}.log"
        self.txt  = SESSION_DIR / "Albert_Overview.txt"
        self.html = SESSION_DIR / "Albert_Overview.html"
        self._stress = None

    def header(self):
        with open(self.raw, "w", encoding="utf-8") as f:
            f.write(f"===== Test Start : {ts()} =====\n")
            f.write(f"Script     : cstate_logger_gui.py v{VERSION}\n")
            f.write(f"OS         : {OS_PRETTY}\n")
            f.write(f"Mode       : {self.mode}\n")
            f.write(f"Interval   : {self.interval}s\n")
            f.write(f"Repeats    : {self.repeats}\n")
            f.write(f"Total Time : {self.total}s ({self.total/60:.1f} min)\n\n")

    def start_stress(self):
        if self.mode != "stress":
            return
        ok, hint = need_tool("stress-ng")
        if not ok:
            raise RuntimeError(f"缺少 stress-ng。{hint}")
        self._stress = subprocess.Popen(
            ["stress-ng", "--cpu", "0", "--timeout", f"{self.total}s"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        INFO(f"已啟動 stress-ng（時長 {self.total} 秒）")

    def stop_stress(self):
        if self._stress and self._stress.poll() is None:
            try:
                self._stress.terminate()
                self._stress.wait(timeout=3)
            except Exception:
                try:
                    self._stress.kill()
                except Exception:
                    pass

    def one_shot(self) -> str:
        ok, hint = need_tool("turbostat")
        if not ok:
            raise RuntimeError(f"缺少 turbostat。{hint}")
        cmd = SUDO + ["turbostat", "--quiet", "--Summary", "--interval", "1", "--num_iterations", "1"]
        if self.hide_cols:
            cmd += ["--hide", self.hide_cols]
        rc, out, err = run(cmd, capture=True)
        if rc != 0:
            raise RuntimeError(f"turbostat 失敗：{err.strip()}")
        return out

    def build_overview(self):
        start, end = "", ""
        with open(self.raw, "r", encoding="utf-8") as f:
            for ln in f:
                if ln.startswith("===== Test Start"):
                    start = ln.strip().replace("===== Test Start : ", "")
                if ln.startswith("===== Test End"):
                    end = ln.strip().replace("===== Test End   : ", "")
        with open(self.txt, "w", encoding="utf-8") as f:
            f.write("================= Albert Overview =================\n")
            f.write(f"Script   : cstate_logger_gui.py v{VERSION}\n")
            f.write(f"OS       : {OS_PRETTY}\n")
            f.write(f"Mode     : {self.mode}\n")
            f.write(f"Interval : {self.interval}s\n")
            f.write(f"Repeats  : {self.repeats}\n")
            f.write(f"Total    : {self.total}s ({self.total/60:.1f} min)\n")
            f.write(f"Start    : {start}\n")
            f.write(f"End      : {end}\n")
            f.write(f"Raw Log  : {self.raw.name}\n")
            f.write(f"Path     : {SESSION_DIR}\n")
            f.write("====================================================\n")

        # 取第一筆樣本（節錄前 80 行）
        first = ""
        with open(self.raw, "r", encoding="utf-8") as f:
            grab = False
            buf = []
            for ln in f:
                if ln.startswith("------ 第 1"):
                    grab = True
                elif ln.startswith("------ 第 2"):
                    break
                if grab:
                    buf.append(ln.rstrip("\n"))
        first = "\n".join(buf[:80]).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        html = f"""<!doctype html>
<html lang="zh-Hant"><meta charset="utf-8">
<title>Albert Overview - C-State Logger</title>
<style>
body{{font-family:Segoe UI,Arial,Helvetica,sans-serif;background:#0b1020;color:#e6e9ef;margin:24px}}
h1{{margin:0 0 8px;font-size:20px}}
section{{background:#11172e;border:1px solid #1e2a4a;border-radius:12px;padding:16px;margin-bottom:16px}}
code,pre{{background:#0a0f1e;padding:12px;border-radius:8px;display:block;white-space:pre-wrap}}
.badge{{display:inline-block;padding:4px 8px;border-radius:8px;background:#1e2a4a;margin-right:6px}}
.kv{{line-height:1.7}}
.kv b{{color:#a8c7ff}}
.footer{{opacity:.7;font-size:12px;margin-top:12px}}
</style>
<body>
<h1>Albert Overview - C-State Logger</h1>
<section class="kv">
<span class="badge">v{VERSION}</span>
<span class="badge">OS: {OS_PRETTY}</span>
<span class="badge">Mode: {self.mode}</span>
<div><b>Interval</b>: {self.interval}s &nbsp;&nbsp; <b>Repeats</b>: {self.repeats} &nbsp;&nbsp; <b>Total</b>: {self.total}s ({self.total/60:.1f} min)</div>
<div><b>Output Dir</b>: {SESSION_DIR}</div>
<div><b>Raw Log</b>: {self.raw.name}</div>
</section>
<section><b>Timeline</b>
<pre>
  ===== Test Start : {start}
  ===== Test End   : {end}
</pre></section>
<section><b>First Sample (truncated)</b>
<pre>{first}</pre></section>
<div class="footer">Generated at {ts()}</div>
</body></html>"""
        Path(self.html).write_text(html, encoding="utf-8")

    def run(self, progress_cb=None, eta_cb=None):
        self.header()
        self.start_stress()
        try:
            for i in range(1, self.repeats + 1):
                now = ts()
                with open(self.raw, "a", encoding="utf-8") as f:
                    f.write(f"------ 第 {i} 次紀錄 / 共 {self.repeats} 次 － {now} ------\n")
                    f.write(self.one_shot())
                    f.write("\n")
                if progress_cb:
                    progress_cb(i, self.repeats)
                if eta_cb:
                    eta_cb((self.repeats - i) * self.interval)
                if i < self.repeats:
                    time.sleep(self.interval)
        finally:
            self.stop_stress()
            with open(self.raw, "a", encoding="utf-8") as f:
                f.write(f"===== Test End   : {ts()} =====\n")
            self.build_overview()
            PASS(f"完成！Log 輸出在：{SESSION_DIR}")

# ----------------- 即時頻率視窗（Tkinter） -----------------
def live_freq_loop_tk(stop_event, text_widget):
    rc, out, _ = run("lscpu", capture=True)
    model = maxMHz = minMHz = ""
    if rc == 0:
        for line in out.splitlines():
            if "Model name" in line:
                model = line.split(":", 1)[1].strip()
            if "CPU max MHz" in line:
                maxMHz = line.split(":", 1)[1].strip()
            if "CPU min MHz" in line:
                minMHz = line.split(":", 1)[1].strip()
    while not stop_event.is_set():
        mhz = []
        try:
            for ln in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
                if "cpu MHz" in ln:
                    mhz.append(float(ln.split(":", 1)[1].strip()))
        except Exception:
            pass
        header = tk_safe(
            f"作業系統：{OS_PRETTY}\n"
            f"CPU 型號：{model}\n"
            f"頻率上/下限：min {minMHz or '?'} MHz / max {maxMHz or '?'} MHz\n"
            f"-- 每秒更新 --\n\n"
        )
        body = tk_safe(
            "\n".join([f"CPU{idx:<3d} {v:8.1f} MHz" for idx, v in enumerate(mhz)])
            or "(此平台無 /proc/cpuinfo cpu MHz；可改用：sudo turbostat -i 1)"
        )
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", header + body)
        text_widget.config(state="disabled")
        time.sleep(1)

def show_live_freq_tk():
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as e:
        FAIL(f"Tkinter 不可用：{e}\n改用 TUI（Ctrl+C 離開）")
        # 備援：用 watch 顯示 /proc/cpuinfo 的頻率
        os.system(r"""bash -lc "watch -n1 \"awk -F: '/cpu MHz/ {gsub(/^[ \t]+/,\\\"\\\",$2); printf(\\\"CPU%-3d %8.1f MHz\\n\\\", NR-1, $2)}' /proc/cpuinfo\"" """)
        return

    root = tk.Tk()
    root.title("即時 CPU 頻率")
    root.geometry("780x540")

    f = ttk.Frame(root, padding=12)
    f.pack(fill="both", expand=True)

    text = tk.Text(f, font=("Consolas", 11), bg="#0b1020", fg="#e6e9ef", insertbackground="#e6e9ef")
    text.pack(fill="both", expand=True)

    stop = threading.Event()
    t = threading.Thread(target=live_freq_loop_tk, args=(stop, text), daemon=True)
    t.start()

    def on_close():
        stop.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

# ----------------- GUI -----------------
def start_gui():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except Exception as e:
        WARN(f"Tkinter GUI 無法使用：{e}，改為 TUI。")
        return start_tui()

    root = tk.Tk()
    root.title(f"C-State Logger（Albert v{VERSION}）")
    root.geometry("560x360")

    main = ttk.Frame(root, padding=14)
    main.pack(fill="both", expand=True)

    ttk.Label(
        main,
        text=tk_safe(f"偵測到作業系統：{OS_PRETTY}"),
        font=("Segoe UI", 11, "bold")
    ).pack(anchor="w", pady=(0, 6))

    # 預設情境
    preset = tk.StringVar(value="1H_IDLE")
    rb = ttk.LabelFrame(main, text="快速選擇 / Presets")
    rb.pack(fill="x", pady=6)

    ttk.Radiobutton(rb, text="1 小時 Idle（每 900 秒 × 4 次）",  variable=preset, value="1H_IDLE").pack(anchor="w", pady=2)
    ttk.Radiobutton(rb, text="12 小時 Idle（每 1800 秒 × 24 次）", variable=preset, value="12H_IDLE").pack(anchor="w", pady=2)
    ttk.Radiobutton(rb, text="1 小時 Stress（每 900 秒 × 4 次）",  variable=preset, value="1H_STRESS").pack(anchor="w", pady=2)
    ttk.Radiobutton(rb, text="自訂（下方填入）",                   variable=preset, value="CUSTOM").pack(anchor="w", pady=2)

    # 自訂區
    custom = ttk.LabelFrame(main, text="自訂（選到『自訂』才會套用）")
    custom.pack(fill="x", pady=6)

    mode = tk.StringVar(value="idle")
    ttk.Label(custom, text="模式：").grid(row=0, column=0, sticky="e", padx=4, pady=4)
    ttk.Combobox(custom, textvariable=mode, values=["idle", "stress"], width=10, state="readonly").grid(row=0, column=1, sticky="w", padx=4, pady=4)

    interval = tk.StringVar(value="900")
    repeats  = tk.StringVar(value="4")

    ttk.Label(custom, text="每次間隔（秒）：").grid(row=1, column=0, sticky="e", padx=4, pady=4)
    ttk.Entry(custom, textvariable=interval, width=12).grid(row=1, column=1, sticky="w", padx=4, pady=4)

    ttk.Label(custom, text="總次數：").grid(row=2, column=0, sticky="e", padx=4, pady=4)
    ttk.Entry(custom, textvariable=repeats, width=12).grid(row=2, column=1, sticky="w", padx=4, pady=4)

    tip = ttk.Label(
        main,
        text=tk_safe("時間提示：3600 秒 = 1 小時；43200 秒 = 12 小時｜紀錄次數提示：1 小時 = 4 次；12 小時 = 24 次"),
        foreground="#888"
    )
    tip.pack(fill="x", pady=(2, 8))

    pb  = ttk.Progressbar(main, mode="determinate", maximum=100)
    eta = ttk.Label(main, text="ETA：--:--:--")

    def set_progress(i, t):
        pb["value"] = int(i * 100 / t)
        root.update_idletasks()

    def set_eta(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        eta.config(text=f"ETA：{h:02d}:{m:02d}:{s:02d}")

    btn = ttk.Frame(main)
    btn.pack(fill="x", pady=6)

    ttk.Button(btn, text="即時頻率視窗", command=show_live_freq_tk).pack(side="left")

    def resolve_params():
        p = preset.get()
        if p == "1H_IDLE":
            return "idle", 900, 4
        if p == "12H_IDLE":
            return "idle", 1800, 24
        if p == "1H_STRESS":
            return "stress", 900, 4
        # 自訂
        try:
            iv = int(interval.get().strip())
            rp = int(repeats.get().strip())
        except Exception:
            messagebox.showerror("錯誤", "自訂參數需為正整數")
            return None
        md = mode.get().strip().lower()
        if md not in ("idle", "stress"):
            messagebox.showerror("錯誤", "模式必須為 idle 或 stress")
            return None
        return md, iv, rp

    def on_start():
        params = resolve_params()
        if not params:
            return
        md, iv, rp = params

        ok, hint = need_tool("turbostat")
        if not ok:
            messagebox.showerror("缺少 turbostat", hint)
            return

        if md == "stress":
            ok, hint = need_tool("stress-ng")
            if not ok:
                messagebox.showerror("缺少 stress-ng", hint)
                return

        messagebox.showinfo(
            "確認",
            tk_safe(f"作業系統：{OS_PRETTY}\n模式：{md}\n每次間隔：{iv} 秒\n總次數：{rp}\n預估總時長：{iv*rp} 秒\n\n輸出資料夾：\n{SESSION_DIR}")
        )

        pb.pack(fill="x")
        eta.pack(anchor="e")

        logger = CStateLogger(md, iv, rp)

        def work():
            try:
                logger.run(progress_cb=set_progress, eta_cb=set_eta)
                messagebox.showinfo(
                    "完成",
                    tk_safe(f"RAW：{logger.raw.name}\nTXT：{logger.txt.name}\nHTML：{logger.html.name}\n\n路徑：{SESSION_DIR}")
                )
            except Exception as e:
                messagebox.showerror("失敗", str(e))

        threading.Thread(target=work, daemon=True).start()

    ttk.Button(btn, text="開始測試", command=on_start).pack(side="right")
    root.mainloop()

# ----------------- TUI -----------------
def start_tui():
    INFO(f"偵測到作業系統：{OS_PRETTY}")
    print("1) 1 小時 Idle  2) 12 小時 Idle  3) 1 小時 Stress  4) 自訂  5) 即時頻率視窗")
    ch = input("請選擇 (1-5)：").strip()

    if ch == "5":
        show_live_freq_tk()
        return
    if ch == "1":
        mode, interval, repeats = "idle", 900, 4
    elif ch == "2":
        mode, interval, repeats = "idle", 1800, 24
    elif ch == "3":
        mode, interval, repeats = "stress", 900, 4
    elif ch == "4":
        print("\n時間提示：3600 秒 = 1 小時；43200 秒 = 12 小時｜紀錄次數提示：1 小時 = 4 次；12 小時 = 24 次\n")
        mode = input("模式 idle/stress：").strip().lower()
        interval = int(input("每次紀錄間隔（秒）[預設 900]：").strip() or "900")
        repeats = int(input("總紀錄次數 [預設 4]：").strip() or "4")
        if mode not in ("idle", "stress"):
            FAIL("模式必須為 idle 或 stress")
            return
    else:
        FAIL("無效選項")
        return

    ok, hint = need_tool("turbostat")
    if not ok:
        FAIL(f"缺少 turbostat。{hint}")
        return
    if mode == "stress":
        ok, hint = need_tool("stress-ng")
        if not ok:
            FAIL(f"缺少 stress-ng。{hint}")
            return

    logger = CStateLogger(mode, interval, repeats)

    def pb(i, t):
        print(f"[進度] {i}/{t} ({int(i*100/t)}%)")

    def eta(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        print(f"[ETA] {h:02d}:{m:02d}:{s:02d}")

    try:
        logger.run(progress_cb=pb, eta_cb=eta)
        PASS(f"RAW={logger.raw.name}  TXT={logger.txt.name}  HTML={logger.html.name}")
        INFO(f"路徑：{SESSION_DIR}")
    except Exception as e:
        FAIL(str(e))

# ----------------- Main -----------------
def main():
    if not IS_ROOT:
        INFO("建議以 root 執行（turbostat 可能需要）。")
    use_gui = os.environ.get("DISPLAY") not in (None, "")
    if use_gui:
        start_gui()
    else:
        start_tui()

if __name__ == "__main__":
    atexit.register(lambda: INFO("Bye"))
    main()
