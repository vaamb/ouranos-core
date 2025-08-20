LOGGING_FILE="${1:-}"

if [ -z "$LOGGING_FILE" ]; then
  echo "Usage: $0 <log_file>" >&2
  exit 1 # Exit if LOGGING_FILE is not set
fi

# Constants for log levels
readonly INFO="INFO"
readonly WARN="WARN"
readonly ERROR="ERROR"
readonly SUCCESS="SUCCESS"

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
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case "$1" in
        INFO)
            echo -e "${LIGHT_YELLOW}$2${NC}"
            echo -e "[${timestamp}] [INFO] $2" >> "${LOGGING_FILE}"
            ;;
        WARN)
            echo -e "${YELLOW}Warning: $2${NC}"
            echo -e "[${timestamp}] [WARNING] $2" >> "${LOGGING_FILE}"
            ;;
        ERROR)
            echo -e "${RED}Error: $2${NC}"
            echo -e "[${timestamp}] [ERROR] $2" >> "${LOGGING_FILE}"
            exit 1
            ;;
        SUCCESS)
            echo -e "${GREEN}$2${NC}"
            echo -e "[${timestamp}] [SUCCESS] $2" >> "${LOGGING_FILE}"
            ;;
        *)
            echo -e "$1"
            echo -e "[${timestamp}] $1" >> "${LOGGING_FILE}"
            ;;
    esac
}

log INFO "Log file: ${LOGGING_FILE}"
