#!/bin/bash

# Exit on error, unset variable, and pipefail
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
DRY_RUN=false
FORCE_UPDATE=false

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

# Function to display help
show_help() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -d, --dry-run    Show what would be updated without making changes"
    echo "  -f, --force      Force update even if already at the latest version"
    echo "  -h, --help       Show this help message and exit"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -f|--force)
            FORCE_UPDATE=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            error_exit "Unknown option: $1"
            ;;
    esac
done

# Check if OURANOS_DIR is set
if [[ -z "${OURANOS_DIR:-}" ]]; then
    error_exit "OURANOS_DIR environment variable is not set. Please source your profile or run the install script first."
fi

# Check if the directory exists
if [[ ! -d "$OURANOS_DIR" ]]; then
    error_exit "Ouranos directory not found at $OURANOS_DIR. Please check your installation."
fi

cd "$OURANOS_DIR" || error_exit "Failed to change to Ouranos directory: $OURANOS_DIR"

# Check if virtual environment exists
if [[ ! -d "python_venv" ]]; then
    error_exit "Python virtual environment not found. Please run the install script first."
fi

# Activate virtual environment
# shellcheck source=/dev/null
if ! source "python_venv/bin/activate"; then
    error_exit "Failed to activate Python virtual environment"
fi

# Function to update a single repository
update_repo() {
    local repo_dir="$1"
    local repo_name=$(basename "$repo_dir")
    
    echo -e "\n${GREEN}Checking $repo_name...${NC}"
    
    if [[ ! -d "$repo_dir/.git" ]]; then
        warn "$repo_dir is not a git repository. Skipping."
        return 1
    fi
    
    cd "$repo_dir" || return 1
    
    # Get current branch and status
    local current_branch
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    local has_changes
    has_changes=$(git status --porcelain)
    
    if [[ -n "$has_changes" ]]; then
        warn "$repo_name has uncommitted changes. Stashing them..."
        if [[ "$DRY_RUN" == false ]]; then
            git stash save "Stashed by Ouranos update script"
        fi
    fi
    
    # Fetch all updates
    echo "Fetching updates for $repo_name..."
    if [[ "$DRY_RUN" == false ]]; then
        git fetch --all --tags --prune
    fi
    
    # Get current and latest tags
    local current_tag
    current_tag=$(git describe --tags 2>/dev/null || echo "No tags found")
    local latest_tag
    latest_tag=$(git describe --tags "$(git rev-list --tags --max-count=1 2>/dev/null)" 2>/dev/null || echo "No tags found")
    
    echo "Current version: $current_tag"
    echo "Latest version:  $latest_tag"
    
    if [[ "$current_tag" == "$latest_tag" && "$FORCE_UPDATE" == false ]]; then
        echo "$repo_name is already at the latest version. Use -f to force update."
        return 0
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        echo "[DRY RUN] Would update $repo_name from $current_tag to $latest_tag"
        return 0
    fi
    
    # Checkout the latest tag
    echo "Updating $repo_name to $latest_tag..."
    git checkout "$latest_tag"
    
    # Install the package in development mode
    if [[ -f "pyproject.toml" ]]; then
        echo "Installing $repo_name..."
        pip install -e .
    fi
    
    # Return to the original branch if not on a detached HEAD
    if [[ "$current_branch" != "HEAD" ]]; then
        echo "Returning to branch $current_branch..."
        git checkout "$current_branch"
        
        # Apply stashed changes if any
        if [[ -n "$has_changes" ]]; then
            echo "Restoring stashed changes..."
            git stash pop
        fi
    fi
    
    echo "$repo_name updated to $latest_tag"
    return 0
}

# Main update process
info "Starting Ouranos update..."

# Update ouranos-core
for OURANOS_PKG in "${OURANOS_DIR}/lib"/ouranos-*; do
  update_repo "$OURANOS_PKG"
done

# Deactivate virtual environment
deactivate 2>/dev/null || true

info "\nUpdate complete!"

# Show final instructions
if [[ "$DRY_RUN" == false ]]; then
    echo -e "\nTo apply the updates, please restart the Ouranos service with one of these commands:"
    echo -e "  ${YELLOW}ouranos restart${NC}    # If using the ouranos command"
    echo -e "  ${YELLOW}sudo systemctl restart ouranos.service${NC}  # If using systemd"
else
    echo -e "\nThis was a dry run. No changes were made. Use ${YELLOW}$0${NC} without --dry-run to perform the updates."
fi

exit 0
