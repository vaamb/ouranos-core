#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

INSTALL_DIR="${1:-}"  # ${OURANOS_DIR} in practice
OUTPUT_FILE="${2:-}"
TEMPLATE_FILE="${3:-}"

# Validate arguments
if [[ -z "${INSTALL_DIR}" || -z "${OUTPUT_FILE}" || -z "${TEMPLATE_FILE}" ]]; then
  echo "Usage: $0 <ouranos_install_dir> <nginx_conf_path> <template_path>" >&2
  echo "  When run from an installed tree, pass the template explicitly, e.g." >&2
  echo "  <ouranos_install_dir>/lib/ouranos-core/deploy/nginx/ouranos.conf" >&2
  exit 1
fi

# Simply expands ${OURANOS_DIR} into its value (rem: need to use `|` as sed
# delimiters as `${INSTALL_DIR}` is a path what contains `/`)
sed "s|\${OURANOS_DIR}|${INSTALL_DIR}|g" "${TEMPLATE_FILE}" > "${OUTPUT_FILE}"
