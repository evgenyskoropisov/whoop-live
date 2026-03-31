#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
#  WHOOP BLE Monitor — запуск
# ──────────────────────────────────────────────────────────────
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo ""
echo "  ⌁  WHOOP BLE Monitor"
echo "  ─────────────────────────────────────"

if ! command -v python3 &>/dev/null; then
  echo "  ❌  Python 3 не найден."; exit 1
fi
echo "  ✓  $(python3 --version)"

# ── Проверяем разрешение Bluetooth для терминала ──────────────
echo "  🔵  Для BLE нужен доступ к Bluetooth."
echo "      Если macOS спросит разрешение — нажми OK."
echo ""

# ── Виртуальное окружение ──────────────────────────────────────
if [ ! -d "venv" ]; then
  echo "  📦  Создаю venv..."; python3 -m venv venv
fi
source venv/bin/activate

# ── Зависимости ────────────────────────────────────────────────
echo "  📦  Устанавливаю зависимости..."
pip install -q --upgrade pip
pip install -q flask bleak pywebview
echo "  ✓  Готово"

echo "  🚀  Launching WHOOP Live..."
echo "  ⏹   Close the app window or press Ctrl+C to stop"
echo "  ─────────────────────────────────────"
echo ""

python3 server.py
