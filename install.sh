#!/bin/sh
set -eu
cd "$(dirname "$0")"

check_dependencies() {
    command -v crontab >/dev/null && command -v flock >/dev/null &&
        command -v ip >/dev/null &&
        python3 -c 'import lgpio, numpy, requests; from PIL import Image, ImageFont'
}

if [ "${1:-}" = --check ]; then
    check_dependencies
    printf '%s\n' 'Potřebné nástroje a knihovny jsou dostupné.'
    exit 0
fi
if [ "$#" -ne 0 ] || [ "$(id -u)" -eq 0 ]; then
    printf '%s\n' 'Spusť ./install.sh ze svého běžného účtu na Pi.' >&2
    exit 1
fi
if ! command -v apt-get >/dev/null || [ ! -e /dev/gpiochip0 ]; then
    printf '%s\n' 'Instalátor očekává Raspberry Pi OS a dostupné GPIO.' >&2
    exit 1
fi

if ! check_dependencies >/dev/null 2>&1 || [ ! -f /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf ]; then
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends python3-lgpio python3-pil python3-numpy \
        python3-requests fonts-dejavu-core ca-certificates tzdata cron iproute2 util-linux
fi
if [ ! -w /dev/gpiochip0 ]; then
    printf 'Povol GPIO a znovu se přihlas příkazem sudo usermod -aG gpio %s\n' "$(id -un)" >&2
    exit 1
fi
if ! systemctl is-active --quiet cron; then
    sudo systemctl enable --now cron
fi
chmod +x start.sh start-at-boot.sh install.sh

tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
if ! LC_ALL=C crontab -l > "$tmp/current" 2>"$tmp/error"; then
    if ! grep -Fxq "no crontab for $(id -un)" "$tmp/error"; then
        cat "$tmp/error" >&2
        exit 1
    fi
fi

job=$(python3 - <<'PY'
import shlex
from pathlib import Path
launcher = str(Path('start-at-boot.sh').resolve())
if '\n' in launcher or '%' in launcher:
    raise SystemExit('Použij cestu bez znaku procenta nebo nového řádku.')
print('@reboot exec ' + shlex.quote(launcher))
PY
)
old_job='@reboot "$HOME/eink-dashboard/start-at-boot.sh"'
if [ "$PWD" = "$HOME/eink-dashboard" ] && grep -Fxq "$old_job" "$tmp/current"; then
    job="$old_job"
fi
if ! grep -Fxq "$job" "$tmp/current"; then
    if grep -q 'start-at-boot\.sh' "$tmp/current"; then
        printf '%s\n' 'V cronu už je jiná instalace dashboardu. Aktualizuj ji v její stávající složce.' >&2
        exit 1
    fi
    printf '\n%s\n' "$job" >> "$tmp/current"
    crontab "$tmp/current"
fi

code=$(python3 - <<'PY'
from pathlib import Path
from device_settings import DeviceSettings
print(DeviceSettings(Path.cwd()).code)
PY
)
if flock -n .panel.lock true; then
    nohup ./start-at-boot.sh </dev/null >/dev/null 2>&1 &
fi
address=$(ip -o -4 addr show up scope global 2>/dev/null |
    awk '{ sub(/\/.*/, "", $4); print $4; exit }')
if [ -n "$address" ]; then
    printf 'Otevři v prohlížeči http://%s:8080/\n' "$address"
else
    printf '%s\n' 'Po připojení k síti otevři IP adresu Pi na portu 8080.'
fi
printf 'Kód nastavení: %s\n' "$code"
