#!/bin/bash
# ================================================================
#  Script Name : cstate_logger_gui.sh
#  Purpose     : CPU C-State / Utilization sampling with GUI/TUI
#  Platforms   : RHEL 9.x / SLE 15 SPx / openSUSE Leap 15.x
#  Author      : Albert.Chou style (prepared by ChatGPT)
#  Version     : v1.0.0
#  Date        : 2025-10-02
#  License     : Internal use
#
#  Features (Albert Style)
#  - Auto-detect OS/version → logs grouped by OS
#  - Zenity GUI with "Quick Presets + Custom" (1H/12H Idle, 1H Stress)
#  - Stable single-shot sampling: turbostat --interval 1 --num_iterations 1
#  - Colorized console, timestamps, safe cleanup
#  - Outputs:
#      * RAW  : <os><ver>_cstate_<mode>_<ts>.log
#      * TXT  : Albert_Overview.txt
#      * HTML : Albert_Overview.html
#
#  Dependencies
#    turbostat (RHEL: kernel-tools; SLE/Leap: linux-tools)
#    stress-ng (only for stress mode)
#    zenity (optional for GUI; fallback to TUI)
#
#  Change Log
#   - v1.0.0 (2025-10-02) Initial release with GUI presets, OS-aware logs,
#                         dual overview logs, stable turbostat loop.
# ================================================================

set -uo pipefail

# -----------------------------
# Color & Log Helpers (Albert)
# -----------------------------
NC='\033[0m'; RED='\033[0;31m'; YEL='\033[0;33m'; GRN='\033[0;32m'; BLU='\033[0;34m'
_ts(){ date '+%Y-%m-%d %H:%M:%S'; }

SESSION_LOG=""   # set after directories ready

_log(){  # console + session log
  local level="$1"; shift
  local msg="[$(_ts)] [$level] $*"
  echo -e "$msg"
  [[ -n "$SESSION_LOG" ]] && echo -e "$msg" >> "$SESSION_LOG"
}
Info(){  echo -e "${BLU}[$(_ts)] [INFO]${NC} $*";  [[ -n "$SESSION_LOG" ]] && echo "[$(_ts)] [INFO] $*" >> "$SESSION_LOG"; }
Warn(){  echo -e "${YEL}[$(_ts)] [WARN]${NC} $*";  [[ -n "$SESSION_LOG" ]] && echo "[$(_ts)] [WARN] $*" >> "$SESSION_LOG"; }
Fail(){  echo -e "${RED}[$(_ts)] [FAIL]${NC} $*";  [[ -n "$SESSION_LOG" ]] && echo "[$(_ts)] [FAIL] $*" >> "$SESSION_LOG"; }
Pass(){  echo -e "${GRN}[$(_ts)] [PASS]${NC} $*";  [[ -n "$SESSION_LOG" ]] && echo "[$(_ts)] [PASS] $*" >> "$SESSION_LOG"; }

# -----------------------------
# OS Detect
# -----------------------------
if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  OS_ID="${ID:-linux}"
  OS_VER="${VERSION_ID:-unknown}"
  OS_PRETTY="${PRETTY_NAME:-$OS_ID $OS_VER}"
else
  OS_ID="linux"
  OS_VER="$(uname -r)"
  OS_PRETTY="Linux $OS_VER"
fi

# -----------------------------
# Paths / Session
# -----------------------------
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_BASE="$HOME/Downloads/cstate_logs"
OS_DIR="$LOG_BASE/${OS_ID}-${OS_VER}"
SESSION_DIR="$OS_DIR/$STAMP"
mkdir -p "$SESSION_DIR"
SESSION_LOG="$SESSION_DIR/Albert_Run.log"

SUDO=""
[[ $EUID -ne 0 ]] && SUDO="sudo"

# -----------------------------
# GUI / TUI helpers
# -----------------------------
has_zenity=0
command -v zenity >/dev/null 2>&1 && has_zenity=1

_gui_info(){
  [[ $has_zenity -eq 1 ]] && zenity --info --no-wrap --title="C-State Logger" --text="$1" 2>/dev/null
}
_gui_question(){
  if [[ $has_zenity -eq 1 ]]; then
    zenity --question --no-wrap --title="確認" --text="$1" 2>/dev/null
    return $?
  else
    return 0
  fi
}

