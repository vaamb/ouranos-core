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

# Check that a PID is really an Ouranos process, and not a recycled PID.
# Ouranos renames itself to "ouranos" (setproctitle), but only once its imports
# are done: until then it is still "<python> -m ouranos". Matching the command
# line covers both, so an instance still starting up is not mistaken for a dead
# one.
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

# Check if already running — prefer PID file
if [[ -f "${OURANOS_DIR}/ouranos.pid" ]]; then
    PID=$(cat "${OURANOS_DIR}/ouranos.pid")
    if kill -0 "$PID" 2>/dev/null && is_ouranos_proc "$PID"; then
        log WARN "Ouranos is already running with PID $PID"
        log INFO "If you want to restart, please run: ouranos restart"
        exit 0
    fi
    # Stale PID file — process is gone, clean up and continue
    rm -f "${OURANOS_DIR}/ouranos.pid"
fi
# Fallback to pgrep if no PID file — match both the renamed process and one
# still starting up ("<python> -m ouranos"); -f on the latter is safe as it
# cannot match this script's own command line.
PID=$({ pgrep -x "ouranos"; pgrep -f -- "-m ouranos"; } 2>/dev/null | head -n1 || true)
if [[ -n "$PID" ]]; then
    log WARN "Ouranos is already running with PID $PID"
    log INFO "If you want to restart, please run: ouranos restart"
    exit 0
fi

# Change to Ouranos directory
cd "$OURANOS_DIR" ||
    die "Failed to change to Ouranos directory: $OURANOS_DIR"

# Check if virtual environment exists
readonly PYTHON="${OURANOS_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
    die "Python virtual environment not found. Please run the installation script first."
fi

# Run the venv's interpreter directly rather than through `uv run`: the venv is
# already synced by install.sh / update_ouranos.sh, and `uv run` would fork a
# child, leaving $! pointing at the wrapper instead of at Ouranos itself.

# Start Ouranos
log INFO "Starting Ouranos..."

if [[ "$FOREGROUND" = true ]]; then
    log INFO "Running in foreground mode (logs will be shown in terminal)"
    "${PYTHON}" -m ouranos
    EXIT_CODE=$?

    log INFO "Ouranos process exited with code $EXIT_CODE"
    exit "$EXIT_CODE"
else
    # Run Ouranos in the background and capture its PID immediately
    nohup "${PYTHON}" -m ouranos > "${OURANOS_DIR}/logs/stdout" 2>&1 &
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
        rm -f "${OURANOS_DIR}/ouranos.pid"
        die "Failed to start Ouranos. Check the logs at ${LOG_FILE}."
    fi

    log SUCCESS "Ouranos started successfully with PID $OURANOS_PID"

    exit 0
fi
