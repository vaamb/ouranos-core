#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

# Load logging functions
readonly DATETIME=$(date +%Y%m%d_%H%M%S)
readonly LOG_FILE="/tmp/ouranos_update_${DATETIME}.log"
source "${OURANOS_DIR}/scripts/utils/logging.sh" "${LOG_FILE}"

readonly BACKUP_DIR="/tmp/ouranos_backup_${DATETIME}"

# Constants
DRY_RUN=false
FORCE_UPDATE=false
UPDATE_ALL=true

# Function to display help
show_help() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -d, --dry-run    Show what would be updated without making changes"
    echo "  -f, --force      Force update even if already at the latest version"
    echo "  -c, --core       Update the core package only"
    echo "  -h, --help       Show this help message and exit"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -d|--dry-run)
            DRY_RUN=true
            export DRY_RUN
            shift
            ;;
        -f|--force)
            FORCE_UPDATE=true
            shift
            ;;
        -c|--core)
            UPDATE_ALL=false
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log ERROR "Unknown option: $1"
            ;;
    esac
done

check_requirements() {
    # Check if uv is installed
    if ! command -v uv &> /dev/null; then
        log ERROR "uv is not installed. Please install it first."
    fi

    # Check if OURANOS_DIR is set
    if [[ -z "${OURANOS_DIR:-}" ]]; then
        log ERROR "OURANOS_DIR environment variable is not set. Please source your profile or run the installation script first."
    fi

    # Check if the directory exists
    if [[ ! -d "$OURANOS_DIR" ]]; then
        log ERROR "Ouranos directory not found at $OURANOS_DIR. Please check your installation."
    fi

    cd "$OURANOS_DIR" || log ERROR "Failed to change to Ouranos directory: $OURANOS_DIR"

    # Check if virtual environment exists
    if [[ ! -d "${OURANOS_DIR}/.venv" ]]; then
        log INFO "uv virtual environment not found. Creating it..."
        uv venv
        # log ERROR "Python virtual environment not found. Please run the installation script first."
    fi
}

create_backup() {
    # Create backup directory
    cp -r "$OURANOS_DIR" "$BACKUP_DIR" ||
        log ERROR "Failed to create backup directory: $BACKUP_DIR"
}

update_git_repo() {
    local repo_dir="$1"
    local repo_name
    repo_name=$(basename "$repo_dir")

    cd "$repo_dir" || return 1

    # Get current branch and status
    local current_branch
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    local has_changes
    has_changes=$(git status --porcelain)

    if [[ -n "$has_changes" ]]; then
        log WARN "$repo_name has uncommitted changes. Stashing them..."
        if [[ "$DRY_RUN" == false ]]; then
            git stash save "Stashed by Ouranos update script"
        fi
    fi

    # Fetch all updates
    log INFO "Fetching updates for $repo_name..."
    if [[ "$DRY_RUN" == false ]]; then
        git fetch --all --tags --prune
    fi

    # Get current and latest tags
    local current_tag
    current_tag=$(git describe --tags 2>/dev/null || echo "No tags found")
    local latest_tag
    latest_tag=$(git describe --tags "$(git rev-list --tags --max-count=1 2>/dev/null)" 2>/dev/null || echo "No tags found")

    log "Current version: $current_tag"
    log "Latest version:  $latest_tag"

    if [[ "$current_tag" == "$latest_tag" && "$FORCE_UPDATE" == false ]]; then
        log INFO "$repo_name is already at the latest version. Use -f to force update."
        return 0
    fi

    if [[ "$DRY_RUN" == true ]]; then
        log INFO "[DRY RUN] Would update $repo_name from $current_tag to $latest_tag"
        return 0
    fi

    # Checkout the latest tag
    log INFO "Updating $repo_name to $latest_tag..."
    git checkout "$latest_tag"

    # Return to the original branch if not on a detached HEAD
    if [[ "$current_branch" != "HEAD" ]]; then
        log "Returning to branch $current_branch..."
        git checkout "$current_branch"

        # Apply stashed changes if any
        if [[ -n "$has_changes" ]]; then
            log "Restoring stashed changes..."
            git stash pop
        fi
    fi

    log INFO "$repo_name updated to $latest_tag"
}

# Function to update a package other than ouranos-core
update_package() {
    local package_dir="$1"
    local package_name
    package_name=$(basename "${package_dir}")

    log INFO "Checking ${package_name}..."

    # Update the git directory
    if [[ -d "${package_dir}/.git" ]]; then
        update_git_repo "$package_dir"
    else
        log WARN "${package_name} is not a git repository. Skipping."
        return 1
    fi

    # If the package has an update script, run it
    if [[ -f "${package_dir}/scripts/update.sh" ]]; then
        if [[ $DRY_RUN == false ]]; then
            log INFO "${package_name} has an update script. Running it..."
            source "${package_dir}/scripts/update.sh"
        else
            log INFO "[DRY RUN] Would run update script for ${package_name}"
        fi
    fi

    log SUCCESS "${package_name} updated successfully"

    return 0
}

