#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

# Version requirements
readonly MIN_PYTHON_VERSION="3.11"
readonly OURANOS_VERSION="0.9.0"
readonly OURANOS_REPO="https://github.com/vaamb/ouranos-core.git"

# Default values
OURANOS_DIR="${PWD}/ouranos"

# Load logging functions
readonly DATETIME=$(date +%Y%m%d_%H%M%S)
readonly LOG_FILE="/tmp/ouranos_install_${DATETIME}.log"
. "./logging.sh"

check_requirements() {
    local missing_deps=()
    local cmd

    # Function to check if command exists
    command_exists() {
        command -v "$1" >/dev/null 2>&1
    }

    # Check for required commands
    for cmd in git python3 systemctl; do
        if ! command_exists "${cmd}"; then
            missing_deps+=("${cmd}")
        fi
    done

    if [ ${#missing_deps[@]} -gt 0 ]; then
        log WARN "Missing required dependencies: ${missing_deps[*]}"
        log INFO "Attempting to install missing dependencies..."
            sudo apt-get update && sudo apt-get install -y "${missing_deps[@]}" ||
                log ERROR "Failed to install required packages"
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

setup_python_venv() {
    # Setup Python virtual environment
    if [ ! -d "python_venv" ]; then
        python3 -m venv "${OURANOS_DIR}/python_venv" ||
            log ERROR "Failed to create Python virtual environment"
    else
        log WARN "Virtual environment already exists at ${OURANOS_DIR}/python_venv"
    fi
}

install_ouranos() {
    # Activate virtual environment
    # shellcheck source=/dev/null
    source "${OURANOS_DIR}/python_venv/bin/activate" ||
        log ERROR "Failed to activate Python virtual environment"

    # Get Ouranos repository
    log INFO "Cloning Ouranos repository..."
    if [ ! -d "${OURANOS_DIR}/lib/ouranos-core" ]; then
        if ! git clone --branch "${OURANOS_VERSION}" "${OURANOS_REPO}" \
                "${OURANOS_DIR}/lib/ouranos-core" > /dev/null 2>&1; then
            log ERROR "Failed to clone Ouranos repository"
        fi

        cd "${OURANOS_DIR}/lib/ouranos-core" ||
            log ERROR "Failed to enter Ouranos directory"
    else
        log ERROR "Ouranos installation detected at ${OURANOS_DIR}/lib/ouranos-core. Please update using the update script."
    fi

    log INFO "Updating Python packaging tools..."
    pip install --upgrade pip setuptools wheel ||
        log ERROR "Failed to update Python packaging tools"

    # Install Ouranos
    log INFO "Installing Ouranos and its dependencies..."
    pip install -e . || log ERROR "Failed to install Ouranos"
    deactivate ||
        log ERROR "Failed to deactivate virtual environment"
}

copy_scripts() {
    # Copy scripts
    cp -r "${OURANOS_DIR}/lib/ouranos-core/scripts/"* "${OURANOS_DIR}/scripts/" ||
        log ERROR "Failed to copy scripts"
    chmod +x "${OURANOS_DIR}/scripts/"*.sh
}

# Update .profile
update_profile() {
    ${OURANOS_DIR}/scripts/gen_profile.sh "${OURANOS_DIR}" ||
        log ERROR "Failed to update shell profile"
}

install_service() {
    local service_file="${OURANOS_DIR}/scripts/ouranos.service"

    ${OURANOS_DIR}/scripts/gen_service.sh "${OURANOS_DIR}" "${service_file}" ||
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
        log ERROR "Installation failed. Check the log file for details: ${LOG_FILE}"
        rm -r "${OURANOS_DIR}"
    else
        log SUCCESS "Installation completed successfully!"
    fi

    # Reset terminal colors
    echo -e "${NC}"
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

    log INFO "Creating Python virtual environment..."
    setup_python_venv
    log SUCCESS "Python virtual environment created successfully."

    log INFO "Installing Ouranos ..."
    install_ouranos
    log SUCCESS "Ouranos installed successfully"

    log INFO "Making scripts more easily accessible..."
    copy_scripts

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

main "$@"
