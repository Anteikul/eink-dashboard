#!/bin/sh
set -eu
cd "$(dirname "$0")"

# Existing installations can also use dependencies extracted into this directory.
if [ -d .spotify-runtime ]; then
    runtime="$PWD/.spotify-runtime"
    lib="$runtime/usr/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH 2>/dev/null || printf arm-linux-gnueabihf)"
    export PYTHONPATH="$runtime/usr/lib/python3/dist-packages${PYTHONPATH:+:$PYTHONPATH}"
    export LD_LIBRARY_PATH="$lib:$lib/blas:$lib/lapack${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

address=${EINK_LISTEN_ADDRESS:-}
while [ -z "$address" ]; do
    address=$(ip -o -4 addr show up scope global 2>/dev/null |
        awk '{ sub(/\/.*/, "", $4); print $4; exit }')
    if [ -n "$address" ] || [ "${EINK_WAIT_FOR_NETWORK:-0}" != 1 ]; then
        break
    fi
    sleep 2
done

if [ -n "$address" ]; then
    set -- --listen "$address" "$@"
fi
if command -v authbind >/dev/null; then
    exec authbind --deep python3 -u dashboard.py --seconds 0 "$@"
fi
exec python3 -u dashboard.py --seconds 0 "$@"
