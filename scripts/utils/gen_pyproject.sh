#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

INSTALL_DIR="${1:-}"

# Validate argument
if [[ -z "${INSTALL_DIR}" ]]; then
  echo "Usage: $0 <ouranos_install_dir>" >&2
  exit 1
fi

cat >> "${PWD}/pyproject.toml" << EOF
[project]
name = "ouranos"
version = "0.10.0"
description = "An app to manage Gaia instances"
requires-python = ">=3.11"
dependencies = ["ouranos-core"]

[tool.uv.sources]
ouranos-core = { workspace = true }

[tool.uv.workspace]
members = ["lib/ouranos-*"]
EOF
