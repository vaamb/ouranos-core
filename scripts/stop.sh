#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

# Check if OURANOS_DIR is set and the directory exists
if [[ ! -d "${OURANOS_DIR}" ]]; then
    echo "OURANOS_DIR environment variable is not set or the directory does not exist. Please source your profile or run the installation script first."
    exit 1
fi

# Load logging functions
readonly DATETIME=$(date +%Y%m%d_%H%M%S)
rm -f /tmp/ouranos_stop_*.log
readonly LOG_FILE="/tmp/ouranos_stop_${DATETIME}.log"
. "${OURANOS_DIR}/scripts/utils/logging.sh"

# Log stop attempt
log INFO "Attempting to stop Ouranos..."

# Check that a PID is really an Ouranos process, and not a recycled PID.
# Ouranos renames itself to "ouranos" (setproctitle), but only once its imports
# are done: until then it is still "<python> -m ouranos". Matching the command
# line covers both, so an instance can be stopped while it is still starting up.
is_ouranos_proc() {
    local pid=$1
    local cmdline
    # tr flattens the NUL-separated argv. 2>/dev/null before the redirect silences
    # a dead PID's who fails to open. A missing /proc entry returns 1.
    cmdline=$(tr '\0' ' ' 2>/dev/null < "/proc/${pid}/cmdline") || return 1
    # read strips the trailing NUL-padding setproctitle leaves behind.
    read -r cmdline <<< "$cmdline"
    # Use "-m ouranos" so it matches both "uv run ..." and "python ..."
    [[ "$cmdline" == "ouranos" || "$cmdline" == *"-m ouranos" ]]
}

# Function to get Ouranos PID
get_ouranos_pid() {
    # Prefer PID file when available
    if [[ -f "${OURANOS_DIR}/ouranos.pid" ]]; then
        local pid
        pid=$(cat "${OURANOS_DIR}/ouranos.pid")
        if kill -0 "$pid" 2>/dev/null && is_ouranos_proc "$pid"; then
            echo "$pid"
            return 0
        fi
    fi
    # Fallback: the PID file may be missing or stale while an instance started
    # by other means is still running. Match both the renamed process and one
    # still starting up ("<python> -m ouranos"); -f on the latter is safe as it
    # cannot match this script's own command line.
    { pgrep -x "ouranos"; pgrep -f -- "-m ouranos"; } 2>/dev/null | head -n1 || true
}

# Check if Ouranos is running
OURANOS_PID=$(get_ouranos_pid)

if [[ -z "$OURANOS_PID" ]]; then
    log INFO "No running instance of Ouranos found."

    # Clean up PID file if it exists
    if [[ -f "${OURANOS_DIR}/ouranos.pid" ]]; then
        log WARN "Stale PID file found. Cleaning up..."
        rm -f "${OURANOS_DIR}/ouranos.pid"
    fi

    exit 0
fi

log INFO "Stopping Ouranos (PID: $OURANOS_PID)..."

# Send SIGTERM (15) - graceful shutdown
if kill -15 "$OURANOS_PID" 2>/dev/null; then
    # Wait for the process to terminate
    TIMEOUT=10  # seconds
    sleep .5
    while (( TIMEOUT-- > 0 )) && kill -0 "$OURANOS_PID" 2>/dev/null; do
        echo -n "."
        sleep 1
    done

    # Check if process is still running
    if kill -0 "$OURANOS_PID" 2>/dev/null; then
        log WARN "Graceful shutdown failed. Force killing the process..."
        kill -9 "$OURANOS_PID" 2>/dev/null || true
        sleep .5
    fi

    # Clean up PID file
    if [[ -f "${OURANOS_DIR}/ouranos.pid" ]]; then
        rm -f "${OURANOS_DIR}/ouranos.pid"
    fi

    # Verify the process was actually stopped
    if kill -0 "$OURANOS_PID" 2>/dev/null; then
        die "Failed to stop Ouranos. Process still running with PID: ${OURANOS_PID}."
    fi

    log SUCCESS "Ouranos stopped successfully."
    exit 0
else
    die "Failed to send stop signal to Ouranos (PID: ${OURANOS_PID}). You may need to run with sudo."
fi
