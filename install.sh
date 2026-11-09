#!/bin/sh
set -eu
cd "$(dirname "$0")"

check_dependencies() {
    command -v crontab >/dev/null && command -v flock >/dev/null &&
        command -v ip >/dev/null && command -v authbind >/dev/null &&
        python3 -c 'import lgpio, numpy, requests; from PIL import Image, ImageFont'
}

check_wifi_dependencies() {
    command -v nmcli >/dev/null && [ -x /usr/sbin/dnsmasq ] &&
        python3 -c 'import dbus'
}

if [ "${1:-}" = --check ]; then
    check_dependencies
    printf '%s\n' 'Required commands and libraries are available.'
    exit 0
fi
wifi_setup=0
if [ "$#" -eq 1 ] && [ "$1" = --wifi-setup ]; then
    wifi_setup=1
    shift
fi
if [ "$#" -ne 0 ] || [ "$(id -u)" -eq 0 ]; then
    printf '%s\n' 'Run ./install.sh [--wifi-setup] from your normal user account on the Pi.' >&2
    exit 1
fi
if ! command -v apt-get >/dev/null || [ ! -e /dev/gpiochip0 ]; then
    printf '%s\n' 'The installer requires Raspberry Pi OS and a GPIO device.' >&2
    exit 1
fi

if ! check_dependencies >/dev/null 2>&1 || [ ! -f /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf ]; then
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends python3-lgpio python3-pil python3-numpy \
        python3-requests fonts-dejavu-core ca-certificates tzdata cron iproute2 util-linux authbind
fi
if [ ! -w /dev/gpiochip0 ]; then
    printf 'Run sudo usermod -aG gpio %s to enable GPIO, then sign in again.\n' "$(id -un)" >&2
    exit 1
fi
port_access=/etc/authbind/byport/80
if [ ! -e "$port_access" ]; then
    sudo install -m 0500 -o "$(id -un)" /dev/null "$port_access"
fi
if [ ! -x "$port_access" ]; then
    printf '%s\n' 'The existing authbind configuration does not grant this user access to port 80.' >&2
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
    raise SystemExit('Use an installation path without percent signs or line breaks.')
print('@reboot exec ' + shlex.quote(launcher))
PY
)
old_job='@reboot "$HOME/eink-dashboard/start-at-boot.sh"'
if [ "$PWD" = "$HOME/eink-dashboard" ] && grep -Fxq "$old_job" "$tmp/current"; then
    job="$old_job"
fi
if ! grep -Fxq "$job" "$tmp/current" && grep -q 'start-at-boot\.sh' "$tmp/current"; then
    printf '%s\n' 'Cron already points to another dashboard installation. Update it in its existing directory.' >&2
    exit 1
fi
if [ "$wifi_setup" -eq 1 ]; then
    account=$(id -un)
    case "$account" in
        ''|*[!a-zA-Z0-9_.-]*) printf '%s\n' 'This account name cannot be used for Wi-Fi setup.' >&2; exit 1 ;;
    esac
    if ! check_wifi_dependencies >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y --no-install-recommends network-manager dnsmasq-base python3-dbus
    fi
    sed "s/@ACCOUNT@/$account/g" eink-wifi.socket > "$tmp/eink-wifi.socket"
    sudo install -d -o root -g root -m 0755 /usr/local/libexec
    sudo install -o root -g root -m 0755 wifi_setup.py /usr/local/libexec/eink-wifi
    sudo install -o root -g root -m 0644 "$tmp/eink-wifi.socket" eink-wifi@.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable eink-wifi.socket
    sudo systemctl restart eink-wifi.socket
fi
if ! grep -Fxq "$job" "$tmp/current"; then
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
else
    printf '%s\n' 'The dashboard is already running. Restart the Pi to apply the update.'
fi
address=$(ip -o -4 addr show up scope global 2>/dev/null |
    awk '{ sub(/\/.*/, "", $4); print $4; exit }')
if [ -n "$address" ]; then
    printf 'Open http://%s/ in your browser.\n' "$address"
elif [ -S /run/eink-wifi.sock ]; then
    printf '%s\n' 'If Wi-Fi is unavailable, follow the hotspot instructions on the e-paper display.'
else
    printf '%s\n' 'Open the Pi IP address in your browser once the Pi is online.'
fi
printf 'Setup code: %s\n' "$code"
