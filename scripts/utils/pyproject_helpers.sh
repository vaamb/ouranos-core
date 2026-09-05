#!/bin/bash

add_dependency() {
    # add_dependency <name> [extras] [source]
    #   name:    the package name, ex: `ouranos-frontend`
    #   extras:  optional comma-separated extras, ex: `postgresql`
    #   source:  the `[tool.uv.sources]` entry, `{ workspace = true }` by
    #            default, or `none` for a package coming from PyPI
    local name="${1:-}"
    local extras="${2:-}"
    local source="${3:-}"

    if [[ -z "${name}" ]]; then
        echo "add_dependency: missing package name" >&2
        return 1
    fi

    if [[ -z "${source}" ]]; then
        source="{ workspace = true }"
    fi

    # Ensure the master pyproject is accessible
    local pyproject="${OURANOS_DIR:-}/pyproject.toml"
    if [[ ! -f "${pyproject}" ]]; then
        echo "add_dependency: ${pyproject} not found, is OURANOS_DIR set?" >&2
        return 1
    fi

    # Ensure the anchors exist
    local dependency_anchor="# Add extra dependencies above this line"
    if ! grep -qF "${dependency_anchor}" "${pyproject}"; then
        echo "add_dependency: '${dependency_anchor}' is missing from ${pyproject}" >&2
        return 1
    fi

    # A `.` is legal in a package name but is a wildcard in a regex: escape it
    local escaped_name="${name//./\\.}"
    # Match the requirement with or without extras, ie `"name"` or `"name[extra]"`
    local requirement_re="^([[:space:]]*)\"${escaped_name}(\[[^]]*\])?\","
    local requirement="\"${name}${extras:+[${extras}]}\","

    if grep -qE "${requirement_re}" "${pyproject}"; then
        # Already required: only rewrite the line when extras are requested, so
        # that a plain `add_dependency ouranos-core` cannot silently drop an
        # already declared `[postgresql]`
        if [[ -n "${extras}" ]]; then
            sed -i -E "s|${requirement_re}|\1${requirement}|" "${pyproject}"
        fi
    else
        sed -i "/${dependency_anchor}/i\\    ${requirement}" "${pyproject}"
    fi

    if [[ "${source}" == "none" ]]; then
        return 0
    fi

    local source_anchor="# Add extra sources above this line"
    if ! grep -qF "${source_anchor}" "${pyproject}"; then
        echo "add_dependency: '${source_anchor}' is missing from ${pyproject}" >&2
        return 1
    fi

    if ! grep -qE "^${escaped_name} = " "${pyproject}"; then
        sed -i "/${source_anchor}/i\\${name} = ${source}" "${pyproject}"
    fi
}
