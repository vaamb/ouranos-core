GAIA_DIR=${1}

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

# shellcheck source=/dev/null
source "${HOME}/.profile"
