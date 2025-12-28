#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

check_ouranos_core_lib() {
    # Check if ouranos-core exists
    if [ ! -d "${OURANOS_DIR}/lib/ouranos-core" ]; then
        log ERROR "Ouranos core installation not found at \
        ${OURANOS_DIR}/lib/ouranos-core. Please install it first using the \
        Ouranos install script."
    fi
}

update_ouranos_core_lib() {
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

        # Fill the database with the new tables
        python -m ouranos fill-db

        # Upgrade the database
        alembic upgrade head ||
            log ERROR "Failed to upgrade the database"
        deactivate
    fi
}

main() {
    # All the backup and cleanup logics are taken care by ouranos scripts
    check_requirements

    # Check if ouranos-core exists
    log INFO "Checking if Ouranos core is installed..."
    check_ouranos_core_lib
    log SUCCESS "Ouranos core installation found"

    log INFO "Updating Ouranos core..."
    update_ouranos_core_lib
    log SUCCESS "Ouranos core updated successfully!"

    exit 0
}

if [ "${BASH_SOURCE[0]}" -ef "$0" ]; then
    echo "This script should be run from the Ouranos update script."
    exit 1
else
    main "$@"
fi
