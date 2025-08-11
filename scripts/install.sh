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

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check for required commands
for cmd in git python3 systemctl; do
    if ! command_exists "$cmd"; then
        log ERROR "$cmd is required but not installed."
    fi
done

# Check Python version
python3 -c "import sys; exit(0) if sys.version_info >= (${MIN_PYTHON_VERSION//./,}) else exit(1)" ||
    log ERROR "Python ${MIN_PYTHON_VERSION} or higher is required"

log INFO "Installing Ouranos"

# Create ouranos directory
mkdir -p "${OURANOS_DIR}" || log ERROR "Failed to create directory: ${OURANOS_DIR}"
cd "${OURANOS_DIR}" || log ERROR "Failed to change to directory: ${OURANOS_DIR}"

log INFO "Creating Python virtual environment..."
if [ ! -d "python_venv" ]; then
    python3 -m venv "${OURANOS_DIR}/python_venv" ||
        log ERROR "Failed to create Python virtual environment"
fi

# Activate virtual environment
# shellcheck source=/dev/null
source "${OURANOS_DIR}/python_venv/bin/activate" ||
    log ERROR "Failed to activate Python virtual environment"

# Create required directories
for dir in logs scripts lib; do
    mkdir -p "${OURANOS_DIR}/${dir}" ||
        log ERROR "Failed to create directory: ${OURANOS_DIR}/${dir}"
done

# Get Ouranos repository
log INFO "Cloning Ouranos repository..."
if [ ! -d "${OURANOS_DIR}/lib/ouranos-core" ]; then
    if ! git clone --branch "${OURANOS_VERSION}" "${OURANOS_REPO}" \
            "${OURANOS_DIR}/lib/ouranos-core" > /dev/null 2>&1; then
        log ERROR "Failed to clone Ouranos repository"
    fi

    cd "${OURANOS_DIR}/lib/ouranos-core" ||
        log ERROR "Failed to enter Ouranos directory"

    log INFO "Updating Python packaging tools..."
    pip install --upgrade pip setuptools wheel ||
        log ERROR "Failed to update Python packaging tools"
else
    log ERROR "Ouranos installation detected at ${OURANOS_DIR}/lib/ouranos-core. Please update using the update script."
fi

# Install Ouranos
log INFO "Installing Ouranos and its dependencies..."
pip install -e . || log ERROR "Failed to install Ouranos"
deactivate

# Copy scripts
cp -r "${OURANOS_DIR}/lib/ouranos-core/scripts/"* "${OURANOS_DIR}/scripts/" ||
    log ERROR "Failed to copy scripts"
chmod +x "${OURANOS_DIR}/scripts/"*.sh

# Update .profile
log INFO "Updating shell profile..."

${OURANOS_DIR}/scripts/gen_profile.sh "${OURANOS_DIR}" ||
    log ERROR "Failed to update shell profile"

info "Setting up systemd service..."
SERVICE_FILE="${OURANOS_DIR}/scripts/ouranos.service"

${OURANOS_DIR}/scripts/gen_service.sh "${OURANOS_DIR}" "${SERVICE_FILE}" ||
    log ERROR "Failed to generate systemd service"

# Install service
if ! sudo cp "${SERVICE_FILE}" "/etc/systemd/system/ouranos.service"; then
    log WARN "Failed to copy service file. You may need to run with sudo."
else
    sudo systemctl daemon-reload ||
        log WARN "Failed to reload systemd daemon"
fi

log SUCCESS    "\nInstallation completed successfully!"
echo -e "\nTo get started:"
echo -e "1. Source your profile: ${YELLOW}source ~/.profile${NC}"
echo -e "2. Start Ouranos: ${YELLOW}ouranos start${NC}"
echo -e "\nOther useful commands:"
echo -e "  ouranos stop     # Stop the service"
echo -e "  ouranos restart  # Restart the service"
echo -e "  ouranos status   # Check service status"
echo -e "  ouranos logs     # View logs"
echo -e "\nTo run as a system service:"
echo -e "  sudo systemctl start ouranos.service"
echo -e "  sudo systemctl enable ouranos.service  # Start on boot"

exit 0
