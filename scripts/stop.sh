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

# Function to check if Ouranos is running
get_ouranos_pid() {
    # Prefer PID file when available
    if [[ -f "${OURANOS_DIR}/ouranos.pid" ]]; then
        local pid
        pid=$(cat "${OURANOS_DIR}/ouranos.pid" 2>/dev/null || echo "")
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
        fi
    # Fallback to strict process match
    else
        pgrep -x "ouranos" | head -n1
    fi
}

is_running() {
    # Check if Ouranos is running
    local pid
    pid=$(get_ouranos_pid)
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        return 0
    fi

    return 1
}

# Check if Ouranos is running
if ! is_running; then
    log INFO "No running instance of Ouranos found."

    # Clean up PID file if it exists
    if [[ -f "${OURANOS_DIR}/ouranos.pid" ]]; then
        log WARN "Stale PID file found. Cleaning up..."
        rm -f "${OURANOS_DIR}/ouranos.pid"
    fi

    exit 0
fi

# Get the PID of the running process (prefer PID from is_running)
OURANOS_PID=$(get_ouranos_pid)

if [[ -z "$OURANOS_PID" ]]; then
    die "Could not determine Ouranos process ID"
fi

log INFO "Stopping Ouranos (PID: $OURANOS_PID)..."

# Send SIGTERM (15) - graceful shutdown
if kill -15 "$OURANOS_PID" 2>/dev/null; then
    # Wait for the process to terminate
    TIMEOUT=10  # seconds
    while (( TIMEOUT-- > 0 )) && kill -0 "$OURANOS_PID" 2>/dev/null; do
        echo -n "."
        sleep 1
    done
    echo

    # Check if process is still running
    if kill -0 "$OURANOS_PID" 2>/dev/null; then
        log WARN "Graceful shutdown failed. Force killing the process..."
        kill -9 "$OURANOS_PID" 2>/dev/null || true
    fi

    # Clean up PID file
    if [[ -f "${OURANOS_DIR}/ouranos.pid" ]]; then
        rm -f "${OURANOS_DIR}/ouranos.pid"
    fi

    # Verify the process was actually stopped
    if is_running > /dev/null; then
        die "Failed to stop Ouranos. Process still running with PID: $OURANOS_PID"
    fi

    log INFO "Ouranos stopped successfully."
    exit 0
else
    die "Failed to send stop signal to Ouranos (PID: $OURANOS_PID). You may need to run with sudo."
fi
