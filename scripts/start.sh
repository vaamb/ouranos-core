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
rm -f /tmp/ouranos_start_*.log
readonly LOG_FILE="/tmp/ouranos_start_${DATETIME}.log"
. "${OURANOS_DIR}/scripts/utils/logging.sh"

# Default values
FOREGROUND=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--foreground)
            FOREGROUND=true
            shift
            ;;
        *)
            die "Unknown parameter: $1"
            ;;
    esac
done

# Create logs directory if it doesn't exist
mkdir -p "${OURANOS_DIR}/logs" ||
    die "Failed to create logs directory"

# Check if already running — prefer PID file
if [[ -f "${OURANOS_DIR}/ouranos.pid" ]]; then
    PID=$(cat "${OURANOS_DIR}/ouranos.pid")
    if kill -0 "$PID" 2>/dev/null && pgrep -x "ouranos" | grep -qw "$PID"; then
        log WARN "Ouranos is already running with PID $PID"
        log INFO "If you want to restart, please run: ouranos restart"
        exit 0
    fi
    # Stale PID file — process is gone, clean up and continue
    rm -f "${OURANOS_DIR}/ouranos.pid"
fi
# Fallback to pgrep if no PID file
if pgrep -x "ouranos" > /dev/null; then
    PID=$(pgrep -x "ouranos" | head -n 1)
    log WARN "Ouranos is already running with PID $PID"
    log INFO "If you want to restart, please run: ouranos restart"
    exit 0
fi

# Change to Ouranos directory
cd "$OURANOS_DIR" ||
    die "Failed to change to Ouranos directory: $OURANOS_DIR"

# Check if virtual environment exists
if [[ ! -d ".venv" ]]; then
    die "Python virtual environment not found. Please run the installation script first."
fi

# Start Ouranos
log INFO "Starting Ouranos..."

if [[ "$FOREGROUND" = true ]]; then
    log INFO "Running in foreground mode (logs will be shown in terminal)"
    uv run python -m ouranos
    EXIT_CODE=$?

    log INFO "Ouranos process exited with code $EXIT_CODE"
    exit "$EXIT_CODE"
else
    # Run Ouranos in the background and capture PID immediately
    nohup uv run python -m ouranos > "${OURANOS_DIR}/logs/stdout" 2>&1 &
    OURANOS_PID=$!
    echo "$OURANOS_PID" > "${OURANOS_DIR}/ouranos.pid"
    log INFO "Ouranos started in background mode"
    log INFO "Ouranos stdout and stderr output redirected to ${OURANOS_DIR}/logs/stdout"

    # Verify that Ouranos started successfully
    sleep 2

    # Check if process is still running
    if ! kill -0 "$OURANOS_PID" 2>/dev/null; then
        # Process died, check error log
        # Clean up PID file
        [[ -f "${OURANOS_DIR}/ouranos.pid" ]] && rm -f "${OURANOS_DIR}/ouranos.pid"
        die "Failed to start Ouranos. Check the logs at ${LOG_FILE}."
    fi

    log SUCCESS "Ouranos started successfully with PID $OURANOS_PID"

    exit 0
fi
