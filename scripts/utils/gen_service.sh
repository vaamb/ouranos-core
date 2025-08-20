#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

INSTALL_DIR="${1:-}"
SERVICE_FILE="${2:-}"

# Validate arguments
if [[ -z "${INSTALL_DIR}" || -z "${SERVICE_FILE}" ]]; then
  echo "Usage: $0 <ouranos_install_dir> <service_file_path>" >&2
  exit 1
fi

# Create systemd service file
cat > "${SERVICE_FILE}" << EOF
[Unit]
Description=Ouranos service
After=network.target

[Service]
Environment=OURANOS_DIR="${INSTALL_DIR}"
Type=simple
User=${USER}
WorkingDirectory=${INSTALL_DIR}
Restart=always
RestartSec=10
ExecStart=${INSTALL_DIR}/scripts/start.sh -f
ExecStop=${INSTALL_DIR}/scripts/stop.sh
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=ouranos

[Install]
WantedBy=multi-user.target
EOF