# -----------------------------
# Tool checks
# -----------------------------
need_tool(){
  local bin="$1"
  if ! command -v "$bin" >/dev/null 2>&1; then
    case "$OS_ID" in
      rhel|centos|rocky|almalinux)
        case "$bin" in
          turbostat) Fail "缺少 turbostat。請先：sudo dnf install -y kernel-tools" ;;
          stress-ng) Fail "缺少 stress-ng。請先：sudo dnf install -y stress-ng" ;;
          zenity)    Warn "缺少 zenity，將使用 TUI。可安裝：sudo dnf install -y zenity" ;;
        esac
        ;;
      sles|sle|suse|opensuse*|opensuse-leap)
        case "$bin" in
          turbostat) Fail "缺少 turbostat（linux-tools）。請先：sudo zypper install -y linux-tools（或離線 PackageHub ISO）" ;;
          stress-ng) Fail "缺少 stress-ng。請先：sudo zypper install -y stress-ng（或離線 PackageHub ISO）" ;;
          zenity)    Warn "缺少 zenity，將使用 TUI。可安裝：sudo zypper install -y zenity" ;;
        esac
        ;;
      *) Fail "缺少 $bin，請用系統套件管理器安裝。";;
    esac
    return 1
  fi
  return 0
}

# -----------------------------
# Gather Inputs (Preset-first GUI)
# -----------------------------
MODE=""; INTERVAL=""; REPEAT=""

if [[ $has_zenity -eq 1 ]]; then
  preset=$(zenity --list --radiolist \
    --title="C-State Logger - 快速開始" \
    --text="選擇預設或自訂（建議直接用預設，最省時）" \
    --column="選" --column="代碼" --column="說明" \
    TRUE  "1H_IDLE"   "1 小時 Idle（每 900 秒 × 4 次）" \
    FALSE "12H_IDLE"  "12 小時 Idle（每 1800 秒 × 24 次）" \
    FALSE "1H_STRESS" "1 小時 Stress（每 900 秒 × 4 次）" \
    FALSE "CUSTOM"    "自訂參數（模式/間隔/次數）" \
    --height=320 --width=640 2>/dev/null) || { Fail "使用者取消。"; exit 1; }

  case "$preset" in
    "1H_IDLE")   MODE="idle";   INTERVAL=900;  REPEAT=4  ;;
    "12H_IDLE")  MODE="idle";   INTERVAL=1800; REPEAT=24 ;;
    "1H_STRESS") MODE="stress"; INTERVAL=900;  REPEAT=4  ;;
    "CUSTOM")
      zenity --info --no-wrap --title="時間/次數提示" \
        --text="⏱️ 3600 秒 = 1 小時\n43200 秒 = 12 小時\n\n📝 建議：每 15 分紀錄一次 → 1H=4 次、12H=24 次" 2>/dev/null || true
      MODE=$(zenity --list --radiolist \
        --title="選擇模式" --text="Idle 或 Stress" \
        --column="選" --column="模式" --column="說明" \
        TRUE "idle"   "閒置（不產生負載）" \
        FALSE "stress" "壓力測試（產生 CPU 負載）" \
        --height=220 --width=520 2>/dev/null) || { Fail "使用者取消。"; exit 1; }
      form=$(zenity --forms --title="自訂參數" --text="請輸入每次紀錄間隔秒數與總紀錄次數" \
             --add-entry="每次紀錄間隔（秒）(預設 900)" \
             --add-entry="總紀錄次數（預設 4）" \
             --separator="," 2>/dev/null) || { Fail "使用者取消。"; exit 1; }
      IFS=',' read -r INTERVAL REPEAT <<< "$form"
      [[ -z "${INTERVAL// }" ]] && INTERVAL=900
      [[ -z "${REPEAT// }"   ]] && REPEAT=4
      ;;
    *) Fail "無效選項。"; exit 1 ;;
  esac
else
  echo -e "\n========== C-State Logger (TUI) =========="
  echo "偵測到 OS：$OS_PRETTY"
  echo "1) 1H Idle  2) 12H Idle  3) 1H Stress  4) 自訂"
  read -rp "選擇 (1-4): " ch
  case "$ch" in
    1) MODE="idle";   INTERVAL=900;  REPEAT=4  ;;
    2) MODE="idle";   INTERVAL=1800; REPEAT=24 ;;
    3) MODE="stress"; INTERVAL=900;  REPEAT=4  ;;
    4)
      echo -e "\n⏱️ 3600=1h, 43200=12h；📝 1h=4 次，12h=24 次\n"
      read -rp "模式 idle/stress: " MODE
      read -rp "每次紀錄間隔（秒）[預設 900]: " INTERVAL; INTERVAL=${INTERVAL:-900}
      read -rp "總紀錄次數 [預設 4]: " REPEAT; REPEAT=${REPEAT:-4}
      ;;
    *) Fail "無效選項。"; exit 1;;
  esac
