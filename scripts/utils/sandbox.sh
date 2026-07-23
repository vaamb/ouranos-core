#!/bin/bash
#
# Run one of the ouranos scripts in a throwaway sandbox, so it can't touch your
# real install, ~/.profile or /etc/systemd/system.
#
# Usage (run from the directory containing the script, e.g. scripts/):
#     ./utils/sandbox.sh "install.sh --unsafe"
#     ./utils/sandbox.sh install.sh --unsafe          # unquoted also works
#
# How it isolates:
#   - throwaway $HOME and install dir under /tmp (mktemp);
#   - stub `sudo` and `systemctl` on PATH, so the systemd step is a visible
#     no-op and /etc/systemd/system is never written;
#   - env -i for a clean environment (your real OURANOS_DIR can't leak in).
# The uv cache is the one exception: it is shared with the real one, see below.
#
# The sandboxed install.sh clones a mirror of the local repository holding the
# current working tree, uncommitted changes included, so the scripts being
# worked on are the ones being tested. Tagging that mirror (it lives in
# ${SANDBOX}/repo-mirror) simulates a new release for update_ouranos.sh:
#     git -C "${OURANOS_SANDBOX}/repo-mirror" tag 0.12.0
#
# After a sandboxed install.sh, the database is filled and stamped (what the
# install script tells the user to do next), so update_ouranos.sh can be run
# against the sandbox right away.
#
# Reusing a sandbox (e.g. install first, then test the update against it):
#     export OURANOS_SANDBOX=$(mktemp -d /tmp/ouranos_sandbox_XXXX)
#     ./utils/sandbox.sh install.sh
#     ./utils/sandbox.sh update_ouranos.sh --dry-run

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 \"<script.sh> [args...]\"   (run from the script's directory)" >&2
    exit 1
fi

