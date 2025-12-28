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

#>>>Logging>>>
# Constants for log levels
readonly INFO="INFO"
readonly WARN="WARN"
readonly ERROR="ERROR"
readonly SUCCESS="SUCCESS"

# Colors for output
if [[ -t 1 ]]; then
    readonly RED='\033[38;5;001m'
    readonly GREEN='\033[38;5;002m'
    readonly YELLOW='\033[38;5;220m'
    readonly LIGHT_YELLOW='\033[38;5;011m'
    readonly NC='\033[0m' # No Color
else
    readonly RED=""
    readonly GREEN=""
    readonly YELLOW=""
    readonly LIGHT_YELLOW=""
    readonly NC=""
fi

# Function to log messages
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case "$1" in
        INFO)
            echo -e "${LIGHT_YELLOW}$2${NC}"
            echo -e "[${timestamp}] [INFO] $2" >> "${LOG_FILE}"
            ;;
        WARN)
            echo -e "${YELLOW}Warning: $2${NC}"
            echo -e "[${timestamp}] [WARNING] $2" >> "${LOG_FILE}"
            ;;
        ERROR)
            echo -e "${RED}Error: $2${NC}"
            echo -e "[${timestamp}] [ERROR] $2" >> "${LOG_FILE}"
            exit 1
            ;;
        SUCCESS)
            echo -e "${GREEN}$2${NC}"
            echo -e "[${timestamp}] [SUCCESS] $2" >> "${LOG_FILE}"
            ;;
        *)
            echo -e "$1"
            echo -e "[${timestamp}] $1" >> "${LOG_FILE}"
            ;;
    esac
}

log INFO "Log file: ${LOG_FILE}"
#<<<Logging<<<

check_no_installation() {
    if [ -d "${OURANOS_DIR}" ]; then
        log ERROR "Ouranos appears to be already installed at ${OURANOS_DIR}"
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
        log ERROR "Python ${MIN_PYTHON_VERSION} or higher is required"
}

create_directories() {
    # Create Ouranos directory
    mkdir -p "${OURANOS_DIR}" || log ERROR "Failed to create directory: ${OURANOS_DIR}"
    cd "${OURANOS_DIR}" || log ERROR "Failed to change to directory: ${OURANOS_DIR}"

    # Create required directories
    for dir in logs scripts lib; do
        mkdir -p "${OURANOS_DIR}/${dir}" ||
            log ERROR "Failed to create directory: ${OURANOS_DIR}/${dir}"
    done
}

get_ouranos_core() {
    # Get Ouranos-core repository
    log INFO "Cloning Ouranos-core repository..."

    if ! git clone --branch "${OURANOS_VERSION}" "${OURANOS_REPO}" \
            "${OURANOS_DIR}/lib/ouranos-core" > /dev/null 2>&1; then
        log ERROR "Failed to clone Ouranos repository"
    fi
}

#>>>Copy>>>
copy_scripts() {
    # Copy scripts from ouranos-core to ouranos/scripts
    cp -r "${OURANOS_DIR}/lib/ouranos-core/scripts/"* "${OURANOS_DIR}/scripts/" ||
        log ERROR "Failed to copy scripts"
    # Make scripts executable
    chmod +x "${OURANOS_DIR}/scripts/"*.sh
    chmod +x "${OURANOS_DIR}/scripts/utils/"*.sh
    # Convert scripts to unix format
    dos2unix "${OURANOS_DIR}/scripts/"*.sh
    dos2unix "${OURANOS_DIR}/scripts/utils/"*.sh
    # Remove ouranos-core update.sh
    rm "${OURANOS_DIR}/scripts/update.sh"
}
#<<<Copy<<<

setup_uv_and_sync() {
    # Generate the master pyproject.toml
    log INFO "Creating the master pyproject.toml"
    "${OURANOS_DIR}/scripts/utils/gen_pyproject.sh" "${OURANOS_DIR}" ||
        log ERROR "Failed to generate Ouranos pyproject.toml"

    # Sync virtual environment
    uv sync --all-packages ||
        log ERROR "Failed to create Python virtual environment and sync it"


    source "${OURANOS_DIR}/.venv/bin/activate" ||
        log ERROR "Failed to activate Python virtual environment"

    # Fill the database
    python -m ouranos fill-db --no-check-revision
    # Stamp the database as up to date
    alembic stamp head

    deactivate ||
        log ERROR "Failed to deactivate Python virtual environment"
}

# Update .profile
update_profile() {
    "${OURANOS_DIR}/scripts/utils/gen_profile.sh" "${OURANOS_DIR}" ||
        log ERROR "Failed to update shell profile"
}

install_service() {
    local service_file="${OURANOS_DIR}/scripts/ouranos.service"

    "${OURANOS_DIR}/scripts/utils/gen_service.sh" "${OURANOS_DIR}" "${service_file}" ||
        log ERROR "Failed to generate systemd service"

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

    if [ ${exit_code} -ne 0 ]; then
        log WARN "Installation failed. Check the log file for details: ${LOG_FILE}"
        yes | rm -r "${OURANOS_DIR}"
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
    if [ -d "${OURANOS_DIR}" ]; then
        log ERROR "Ouranos appears to be already installed at ${OURANOS_DIR}"
    fi

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
    echo -e "1. Source your profile: ${YELLOW}source ~/.profile${NC}"
    echo -e "2. Start Ouranos: ${YELLOW}ouranos start${NC}"
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