fi

# Validate
if ! [[ "$INTERVAL" =~ ^[0-9]+$ && "$REPEAT" =~ ^[0-9]+$ ]]; then
  Fail "參數必須為正整數。"; exit 1
fi
if [[ "$MODE" != "idle" && "$MODE" != "stress" ]]; then
  Fail "模式必須為 idle 或 stress。"; exit 1
fi

TOTAL_TIME=$((INTERVAL * REPEAT))
MINS=$(awk -v s="$TOTAL_TIME" 'BEGIN{printf "%.1f", s/60}')
RAW_LOG="${SESSION_DIR}/${OS_ID}${OS_VER}_cstate_${MODE}_${STAMP}.log"
TXT_SUM="${SESSION_DIR}/Albert_Overview.txt"
HTML_SUM="${SESSION_DIR}/Albert_Overview.html"

# -----------------------------
# Tool presence
# -----------------------------
need_tool "turbostat" || exit 1
[[ "$MODE" == "stress" ]] && need_tool "stress-ng" || true
command -v zenity >/dev/null 2>&1 || Info "未安裝 zenity，將使用 TUI。"

# -----------------------------
# Summary & confirm
# -----------------------------
summary="OS         : ${OS_PRETTY}
Mode       : ${MODE}
Interval   : ${INTERVAL}s
Repeats    : ${REPEAT}
Total Time : ${TOTAL_TIME}s (${MINS} min)
Output Dir : ${SESSION_DIR}"

Info "測試摘要：\n${summary}"
if [[ $has_zenity -eq 1 ]]; then
  _gui_question "確認開始測試？\n\n${summary}" || { Warn "使用者取消。"; exit 0; }
else
  read -rp "確認開始？(y/N): " ok; [[ "$ok" =~ ^[Yy]$ ]] || { Warn "使用者取消。"; exit 0; }
fi

