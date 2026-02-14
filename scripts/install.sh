#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

# Version requirements
readonly MIN_PYTHON_VERSION="3.11"
readonly OURANOS_VERSION="0.10.0"
readonly OURANOS_REPO="https://github.com/vaamb/ouranos-core.git"

# Default values
OURANOS_DIR="${PWD}/ouranos"

# Load logging functions
readonly DATETIME=$(date +%Y%m%d_%H%M%S)
readonly LOG_FILE="/tmp/ouranos_install_${DATETIME}.log"
readonly SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
. "${SCRIPT_DIR}/utils/logging.sh"

# Parse command line arguments
SAFE=true

show_help() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -u, --unsafe     Install the latest development version"
    echo "  -h, --help       Show this help message and exit"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -u|--unsafe)
            unset SAFE
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            die "Unknown option: $1"
            ;;
    esac
done

check_no_installation() {
    if [ -d "${OURANOS_DIR}" ]; then
        die "Ouranos appears to be already installed at ${OURANOS_DIR}"
    fi
}

check_requirements() {
    local missing_deps=()
    local cmd

    # Function to check if command exists
    command_exists() {
        command -v "$1" >/dev/null 2>&1
    }

    # Check for required commands
    for cmd in git python3 systemctl uv; do
        if ! command_exists "${cmd}"; then
            missing_deps+=("${cmd}")
        fi
    done

    if [ ${#missing_deps[@]} -gt 0 ]; then
        log WARN "Missing required dependencies: ${missing_deps[*]}"
    fi

    # Check Python version
    python3 -c "import sys; exit(0) if sys.version_info >= (${MIN_PYTHON_VERSION//./,}) else exit(1)" ||
        die "Python ${MIN_PYTHON_VERSION} or higher is required"
}

create_directories() {
    # Create Ouranos directory
    mkdir -p "${OURANOS_DIR}" ||
        die "Failed to create directory: ${OURANOS_DIR}"
    cd "${OURANOS_DIR}" ||
        die "Failed to change to directory: ${OURANOS_DIR}"

    # Create required directories
    for dir in logs scripts lib migrations; do
        mkdir -p "${OURANOS_DIR}/${dir}" ||
            die "Failed to create directory: ${OURANOS_DIR}/${dir}"
    done
}

get_ouranos_core() {
    # Get Ouranos-core repository
    log INFO "Cloning Ouranos-core repository..."

    if ! git clone ${SAFE:+--branch "${OURANOS_VERSION}"} "${OURANOS_REPO}" \
            "${OURANOS_DIR}/lib/ouranos-core"; then
        die "Failed to clone Ouranos repository"
    fi
}

#>>>Copy>>>
copy_scripts() {
    # Copy scripts from ouranos-core to ouranos/scripts
    cp -r "${OURANOS_DIR}/lib/ouranos-core/scripts/"* "${OURANOS_DIR}/scripts/" ||
        die "Failed to copy scripts"
    # Make scripts executable
    chmod +x "${OURANOS_DIR}/scripts/"*.sh
    chmod +x "${OURANOS_DIR}/scripts/utils/"*.sh
    # Convert scripts to unix format
    dos2unix "${OURANOS_DIR}/scripts/"*.sh
    dos2unix "${OURANOS_DIR}/scripts/utils/"*.sh
    # Remove ouranos-core update.sh
    rm "${OURANOS_DIR}/scripts/update.sh"
    # Copy migrations and alembic.ini
    cp -r "${OURANOS_DIR}/lib/ouranos-core/migrations/"* "${OURANOS_DIR}/migrations/" ||
        die "Failed to copy migration scripts"
    cp -r "${OURANOS_DIR}/lib/ouranos-core/alembic.ini" "${OURANOS_DIR}/" ||
        die "Failed to copy alembic.ini"
}
#<<<Copy<<<

setup_uv_and_sync() {
    # Generate the master pyproject.toml
    log INFO "Creating the master pyproject.toml"
    "${OURANOS_DIR}/scripts/utils/gen_pyproject.sh" "${OURANOS_DIR}" ||
        die "Failed to generate Ouranos pyproject.toml"

    # Sync virtual environment
    uv sync --all-packages ||
        die "Failed to create Python virtual environment and sync it"

    source "${OURANOS_DIR}/.venv/bin/activate" ||
        die "Failed to activate Python virtual environment"

    deactivate ||
        die "Failed to deactivate Python virtual environment"
}

# Update .profile
update_profile() {
    "${OURANOS_DIR}/scripts/utils/gen_profile.sh" "${OURANOS_DIR}" ||
        log WARN "Failed to update shell profile"
}

install_service() {
    local service_file="${OURANOS_DIR}/scripts/ouranos.service"

    "${OURANOS_DIR}/scripts/utils/gen_service.sh" "${OURANOS_DIR}" "${service_file}" ||
        log WARN "Failed to generate systemd service"

    # Install service
    if ! sudo cp "${service_file}" "/etc/systemd/system/ouranos.service"; then
        log WARN "Failed to copy service file. You may need to run with sudo."
    else
        sudo systemctl daemon-reload ||
            log WARN "Failed to reload systemd daemon"
    fi
}

# Cleanup function to run on exit
cleanup() {
    local exit_code=$?

    if [[ "${exit_code}" -ne 0 ]]; then
        log WARN "Installation failed. Check the log file for details: ${LOG_FILE}"
    else
        log SUCCESS "Installation completed successfully!"
    fi

    # Reset terminal colors
    echo -en "${NC}"
    exit ${exit_code}
}

main() {
    # Set up trap for cleanup on exit
    trap cleanup EXIT

    log INFO "Starting Ouranos installation (v${OURANOS_VERSION})"

    # Check if already installed
    check_no_installation

    # Check requirements and permissions
    log INFO "Checking system requirements..."
    check_requirements
    log SUCCESS "System requirements met"

    log INFO "Creating directories..."
    create_directories
    log SUCCESS "Directories created successfully."

    log INFO "Getting Ouranos-core repository..."
    get_ouranos_core
    log SUCCESS "Ouranos-core repository cloned successfully."

    log INFO "Making scripts more easily accessible..."
    copy_scripts

    log INFO "Setting up virtual environment and syncing packages..."
    setup_uv_and_sync
    log SUCCESS "Virtual environment set up and packages synced successfully."

    log INFO "Updating shell profile..."
    update_profile
    log SUCCESS "Shell profile updated successfully"

    log INFO "Setting up systemd service..."
    install_service
    log SUCCESS "Systemd service set up successfully"

    # Display completion message

    echo -e "\n${GREEN}✔ Installation completed successfully!${NC}"
    echo -e "\n${YELLOW}Next steps:${NC}"
    echo -e "- Source your profile: ${YELLOW}source ~/.profile${NC}"
    echo -e "(-) Configure Ouranos"
    echo -e "- Fill the database with ${YELLOW}python -m ouranos fill-db --no-check-revision${NC}"
    echo -e "- Stamp the database as up to date with ${YELLOW}alembic stamp head${NC}"
    echo -e "- Start Ouranos: ${YELLOW}ouranos start${NC}"
    echo -e "\n${YELLOW}Other useful commands:${NC}"
    echo -e "  ouranos stop     # Stop the service"
    echo -e "  ouranos restart  # Restart the service"
    echo -e "  ouranos status   # Check service status"
    echo -e "  ouranos logs     # View logs"
    echo -e "\n${YELLOW}To run as a system service:${NC}"
    echo -e "  sudo systemctl start ouranos.service"
    echo -e "  sudo systemctl enable ouranos.service  # Start on boot"
    echo -e "\n${YELLOW}For troubleshooting, check the log file:${NC} ${LOG_FILE}"

    exit 0
}

if [ "${BASH_SOURCE[0]}" -ef "$0" ]
then
    main "$@"
fi
