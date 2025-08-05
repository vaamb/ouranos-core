#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

# Constants
readonly OURANOS_VERSION="0.9.0"
readonly MIN_PYTHON_VERSION="3.11"

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

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check for required commands
for cmd in git python3 systemctl; do
    if ! command_exists "$cmd"; then
        error_exit "$cmd is required but not installed."
    fi
done

# Check Python version
python3 -c "import sys; exit(0) if sys.version_info >= (${MIN_PYTHON_VERSION//./,}) else exit(1)" || 
    error_exit "Python ${MIN_PYTHON_VERSION} or higher is required"

info "Installing Ouranos"

# Create ouranos directory
OURANOS_DIR="${PWD}/ouranos"
mkdir -p "${OURANOS_DIR}" || error_exit "Failed to create directory: ${OURANOS_DIR}"
cd "${OURANOS_DIR}" || error_exit "Failed to change to directory: ${OURANOS_DIR}"

info "Creating Python virtual environment..."
if [ ! -d "python_venv" ]; then
    python3 -m venv "${OURANOS_DIR}/python_venv" || 
        error_exit "Failed to create Python virtual environment"
fi

# Activate virtual environment
# shellcheck source=/dev/null
source "${OURANOS_DIR}/python_venv/bin/activate" || 
    error_exit "Failed to activate Python virtual environment"

# Create required directories
for dir in logs scripts lib; do
    mkdir -p "${OURANOS_DIR}/${dir}" || 
        error_exit "Failed to create directory: ${OURANOS_DIR}/${dir}"
done

# Get Ouranos repository
info "Cloning Ouranos repository..."
if [ ! -d "${OURANOS_DIR}/lib/ouranos-core" ]; then
    if ! git clone --branch "${OURANOS_VERSION}" \
            "https://github.com/vaamb/ouranos-core.git" \
            "${OURANOS_DIR}/lib/ouranos-core" > /dev/null 2>&1; then
        error_exit "Failed to clone Ouranos repository"
    fi
    
    cd "${OURANOS_DIR}/lib/ouranos-core" || 
        error_exit "Failed to enter Ouranos directory"
    
    info "Updating Python packaging tools..."
    pip install --upgrade pip setuptools wheel || 
        error_exit "Failed to update Python packaging tools"
else
    error_exit "Ouranos installation detected at ${OURANOS_DIR}/lib/ouranos-core. Please update using the update script."
fi

# Install Ouranos
info "Installing Ouranos and its dependencies..."
pip install -e . || error_exit "Failed to install Ouranos"
deactivate

# Copy scripts
cp -r "${OURANOS_DIR}/lib/ouranos-core/scripts/"* "${OURANOS_DIR}/scripts/" || 
    error_exit "Failed to copy scripts"
chmod +x "${OURANOS_DIR}/scripts/"*.sh

# Update .profile
info "Updating shell profile..."

# Remove existing Ouranos section if it exists
if grep -q "#>>>Ouranos variables>>>" "${HOME}/.profile"; then
    sed -i "/#>>>Ouranos variables>>>/,/#<<<Ouranos variables<<</d" "${HOME}/.profile"
fi

cat >> "${HOME}/.profile" << EOF
#>>>Ouranos variables>>>
# Ouranos root directory
export OURANOS_DIR="${OURANOS_DIR}"

# Ouranos utility function to manage the application
ouranos() {
  case \$1 in
    start) "${OURANOS_DIR}/scripts/start.sh" ;;
    stop) "${OURANOS_DIR}/scripts/stop.sh" ;;
    restart) "${OURANOS_DIR}/scripts/stop.sh" && "${OURANOS_DIR}/scripts/start.sh" ;;
    status) systemctl status ouranos.service ;;
    logs) tail -f "${OURANOS_DIR}/logs/ouranos.log" ;;
    update) "${OURANOS_DIR}/scripts/update.sh" ;;
    *) echo "Usage: ouranos {start|stop|restart|status|logs|update}" ;;
  esac
}
complete -W "start stop restart status logs update" ouranos
#<<<Ouranos variables<<<
EOF

# shellcheck source=/dev/null
source "${HOME}/.profile"

# Create systemd service file
info "Setting up systemd service..."
SERVICE_FILE="${OURANOS_DIR}/scripts/ouranos.service"

cat > "${SERVICE_FILE}" << EOF
[Unit]
Description=Ouranos service
After=network.target

[Service]
Environment=OURANOS_DIR="${OURANOS_DIR}"
Type=simple
User=${USER}
WorkingDirectory=${OURANOS_DIR}
Restart=always
RestartSec=10
ExecStart=${OURANOS_DIR}/scripts/start.sh
ExecStop=${OURANOS_DIR}/scripts/stop.sh
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=ouranos

[Install]
WantedBy=multi-user.target
EOF

# Install service
if ! sudo cp "${SERVICE_FILE}" "/etc/systemd/system/ouranos.service"; then
    warn "Failed to copy service file. You may need to run with sudo."
else
    sudo systemctl daemon-reload || 
        warn "Failed to reload systemd daemon"
fi

info    "\nInstallation completed successfully!"
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