# -----------------------------
# Trap for cleanup
# -----------------------------
STRESS_PID=""
cleanup(){
  if [[ -n "$STRESS_PID" ]]; then
    kill "$STRESS_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# -----------------------------
# Write header to RAW log
# -----------------------------
{
  echo "===== Test Start : $(_ts) ====="
  echo "Script     : cstate_logger_gui.sh v1.0.0"
  echo "OS         : ${OS_PRETTY}"
  echo "Mode       : ${MODE}"
  echo "Interval   : ${INTERVAL}s"
  echo "Repeats    : ${REPEAT}"
  echo "Total Time : ${TOTAL_TIME}s (${MINS} min)"
  echo ""
} > "$RAW_LOG"

# -----------------------------
# Start stress if needed
# -----------------------------
if [[ "$MODE" == "stress" ]]; then
  Info "啟動 stress-ng（${TOTAL_TIME}s）..."
  $SUDO stress-ng --cpu 0 --timeout "${TOTAL_TIME}s" &>/dev/null &
  STRESS_PID=$!
fi

# -----------------------------
# Sampling Loop (GUI progress or TUI)
# -----------------------------
if [[ $has_zenity -eq 1 ]]; then
  {
    for ((i=1;i<=REPEAT;i++)); do
      CURRENT="$(_ts)"
      echo "------ 第 $i 次紀錄 / 共 $REPEAT 次 － $CURRENT ------" >> "$RAW_LOG"
      $SUDO turbostat --quiet --Summary --interval 1 --num_iterations 1 >> "$RAW_LOG"
      echo "" >> "$RAW_LOG"
      pct=$(( i * 100 / REPEAT ))
      ETA=$(date -d "+$(( (REPEAT-i)*INTERVAL )) seconds" "+%H:%M:%S")
      echo "$pct"
      echo "# 已完成第 $i 次紀錄，休息 ${INTERVAL}s ...  (ETA ${ETA})"
      sleep "$INTERVAL"
    done
  } | zenity --progress --title="C-State Logger" --percentage=0 --auto-close --no-cancel --width=560 2>/dev/null
else
  for ((i=1;i<=REPEAT;i++)); do
    CURRENT="$(_ts)"
    Info "[$CURRENT] 第 $i/$REPEAT 次取樣..."
    echo "------ 第 $i 次紀錄 / 共 $REPEAT 次 － $CURRENT ------" >> "$RAW_LOG"
    $SUDO turbostat --quiet --Summary --interval 1 --num_iterations 1 >> "$RAW_LOG"
    echo "" >> "$RAW_LOG"
    sleep "$INTERVAL"
  done
fi

# -----------------------------
# Wrap up
# -----------------------------
echo "===== Test End   : $(_ts) =====" >> "$RAW_LOG"

# Build TXT overview
{
  echo "================= Albert Overview ================="
  echo "Script   : cstate_logger_gui.sh v1.0.0"
  echo "OS       : ${OS_PRETTY}"
  echo "Mode     : ${MODE}"
  echo "Interval : ${INTERVAL}s"
  echo "Repeats  : ${REPEAT}"
  echo "Total    : ${TOTAL_TIME}s (${MINS} min)"
  echo "Start    : $(head -n 1 "$RAW_LOG" | sed -E 's/^===== Test Start : //')"
  echo "End      : $(tail -n 1 "$RAW_LOG"  | sed -E 's/^===== Test End   : //')"
  echo "Raw Log  : $(basename "$RAW_LOG")"
  echo "Path     : ${SESSION_DIR}"
  echo "===================================================="
} > "$TXT_SUM"

# Build HTML overview (simple, readable)
cat > "$HTML_SUM" <<EOF
<!doctype html>
<html lang="en"><meta charset="utf-8">
<title>Albert Overview - C-State Logger</title>
<style>
body{font-family:Segoe UI,Arial,Helvetica,sans-serif;background:#0b1020;color:#e6e9ef;margin:24px}
h1{margin:0 0 8px;font-size:20px}
section{background:#11172e;border:1px solid #1e2a4a;border-radius:12px;padding:16px;margin-bottom:16px}
code,pre{background:#0a0f1e;padding:12px;border-radius:8px;display:block;white-space:pre-wrap}
.badge{display:inline-block;padding:4px 8px;border-radius:8px;background:#1e2a4a;margin-right:6px}
.kv{line-height:1.7}
.kv b{color:#a8c7ff}
.footer{opacity:.7;font-size:12px;margin-top:12px}
</style>
<body>
<h1>Albert Overview - C-State Logger</h1>
<section class="kv">
<span class="badge">v1.0.0</span>
<span class="badge">OS: ${OS_PRETTY}</span>
<span class="badge">Mode: ${MODE}</span>
<div><b>Interval</b>: ${INTERVAL}s &nbsp;&nbsp; <b>Repeats</b>: ${REPEAT} &nbsp;&nbsp; <b>Total</b>: ${TOTAL_TIME}s (${MINS} min)</div>
<div><b>Output Dir</b>: ${SESSION_DIR}</div>
<div><b>Raw Log</b>: $(basename "$RAW_LOG")</div>
</section>

<section>
<b>Timeline</b>
<pre>
$(grep -E '^(===== Test Start|===== Test End)' "$RAW_LOG" | sed 's/^/  /')
</pre>
</section>

<section>
<b>First Sample (truncated)</b>
<pre>
$(awk '/^------ 第 1/{flag=1;print;next} /^------ 第 2/{flag=0} flag' "$RAW_LOG" | head -n 80 | sed 's/&/&amp;/g; s/</\&lt;/g')
</pre>
</section>

<div class="footer">Generated at $(_ts)</div>
</body></html>
EOF

Pass "完成！Log 輸出在：${SESSION_DIR}"
Info "RAW:  $(basename "$RAW_LOG")"
Info "TXT:  $(basename "$TXT_SUM")"
Info "HTML: $(basename "$HTML_SUM")"

# Final GUI toast
[[ $has_zenity -eq 1 ]] && zenity --info --no-wrap --title="C-State Logger" \
  --text="✅ 完成！\n\n輸出資料夾：\n${SESSION_DIR}\n\nRAW：$(basename "$RAW_LOG")\nTXT：$(basename "$TXT_SUM")\nHTML：$(basename "$HTML_SUM")" 2>/dev/null || true

exit 0
