#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

# Load logging functions
readonly DATETIME=$(date +%Y%m%d_%H%M%S)
readonly LOG_FILE="/tmp/ouranos_start_${DATETIME}.log"
. "./logging.sh"

# Check if OURANOS_DIR is set
if [[ -z "${OURANOS_DIR:-}" ]]; then
    log ERROR "OURANOS_DIR environment variable is not set. Please source your profile or run the install script first."
fi

# Check if the directory exists
if [[ ! -d "$OURANOS_DIR" ]]; then
    log ERROR "Ouranos directory not found at $OURANOS_DIR. Please check your installation."
fi

# Create logs directory if it doesn't exist
mkdir -p "${OURANOS_DIR}/logs" || log ERROR "Failed to create logs directory"

# Check if already running
if pgrep -f "ouranos" > /dev/null; then
    PID=$(pgrep -f "ouranos" | head -n 1)
    log WARN "Ouranos is already running with PID $PID"
    log INFO "If you want to restart, please run: ouranos restart"
    exit 0
fi

# Change to Ouranos directory
cd "$OURANOS_DIR" || log ERROR "Failed to change to Ouranos directory: $OURANOS_DIR"

# Check if virtual environment exists
if [[ ! -d "python_venv" ]]; then
    log ERROR "Python virtual environment not found. Please run the install script first."
fi

# Activate virtual environment
# shellcheck source=/dev/null
if ! source "python_venv/bin/activate"; then
    log ERROR "Failed to activate Python virtual environment"
fi

# Start Ouranos
log INFO "Starting Ouranos..."

# Run Ouranos in the background and log the PID
nohup python3 -m ouranos > "${OURANOS_DIR}/logs/stdout" 2>&1 &
log INFO "Ouranos stdout and stderr output redirected to ${GAIA_DIR}/logs/stdout"

OURANOS_PID=$!
echo "$OURANOS_PID" > "${OURANOS_DIR}/ouranos.pid"

# Verify that Ouranos started successfully
sleep 2

# Check if process is still running
if ! kill -0 "$OURANOS_PID" 2>/dev/null; then
    log ERROR "Failed to start Ouranos. Check the logs at ${OURANOS_DIR}/logs/ouranos.log for details.
$(tail -n 20 "${OURANOS_DIR}/logs/ouranos.log")"
fi

log SUCCESS "Ouranos started successfully with PID $OURANOS_PID"

exit 0
