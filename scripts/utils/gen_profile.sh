#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

INSTALL_DIR="${1:-}"

# Validate argument
if [[ -z "${INSTALL_DIR}" ]]; then
  echo "Usage: $0 <ouranos_install_dir>" >&2
  exit 1
fi

# Remove existing Ouranos section if it exists
if grep -q "#>>>Ouranos variables>>>" "${HOME}/.profile"; then
    sed -i "/#>>>Ouranos variables>>>/,/#<<<Ouranos variables<<</d" "${HOME}/.profile"
fi

cat >> "${HOME}/.profile" << EOF
#>>>Ouranos variables>>>
# Ouranos root directory
export OURANOS_DIR="${INSTALL_DIR}"

# Ouranos utility function to manage the application
ouranos() {
  case \$1 in
    start) "\${OURANOS_DIR}/scripts/start.sh" ;;
    stop) "\${OURANOS_DIR}/scripts/stop.sh" ;;
    restart) "\${OURANOS_DIR}/scripts/stop.sh" && "\${OURANOS_DIR}/scripts/start.sh" ;;
    status) systemctl status ouranos.service ;;
    logs) tail -f "\${OURANOS_DIR}/logs/ouranos.log" ;;
    stdout) tail -f "\${OURANOS_DIR}/logs/stdout" ;;
    update) "\${OURANOS_DIR}/scripts/update.sh" ;;
    *) echo "Usage: ouranos {start|stop|restart|status|logs|update}" ;;
  esac
}
complete -W "start stop restart status logs stdout update" ouranos
#<<<Ouranos variables<<<
EOF

# shellcheck source=/dev/null
source "${HOME}/.profile"