update_packages() {
    # In dry-run, don't activate venv or install; just show intended repo changes
    if [[ "${DRY_RUN}" == false ]]; then
        # Activate virtual environment
        # shellcheck source=/dev/null
        if ! source ".venv/bin/activate"; then
            log ERROR "Failed to activate Python virtual environment"
        fi
    fi

    if [[ "${UPDATE_ALL}" == true ]]; then
        # First update ouranos-core
        update_package "${OURANOS_DIR}/lib/ouranos-core"

        # Update remaining ouranos-* packages
        for pkg_path  in "${OURANOS_DIR}/lib"/ouranos-*; do
            package_name=$(basename "${pkg_path }")
            if [[ "${package_name}" != "ouranos-core" ]]; then
                if ! update_package "$pkg_path"; then
                    log WARN "Failed to update ${package_name}, continuing with other packages..."
                fi
            fi
        done
    else
        update_package "${OURANOS_DIR}/lib/ouranos-core"
    fi

    # Update uv lock and packages
    if [[ "${DRY_RUN}" == false ]]; then
        cd "$OURANOS_DIR"
        uv lock --upgrade
    fi

    if [[ "${DRY_RUN}" == false ]]; then
        # Deactivate virtual environment
        deactivate 2>/dev/null || true
    fi
}

update_core_scripts() {
    # Copy scripts from ouranos-core to ouranos/scripts
    cp -r "${OURANOS_DIR}/lib/ouranos-core/scripts/"* "${OURANOS_DIR}/scripts/" ||
        log ERROR "Failed to copy scripts"
    # Make scripts executable
    chmod +x "${OURANOS_DIR}/scripts/"*.sh
    chmod +x "${OURANOS_DIR}/scripts/utils/"*.sh
    # Convert scripts to unix format
    dos2unix "${OURANOS_DIR}/scripts/"*.sh
    dos2unix "${OURANOS_DIR}/scripts/utils/"*.sh
    # Remove ouranos-core update.sh
    rm "${OURANOS_DIR}/scripts/update.sh"
}

update_profile() {
    "${OURANOS_DIR}/scripts/gen_profile.sh" "${OURANOS_DIR}" ||
        log ERROR "Failed to update shell profile"
}

update_service() {
    local service_file="${OURANOS_DIR}/scripts/ouranos.service"

    "${OURANOS_DIR}/scripts/gen_service.sh" "${OURANOS_DIR}" "${service_file}" ||
        log ERROR "Failed to generate systemd service"

    # Update service
    if ! sudo cp "${service_file}" "/etc/systemd/system/ouranos.service"; then
        log WARN "Failed to copy service file. You may need to run with sudo."
    else
        sudo systemctl daemon-reload ||
            log WARN "Failed to reload systemd daemon"
    fi
}

# Cleanup function to run on exit
cleanup() {
    local exit_code=$?

    if [ "${exit_code}" -ne 0 ]; then
        log WARN "Update failed. Check the log file for details: ${LOG_FILE}"
        if [[ -d "${BACKUP_DIR}" && "${DRY_RUN}" == false ]]; then
            log WARN "Attempting rollback from backup..."
            rm -rf "${OURANOS_DIR}"
            cp -r "${BACKUP_DIR}" "${OURANOS_DIR}"
        fi
    else
        if [[ -d "${BACKUP_DIR}" ]]; then
            rm -rf "${BACKUP_DIR}"
        fi
        log SUCCESS "Update completed successfully!"
    fi

    # Reset terminal colors
    echo -e "${NC}"
    exit "${exit_code}"
}

main () {
    # Set up trap for cleanup on exit
    trap cleanup EXIT

    log INFO "Starting Ouranos update..."

    log INFO "Checking system requirements..."
    check_requirements
    log SUCCESS "System requirements met"

    if [[ "${DRY_RUN}" == false ]]; then
        log INFO "Creating backup..."
        create_backup
        log SUCCESS "Backup created at ${BACKUP_DIR}"
    else
        log INFO "Dry run mode: no changes will be made. Showing intended operations."
    fi

    log INFO "Updating Ouranos packages..."
    update_packages
    log SUCCESS "Packages updated successfully"

    if [[ "${DRY_RUN}" == false ]]; then
        log INFO "Making scripts more easily accessible..."
        update_core_scripts
    else
        log INFO "Dry run: skipping scripts update"
    fi

    if [[ "${DRY_RUN}" == false ]]; then
        log INFO "Updating shell profile..."
        update_profile
        log SUCCESS "Profile updated successfully"
    else
        log INFO "Dry run: skipping profile update"
    fi

    if [[ "${DRY_RUN}" == false ]]; then
        log INFO "Updating systemd service..."
        update_service
        log SUCCESS "Systemd service updated successfully"
    else
        log INFO "Dry run: skipping systemd service update"
    fi

    # Display completion message

    if [[ "$DRY_RUN" == false ]]; then
        echo -e "\n${GREEN}✔ Update completed successfully!${NC}"
        echo -e "\nTo apply the updates, please restart the Ouranos service with one of these commands:"
        echo -e "  ${YELLOW}ouranos restart${NC}                         # If using the ouranos command"
        echo -e "  ${YELLOW}sudo systemctl restart ouranos.service${NC}  # If using systemd"
    else
        echo -e "\nThis was a dry run. No changes were made. Use ${YELLOW}$0${NC} without --dry-run to perform the updates."
    fi

    exit 0
}

if [ "${BASH_SOURCE[0]}" -ef "$0" ]
then
    main "$@"
fi
