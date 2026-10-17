#!/bin/bash
# Double-click previews the verified plan. Explicit --install prepares disabled files.
set -u
FUTURE_BUNDLE_DIR="$(cd "$(dirname "$0")" && pwd -P)"
FUTURE_PYTHON=""
for FUTURE_CANDIDATE in /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /usr/local/bin/python3.13 /usr/local/bin/python3; do
    if [[ -x "$FUTURE_CANDIDATE" ]] && "$FUTURE_CANDIDATE" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,10) else 1)' >/dev/null 2>&1; then
        FUTURE_PYTHON="$FUTURE_CANDIDATE"
        break
    fi
done
if [[ -z "$FUTURE_PYTHON" ]]; then
    echo "需要 Python 3.10 或更新版本。请手动双击包内官方 Python 3.13 安装器，完成后重新运行："
    for FUTURE_PKG in "$FUTURE_BUNDLE_DIR"/vendor/python-3.13.*-macos11.pkg; do
        [[ -f "$FUTURE_PKG" ]] && echo "$FUTURE_PKG"
    done
    echo "如果包内没有安装器，请从 https://www.python.org/downloads/macos/ 获取。"
    exit 1
fi
"$FUTURE_PYTHON" "$FUTURE_BUNDLE_DIR/install.py" "$@"
FUTURE_RESULT=$?
if [[ $# -eq 0 ]]; then
    echo ""
    echo "以上仅为只读计划。准备安装时运行："
    printf '%q --install\n' "$FUTURE_BUNDLE_DIR/install.command"
    if [[ -t 0 ]]; then read -r -p "按回车关闭。" FUTURE_CONTINUE; fi
fi
exit "$FUTURE_RESULT"
