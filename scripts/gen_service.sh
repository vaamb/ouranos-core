OURANOS_DIR=${1}
SERVICE_FILE=${2}

# Create systemd service file
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
