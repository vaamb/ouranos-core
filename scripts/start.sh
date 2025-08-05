#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print error messages
error_exit() {
    echo -e "${RED}Error: $1${NC}" >&2
    exit 1
}

# Function to print info messages
info() {
    echo -e "${GREEN}$1${NC}"
}

# Function to print warning messages
warn() {
    echo -e "${YELLOW}Warning: $1${NC}"
}

# Check if OURANOS_DIR is set
if [[ -z "${OURANOS_DIR:-}" ]]; then
    error_exit "OURANOS_DIR environment variable is not set. Please source your profile or run the install script first."
fi

# Check if the directory exists
if [[ ! -d "$OURANOS_DIR" ]]; then
    error_exit "Ouranos directory not found at $OURANOS_DIR. Please check your installation."
fi

# Create logs directory if it doesn't exist
mkdir -p "${OURANOS_DIR}/logs" || error_exit "Failed to create logs directory"

# Redirect all output to log file
exec > >(tee -a "${OURANOS_DIR}/logs/ouranos.log") 2>&1

# Function to check if Ouranos is running
is_running() {
    if pgrep -f "python3 -m ouranos" > /dev/null; then
        return 0
    else
        return 1
    fi
}

# Check if already running
if is_running; then
    PID=$(pgrep -f "python3 -m ouranos")
    warn "Ouranos is already running with PID $PID"
    info "If you want to restart, please run: ouranos restart"
    exit 0
fi

# Change to Ouranos directory
cd "$OURANOS_DIR" || error_exit "Failed to change to Ouranos directory: $OURANOS_DIR"

# Check if virtual environment exists
if [[ ! -d "python_venv" ]]; then
    error_exit "Python virtual environment not found. Please run the install script first."
fi

# Activate virtual environment
# shellcheck source=/dev/null
if ! source "python_venv/bin/activate"; then
    error_exit "Failed to activate Python virtual environment"
fi

# Start Ouranos
info "$(date) - Starting Ouranos..."
info "Logging to: ${OURANOS_DIR}/logs/ouranos.log"

# Run Ouranos in the background and log the PID
nohup python3 -m ouranos > "${OURANOS_DIR}/logs/ouranos.log" 2>&1 &
OURANOS_PID=$!

echo "$OURANOS_PID" > "${OURANOS_DIR}/ouranos.pid"

# Verify that Ouranos started successfully
sleep 2
if ! kill -0 "$OURANOS_PID" 2>/dev/null; then
    error_exit "Failed to start Ouranos. Check the logs at ${OURANOS_DIR}/logs/ouranos.log for details.
$(tail -n 20 "${OURANOS_DIR}/logs/ouranos.log")"
fi

info "Ouranos started successfully with PID $OURANOS_PID"
info "To view logs: tail -f ${OURANOS_DIR}/logs/ouranos.log"

exit 0
