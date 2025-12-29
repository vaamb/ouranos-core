#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

# Check if OURANOS_DIR is set and the directory exists
if [[ ! -d "${OURANOS_DIR}" ]]; then
    echo "OURANOS_DIR environment variable is not set or the directory does not exist. Please source your profile or run the installation script first."
    exit 1
fi

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
            log ERROR "Unknown parameter: $1"
            exit 1
            ;;
    esac
done

# Load logging functions
readonly DATETIME=$(date +%Y%m%d_%H%M%S)
readonly LOG_FILE="/tmp/ouranos_start_${DATETIME}.log"
source "${OURANOS_DIR}/scripts/utils/logging.sh" "${LOG_FILE}"

# Create logs directory if it doesn't exist
mkdir -p "${OURANOS_DIR}/logs" || log ERROR "Failed to create logs directory"

# Check if already running
if pgrep -x "ouranos" > /dev/null; then
    PID=$(pgrep -x "ouranos" | head -n 1)
    log WARN "Ouranos is already running with PID $PID"
    log INFO "If you want to restart, please run: ouranos restart"
    exit 0
fi

# Change to Ouranos directory
cd "$OURANOS_DIR" || log ERROR "Failed to change to Ouranos directory: $OURANOS_DIR"

# Check if virtual environment exists
if [[ ! -d ".venv" ]]; then
    log ERROR "Python virtual environment not found. Please run the installation script first."
fi

# Activate virtual environment
# shellcheck source=/dev/null
if ! source ".venv/bin/activate"; then
    log ERROR "Failed to activate Python virtual environment"
fi

# Start Ouranos
log INFO "Starting Ouranos..."

if [ "$FOREGROUND" = true ]; then
    log INFO "Running in foreground mode (logs will be shown in terminal)"
    # Run Ouranos in the foreground
    python3 -m ouranos
    EXIT_CODE=$?

    # Clean up and exit with the same code as Ouranos
    deactivate || log WARN "Failed to deactivate virtual environment"
    log INFO "Ouranos process exited with code $EXIT_CODE"
    exit $EXIT_CODE
else
    # Run Ouranos in the background and log the PID
    nohup python3 -m ouranos > "${OURANOS_DIR}/logs/stdout" 2>&1 &
    log INFO "Ouranos started in background mode"
    log INFO "Ouranos stdout and stderr output redirected to ${OURANOS_DIR}/logs/stdout"

    deactivate || log ERROR "Failed to deactivate virtual environment"

    OURANOS_PID=$!
    echo "$OURANOS_PID" > "${OURANOS_DIR}/ouranos.pid"

    # Verify that Ouranos started successfully
    sleep 2

    # Check if process is still running
    if ! kill -0 "$OURANOS_PID" 2>/dev/null; then
        log ERROR "Failed to start Ouranos. Check the logs at ${LOG_FILE}.
                   $(tail -n 20 "${LOG_FILE}")"
    fi

    log SUCCESS "Ouranos started successfully with PID $OURANOS_PID"

    exit 0
fi
