if [ -z "$LOG_FILE" ]; then
  echo "LOG_FILE environment variable is not set."
  exit 1 # Exit if LOG_FILE is not set
fi

# Create the log dir if it doesn't already exist
mkdir -p "$(dirname "$LOG_FILE")"

# Colors for output
if [[ -t 1 ]]; then
    readonly RED='\033[38;5;001m'
    readonly GREEN='\033[38;5;002m'
    readonly YELLOW='\033[38;5;220m'
    readonly LIGHT_YELLOW='\033[38;5;011m'
    readonly NC='\033[0m' # No Color
else
    readonly RED=""
    readonly GREEN=""
    readonly YELLOW=""
    readonly LIGHT_YELLOW=""
    readonly NC=""
fi

# Function to log messages
log() {
    local timestamp=$(date '+%H:%M:%S')
    local full_timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case "$1" in
        INFO)
            echo -e "${LIGHT_YELLOW}[${timestamp}]${NC}$2"
            echo -e "[${full_timestamp}] [INFO] $2" >> "${LOG_FILE}"
            ;;
        WARN)
            echo -e "${YELLOW}[${timestamp}]${NC}$2" >&2
            echo -e "[${full_timestamp}] [WARNING] $2" >> "${LOG_FILE}"
            ;;
        ERROR)
            echo -e "${RED}[${timestamp}]${NC}$2" >&2
            echo -e "[${full_timestamp}] [ERROR] [${BASH_SOURCE[1]}:${BASH_LINENO[0]}] $2" >> "${LOG_FILE}"
            ;;
        SUCCESS)
            echo -e "${GREEN}[${timestamp}]${NC}$2"
            echo -e "[${full_timestamp}] [SUCCESS] $2" >> "${LOG_FILE}"
            ;;
    esac
}

die() {
    log ERROR "$1"
    exit 1
}

log INFO "Log file: ${LOG_FILE}"