# Accept either a single quoted string ("install.sh -u") or separate arguments.
if [[ $# -eq 1 ]]; then
    read -r -a CMD <<< "$1"
else
    CMD=("$@")
fi

# Resolve the script relative to the directory you invoked this from, since we
# cd into the sandbox before running it.
if [[ "${CMD[0]}" != /* && -f "${PWD}/${CMD[0]}" ]]; then
    CMD[0]="${PWD}/${CMD[0]}"
fi
[[ -f "${CMD[0]}" ]] || { echo "Script not found: ${CMD[0]}" >&2; exit 1; }

# Repository the sandboxed install.sh clones from. Only the entry script below
# runs from the working tree: everything else (utils/, update.sh, start.sh...)
# is deployed from that clone, so it has to be the local repository for local
# changes to be tested at all. See `build_mirror` further down.
REPO="$(git -C "$(dirname "${CMD[0]}")" rev-parse --show-toplevel 2>/dev/null || true)"

# Fresh sandbox unless one was provided (reuse across install + update).
SANDBOX="${OURANOS_SANDBOX:-$(mktemp -d /tmp/ouranos_sandbox_XXXX)}"
echo "Sandbox: ${SANDBOX}   (remove with: rm -rf \"${SANDBOX}\")"
mkdir -p "${SANDBOX}/home" "${SANDBOX}/bin"

# The working-tree scripts are stored CRLF (see .gitattributes); the deployed
# copies get dos2unix'd. Do the same for the entry script we run directly, else
# bash chokes on the \r. (Its siblings under utils/ are normalised on copy.)
RUN="${SANDBOX}/$(basename "${CMD[0]}")"
tr -d '\r' < "${CMD[0]}" > "${RUN}"
CMD[0]="${RUN}"

# Stub sudo/systemctl so the systemd step is a visible no-op (never touches /etc)
printf '#!/bin/bash\necho "[stub] sudo $*"\n' > "${SANDBOX}/bin/sudo"
printf '#!/bin/bash\necho "[stub] systemctl $*"\n' > "${SANDBOX}/bin/systemctl"
chmod +x "${SANDBOX}/bin/"*

cd "${SANDBOX}"   # install.sh installs into ${PWD}/ouranos

# $HOME below expands (outer shell) to your real home, so uv on ~/.local/bin is
# found; adjust if uv lives elsewhere. The uv cache is pointed back at the real
# one on purpose: it is content-addressed and shared, and a sandboxed HOME would
# otherwise re-download every wheel (~400 MB) for each new sandbox.
# USER must be passed explicitly: gen_service.sh references ${USER} under set -u,
# and it is not always exported (cron, containers, `env -i` shells).
SANDBOX_ENV=(
    HOME="${SANDBOX}/home"
    USER="${USER:-$(id -un)}"
    TERM="${TERM:-xterm}"
    UV_CACHE_DIR="${UV_CACHE_DIR:-${XDG_CACHE_HOME:-${HOME}/.cache}/uv}"
    PATH="${SANDBOX}/bin:${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin"
)

# `git clone` only ever sees committed state, which makes iterating on a script
# tedious. Mirror the repository inside the sandbox and lay the working tree on
# top of it, so the installation runs the scripts as they currently are on disk.
# The real repository is only ever read from.
build_mirror() {
    local created=false
    local version

    if [[ ! -d "${MIRROR}" ]]; then
        git clone --no-hardlinks --quiet "${REPO}" "${MIRROR}"
        created=true
    fi

    # Wipe the checkout before copying, so files deleted in the working tree do
    # not linger in the mirror
    find "${MIRROR}" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +

    # Tracked and new files, minus the git-ignored ones (.venv, caches...)
    git -C "${REPO}" ls-files -z --cached --others --exclude-standard |
        rsync -a --files-from=- --from0 "${REPO}/" "${MIRROR}/"

    # core.safecrlf would warn about every CRLF file the repository holds
    git -C "${MIRROR}" -c core.safecrlf=false add --all
    git -C "${MIRROR}" -c user.email=sandbox@ouranos -c user.name=sandbox \
        commit --quiet --allow-empty --message "Sandboxed working tree"

    # When installing the safe version, install.sh clones the tag matching its
    # own OURANOS_VERSION: move it onto the working tree, creating it if this is
    # a version that has not been released yet. Only do so when creating the
    # mirror: the `git fetch --tags` update_ouranos.sh runs exits non-zero on a
    # tag that moved, which would abort the update and roll it back.
    if [[ "${created}" == true ]]; then
        # Stop at the closing quote rather than anchoring on it, so a CRLF
        # install.sh (trailing \r before the line end) still matches
        version=$(sed -n 's/^readonly OURANOS_VERSION="\([^"]*\)".*/\1/p' "${MIRROR}/scripts/install.sh")
        if [[ -n "${version}" ]]; then
            git -C "${MIRROR}" tag --force "${version}" > /dev/null
        fi
    fi
}

# Only install.sh clones, but a reused sandbox gets its mirror refreshed too, so
# that update_ouranos.sh --unsafe sees the latest state of the working tree.
# Tags are left where they are on a refresh, so tagging the mirror to simulate a
# release keeps working for the safe update path.
MIRROR="${SANDBOX}/repo-mirror"
if [[ -n "${REPO}" ]] &&
        [[ "$(basename "${CMD[0]}")" == install.sh || -d "${MIRROR}" ]]; then
    build_mirror
    SANDBOX_ENV+=(OURANOS_REPO="${MIRROR}")
fi

# install.sh deliberately leaves the database alone: it must be configured before
# being created. update_ouranos.sh however runs `alembic upgrade head`, which
# fails on a database that was never created, so do here what install.sh tells
# the user to do next, leaving the sandbox ready for an update run.
prepare_database() {
    # Nothing to do if install.sh exited without installing (e.g. --help)
    [[ -x "${SANDBOX}/ouranos/.venv/bin/python" ]] || return 0

    echo "Sandbox: filling and stamping the database (install.sh 'Next steps')..."
    env -i "${SANDBOX_ENV[@]}" OURANOS_DIR="${SANDBOX}/ouranos" bash -c '
        set -euo pipefail
        cd "${OURANOS_DIR}"
        . .venv/bin/activate
        python -m ouranos fill-db --no-check-revision
        alembic stamp head
    ' || echo "Sandbox: database preparation failed, update_ouranos.sh will fail on 'alembic upgrade head'" >&2
}

# install.sh refuses to run when OURANOS_DIR is set; every other script needs it
# pointed at the sandbox install.
if [[ "$(basename "${CMD[0]}")" == install.sh ]]; then
    env -i "${SANDBOX_ENV[@]}" bash "${CMD[@]}"
    prepare_database
else
    env -i "${SANDBOX_ENV[@]}" OURANOS_DIR="${SANDBOX}/ouranos" bash "${CMD[@]}"
fi
