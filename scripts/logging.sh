if [ -z "$LOG_FILE" ]; then
  echo "LOG_FILE environment variable is not set."
  exit 1 # Exit if LOG_FILE is not set
fi

# Constants for log levels
readonly INFO=INFO
readonly WARN=WARN
readonly ERROR=ERROR
readonly SUCCESS=SUCCESS

# Colors for output
readonly RED='\033[38;5;001m'
readonly GREEN='\033[38;5;002m'
readonly YELLOW='\033[38;5;220m'
readonly LIGHT_YELLOW='\033[38;5;011m'
readonly NC='\033[0m' # No Color

# Function to log messages
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case "$1" in
        INFO)
            echo -e "${LIGHT_YELLOW}$2${NC}"
            echo -e "[${timestamp}] [INFO] $2" >> "${LOG_FILE}"
            ;;
        WARN)
            echo -e "${YELLOW}Warning: $2${NC}"
            echo -e "[${timestamp}] [WARNING] $2" >> "${LOG_FILE}"
            ;;
        ERROR)
            echo -e "${RED}Error: $2${NC}"
            echo -e "[${timestamp}] [ERROR] $2" >> "${LOG_FILE}"
            exit 1
            ;;
        SUCCESS)
            echo -e "${GREEN}$2${NC}"
            echo -e "[${timestamp}] [SUCCESS] $2" >> "${LOG_FILE}"
            ;;
        *)
            echo -e "$1"
            echo -e "[${timestamp}] $1" >> "${LOG_FILE}"
            ;;
    esac
}

log INFO "Log file: ${LOG_FILE}"
