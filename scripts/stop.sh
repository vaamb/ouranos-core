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

# Function to check if Ouranos is running
is_running() {
    if pgrep -f "python3 -m ouranos" > /dev/null; then
        return 0
    else
        return 1
    fi
}

# Check if OURANOS_DIR is set
if [[ -z "${OURANOS_DIR:-}" ]]; then
    error_exit "OURANOS_DIR environment variable is not set. Please source your profile or run the install script first."
fi

# Check if the directory exists
if [[ ! -d "$OURANOS_DIR" ]]; then
    error_exit "Ouranos directory not found at $OURANOS_DIR. Please check your installation."
fi

# Ensure logs directory exists
mkdir -p "${OURANOS_DIR}/logs" || error_exit "Failed to create logs directory"

# Log stop attempt
info "$(date) - Attempting to stop Ouranos..."

# Check if Ouranos is running
if ! is_running; then
    info "No running instance of Ouranos found."
    
    # Clean up PID file if it exists
    if [[ -f "${OURANOS_DIR}/ouranos.pid" ]]; then
        warn "Stale PID file found. Cleaning up..."
        rm -f "${OURANOS_DIR}/ouranos.pid"
    fi
    
    exit 0
fi

# Get the PID of the running process
OURANOS_PID=$(pgrep -f "python3 -m ouranos")

if [[ -z "$OURANOS_PID" ]]; then
    error_exit "Could not determine Ouranos process ID"
fi

info "Stopping Ouranos (PID: $OURANOS_PID)..."

# Send SIGTERM (15) - graceful shutdown
if kill -15 "$OURANOS_PID" 2>/dev/null; then
    # Wait for the process to terminate
    TIMEOUT=10  # seconds
    while (( TIMEOUT-- > 0 )) && kill -0 "$OURANOS_PID" 2>/dev/null; do
        sleep 1
        echo -n "."
    done
    echo
    
    # Check if process is still running
    if kill -0 "$OURANOS_PID" 2>/dev/null; then
        warn "Graceful shutdown failed. Force killing the process..."
        kill -9 "$OURANOS_PID" 2>/dev/null || true
    fi
    
    # Clean up PID file
    if [[ -f "${OURANOS_DIR}/ouranos.pid" ]]; then
        rm -f "${OURANOS_DIR}/ouranos.pid"
    fi
    
    # Verify the process was actually stopped
    if is_running; then
        error_exit "Failed to stop Ouranos. Process still running with PID: $(pgrep -f "python3 -m ouranos")"
    fi
    
    info "Ouranos stopped successfully."
    exit 0
else
    error_exit "Failed to send stop signal to Ouranos (PID: $OURANOS_PID). You may need to run with sudo."
fi
