# C-State Logger (GUI/TUI) — Albert Style README
**Script**: `cstate_logger_gui.sh`  
**Version**: v1.0.0  
**Date**: 2025‑10‑02  
**Author**: Albert.Chou style (prepared by ChatGPT)  
**License**: Internal use

---

## 目錄 (Table of Contents)
1. [目的與概觀 (Purpose & Overview)](#purpose)
2. [特色 (Features)](#features)
3. [支援平台與相依性 (Platforms & Dependencies)](#deps)
4. [安裝與準備 (Install & Prep)](#install)
5. [快速開始 (Quick Start)](#quickstart)
6. [GUI 版面 (Presets + Custom)](#gui)
7. [輸出與檔案結構 (Outputs & Layout)](#outputs)
8. [日誌格式與範例 (Log Formats)](#logs)
9. [常見問題 (FAQ / Troubleshooting)](#faq)
10. [安全注意 (Safety Notes)](#safety)
11. [移除與清理 (Uninstall / Cleanup)](#cleanup)
12. [版本資訊 (Change Log)](#changelog)

---

<a id="purpose"></a>
## 1) 目的與概觀 (Purpose & Overview)
本工具用於在 **RHEL 9.x / SLE 15 SPx / openSUSE Leap 15.x** 上，**定時採樣 CPU C‑State / Turbo / 溫度等資訊**，以利「待機 (Idle)」或「壓力 (Stress)」情境之功耗/表現驗證。  
特點是 **自動偵測 OS 與版本**，並以 **Zenity GUI**（或 TUI 後備）引導快速操作，**每次僅取單次樣本**避免卡住，且輸出 **Raw/TXT/HTML** 三種檔案，符合「Albert Style」一頁總覽。

---

<a id="features"></a>
## 2) 特色 (Features)
- ✅ **自動偵測 OS/版本**：依據 `/etc/os-release` 產生對應目錄存放 Log。
- ✅ **GUI + TUI**：有 `zenity` 則走 GUI；無則自動回落文字互動。
- ✅ **快速預設**：首頁提供 **1H/12H Idle、1H Stress**；也可自訂參數。
- ✅ **單次穩定採樣**：`turbostat --interval 1 --num_iterations 1`，每輪只取一筆。
- ✅ **Albert 風格輸出**：
  - Raw：完整 `turbostat` 輸出
  - TXT：`Albert_Overview.txt` 概覽
  - HTML：`Albert_Overview.html` 深色主題總覽頁
- ✅ **色彩化 Console、時間戳**，產出 **Session Run Log**（`Albert_Run.log`）。

---

<a id="deps"></a>
## 3) 支援平台與相依性 (Platforms & Dependencies)
- **OS**：RHEL 9.x / SLE 15 SPx / openSUSE Leap 15.x  
- **必需工具**：
  - `turbostat` （RHEL: `kernel-tools`; SLE/Leap: `linux-tools`）
  - `stress-ng`（僅 *Stress* 模式需要）
  - `zenity`（可選；有則 GUI，無則 TUI）

> **SLE/Leap 無網路環境**：請使用 **PackageHub POOL/UPDATES ISO** 建立離線 repo 再安裝 `linux-tools` 與 `stress-ng`；或以 rpm 離線安裝（例如 `bp156` 版本）。

---

<a id="install"></a>
## 4) 安裝與準備 (Install & Prep)
1. 將 `cstate_logger_gui.sh` 放至你要執行的位置（例：`~/tools/`）。  
2. 賦予執行權限：
   ```bash
   chmod +x cstate_logger_gui.sh
   ```
3. 安裝必要工具（擇一環境）：  
   - **RHEL / Rocky / Alma**  
     ```bash
     sudo dnf install -y kernel-tools stress-ng zenity
     ```
   - **SLE / openSUSE Leap**  
     ```bash
     sudo zypper install -y linux-tools stress-ng zenity
     ```
     > 若 `stress-ng` 或 `linux-tools` 找不到，請啟用 PackageHub 或使用離線 ISO 安裝。

---

<a id="quickstart"></a>
## 5) 快速開始 (Quick Start)
```bash
./cstate_logger_gui.sh
```
- 有 `zenity` → 顯示 GUI 首頁（含預設情境）。  
- 無 `zenity` → 進入 TUI 互動模式。

**時間/次數提示**：
- ⏱️ `3600` 秒 = `1` 小時、`43200` 秒 = `12` 小時  
- 📝 每 15 分紀錄一次 → `1H = 4 次`、`12H = 24 次`

---

<a id="gui"></a>
## 6) GUI 版面 (Presets + Custom)
**首頁四選一**：
- `1H Idle`：每 `900s` × `4` 次  
- `12H Idle`：每 `1800s` × `24` 次  
- `1H Stress`：每 `900s` × `4` 次 + 背景執行 `stress-ng`  
- `Custom`：自訂 **模式（Idle/Stress）**、**間隔（秒）**、**次數**

> **Stress 模式**會啟動 `stress-ng --cpu 0 --timeout <總時長>`，於整個測試期間施加 CPU 負載。

---

<a id="outputs"></a>
## 7) 輸出與檔案結構 (Outputs & Layout)
所有輸出集中於：
```
~/Downloads/cstate_logs/<os-id>-<version>/<timestamp>/
```
- `RAW`：`<os><ver>_cstate_<mode>_<timestamp>.log`  
  - 包含每次採樣的 `turbostat` 原始輸出
- `TXT`：`Albert_Overview.txt`  
  - 關鍵資訊總表（OS / Mode / Interval / Repeats / Total / Start / End / Raw 檔名 / 路徑）
- `HTML`：`Albert_Overview.html`  
  - 深色主題、可快速閱讀、內含第一筆樣本節錄（最多 80 行）
- `SESSION`：`Albert_Run.log`  
  - 執行過程之 INFO/WARN/PASS/FAIL 記錄（含時間戳）

---

<a id="logs"></a>
## 8) 日誌格式與範例 (Log Formats)
**Raw** 檔前後各有測試界標：
```
===== Test Start : 2025-10-02 09:00:00 =====
...（每次採樣段落）...
------ 第 1 次紀錄 / 共 4 次 － 2025-10-02 09:00:00 ------
< turbostat 單次輸出（約略 CPU MHz、C1/C6/C10、pkgtemp、Busy% 等）>
------ 第 2 次紀錄 / 共 4 次 － 2025-10-02 09:15:00 ------
...
===== Test End   : 2025-10-02 10:00:00 =====
```

**TXT** 概覽：
```
Script   : cstate_logger_gui.sh v1.0.0
OS       : SLES 15 SP6 (x86_64)
Mode     : idle
Interval : 900s
Repeats  : 4
Total    : 3600s (60.0 min)
Start    : 2025-10-02 09:00:00
End      : 2025-10-02 10:00:00
Raw Log  : sles15.6_cstate_idle_20251002_090000.log
Path     : /home/user/Downloads/cstate_logs/sles-15.6/20251002_090000
```

**HTML** 概覽：
- 頁面頂部有版本、OS、Mode、Interval/Repeats/Total 等徽章（badges）  
- Timeline 顯示 `Test Start/End`  
- 節錄第一筆採樣段落（80 行內）

---

<a id="faq"></a>
## 9) 常見問題 (FAQ / Troubleshooting)
1) **找不到 `turbostat`**  
   - RHEL：`sudo dnf install -y kernel-tools`  
   - SLE/Leap：`sudo zypper install -y linux-tools`（必要時使用 PackageHub ISO 離線安裝）

2) **Stress 模式找不到 `stress-ng`**  
   - RHEL：`sudo dnf install -y stress-ng`  
   - SLE/Leap：`sudo zypper install -y stress-ng` 或以 PackageHub ISO 安裝；若採 rpmfind 離線安裝，遇到 `libsctp.so.1` 依賴，請一併安裝 `lksctp-tools`/`libsctp1`（bp156）。

3) **GUI 沒出現**  
   - 未安裝 `zenity` 或遠端沒有 X/Wayland。改用 TUI；或安裝 `zenity` 後在本機桌面執行。
   - RHEL：`sudo dnf install -y zenity`  
   - SLE/Leap：`sudo zypper install -y zenity`（必要時使用 PackageHub ISO 離線安裝）

4) **需要 root 嗎？**  
   - `turbostat` 通常需要 root 權限。腳本會自動以 `sudo` 執行必要命令。

5) **要不要關 C‑States？**  
   - 測 Idle 表現 → **開啟** C‑States、Package C State Limit 盡量讓 CPU 進深層（C10/Auto）。  
   - 測高性能穩定性 → 可**關閉** C‑States（或 Performance Policy），但 Idle 觀察失焦。

---

<a id="safety"></a>
## 10) 安全注意 (Safety Notes)
- 腳本 **不會**修改系統核心參數或 BIOS；僅執行量測與（選擇性）壓力。  
- `stress-ng` 會提升溫度與功耗；在機房/封閉機殼內測試請確保散熱與風扇策略。  
- 輸出檔預設寫入使用者 `~/Downloads`，不覆蓋先前資料（每次皆分 timestamp 目錄）。

---

<a id="cleanup"></a>
## 11) 移除與清理 (Uninstall / Cleanup)
- 刪除腳本即可：`rm -f cstate_logger_gui.sh`  
- 刪除輸出資料夾：`rm -rf ~/Downloads/cstate_logs`

> 本工具無安裝 systemd 服務、無背景常駐程序。

---

<a id="changelog"></a>
## 12) 版本資訊 (Change Log)
- **v1.0.0 (2025‑10‑02)**  
  - 初版：OS 自動偵測、GUI 快速預設 + 自訂、`turbostat` 單次採樣回圈、Raw/TXT/HTML 三檔輸出、Albert_Run.log。

---

### 附錄：命令小抄 (Cheat Sheet)
```bash
# Idle 1 小時（每 15 分記一次，共 4 次）
./cstate_logger_gui.sh  # GUI 選 1H Idle

# Stress 1 小時
./cstate_logger_gui.sh  # GUI 選 1H Stress

# 手動安裝（RHEL）
sudo dnf install -y kernel-tools stress-ng zenity

# 手動安裝（SLE/Leap）— 線上
sudo zypper install -y linux-tools stress-ng zenity

# 離線（SLE/Leap）— 使用 PackageHub ISO 方式安裝（略，依內部 SOP）
```
