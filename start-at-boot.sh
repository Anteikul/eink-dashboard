#!/bin/sh
set -eu

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
cd "$(dirname "$0")"
exec >>dashboard.log 2>&1

exec 9>.autostart.lock
flock -n 9 || exit 0

printf 'Dashboard autostart: boot=%s time=%s\n' \
    "$(cat /proc/sys/kernel/random/boot_id)" "$(date -Is)"
printf '%s\n' "$$" >dashboard.pid
export EINK_WAIT_FOR_NETWORK=1
exec ./start.sh
