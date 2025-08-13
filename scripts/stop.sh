#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

# Load logging functions
readonly DATETIME=$(date +%Y%m%d_%H%M%S)
readonly LOG_FILE="/tmp/ouranos_stop_${DATETIME}.log"
readonly SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
. "${SCRIPT_DIR}/logging.sh"

# Check if OURANOS_DIR is set
if [[ -z "${OURANOS_DIR:-}" ]]; then
    log ERROR "OURANOS_DIR environment variable is not set. Please source your profile or run the install script first."
fi

# Check if the directory exists
if [[ ! -d "$OURANOS_DIR" ]]; then
    log ERROR "Ouranos directory not found at $OURANOS_DIR. Please check your installation."
fi

# Ensure logs directory exists
mkdir -p "${OURANOS_DIR}/logs" || log ERROR "Failed to create logs directory"

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
    log ERROR "Could not determine Ouranos process ID"
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
        log ERROR "Failed to stop Ouranos. Process still running with PID: $OURANOS_PID)"
    fi

    log INFO "Ouranos stopped successfully."
    exit 0
else
    log ERROR "Failed to send stop signal to Ouranos (PID: $OURANOS_PID). You may need to run with sudo."
fi
