#!/bin/sh
set -eu

# noVNC is intentionally available only through the host's loopback listener
# configured in docker-compose.yml. It exists solely for the first manual login.
if [ "${HEADLESS:-false}" != "true" ]; then
  export DISPLAY="${DISPLAY:-:99}"
  display_number="${DISPLAY#:}"
  display_number="${display_number%%.*}"
  # A container restart can retain Xvfb lock files in its writable layer even
  # though all processes from the previous run are already gone.
  rm -f "/tmp/.X${display_number}-lock" "/tmp/.X11-unix/X${display_number}"
  Xvfb "$DISPLAY" -screen 0 1280x900x24 -ac +extension GLX +render -noreset &
  fluxbox >/tmp/fluxbox.log 2>&1 &
  x11vnc -display "$DISPLAY" -forever -shared -nopw -rfbport 5900 >/tmp/x11vnc.log 2>&1 &
  /usr/share/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 6080 >/tmp/novnc.log 2>&1 &
fi

exec uvicorn main:app --host 0.0.0.0 --port 8080
