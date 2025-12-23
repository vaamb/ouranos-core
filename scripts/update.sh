#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

check_requirements() {
    # Check that Ouranos variable is set
    if [[ -z "${OURANOS_DIR:-}" ]]; then
        echo "OURANOS_DIR environment variable is not set. Please check your installation."
        exit 1
    fi

    # Check that the directories exist
    local dirs=("${OURANOS_DIR}" "${OURANOS_DIR}/lib" "${OURANOS_DIR}/.venv" "${OURANOS_DIR}/scripts")
    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            echo "Ouranos directories not found at $OURANOS_DIR. Please check your installation."
            exit 1
        fi
    done
}

setup_logging() {
    # Load logging functions
    readonly DATETIME=$(date +%Y%m%d_%H%M%S)
    readonly LOG_FILE="/tmp/ouranos_core_update_${DATETIME}.log"
    source "${OURANOS_DIR}/scripts/utils/logging.sh" "${LOG_FILE}"
}

check_ouranos_core_lib() {
    # Check if ouranos-core exists
    if [ ! -d "${OURANOS_DIR}/lib/ouranos-core" ]; then
        log ERROR "Ouranos core installation not found at ${OURANOS_DIR}/lib/ouranos-core. Please install using Ouranos install script."
    fi
}

update_ouranos_core_lib() {
    # Use the update_git_repo function from ouranos scripts
    # It takes care of all the git- and python-side updates
    source "${OURANOS_DIR}/scripts/update_ouranos.sh"
    update_git_repo "${OURANOS_DIR}/lib/ouranos-core"

    # Update DB
    log INFO "Updating the database..."
    if [[ "$DRY_RUN" == false ]]; then
        # Change to Ouranos lib directory
        cd "${OURANOS_DIR}/lib/ouranos-core" ||
            log ERROR "Failed to change to directory: ${OURANOS_DIR}/lib/ouranos-core"

        # Activate virtual environment
        # shellcheck source=/dev/null
        if ! source "${OURANOS_DIR}/.venv/bin/activate"; then
            log ERROR "Failed to activate Python virtual environment"
        fi
        alembic upgrade head ||
            log ERROR "Failed to upgrade the database"
        deactivate
    fi
}

main() {
    # All the backup and cleanup logics are taken care by ouranos scripts
    check_requirements

    setup_logging

    # Check if ouranos-core exists
    log INFO "Checking if Ouranos core is installed..."
    check_ouranos_core_lib
    log SUCCESS "Ouranos core installation found"

    log INFO "Updating Ouranos core..."
    update_ouranos_core_lib
    log SUCCESS "Ouranos core updated successfully!"

    exit 0
}

main "$@"
