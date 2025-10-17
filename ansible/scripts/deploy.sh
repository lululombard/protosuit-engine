#!/bin/bash
# Deployment script for Protosuit Engine

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANSIBLE_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}=== Protosuit Engine Deployment ===${NC}"
echo ""

# Check if Ansible is installed
if ! command -v ansible-playbook &> /dev/null; then
    echo -e "${RED}Error: Ansible is not installed${NC}"
    echo "Install with: sudo apt install ansible"
    exit 1
fi

# Check if we're running as the correct user
if [[ "$USER" != "proto" ]]; then
    echo -e "${YELLOW}Warning: Running as user '$USER', expected 'proto'${NC}"
    echo "You may need to adjust the inventory file for your user"
fi

# Parse command line arguments
DEPLOY_TYPE="full"
TARGET="local"

while [[ $# -gt 0 ]]; do
    case $1 in
        --type)
            DEPLOY_TYPE="$2"
            shift 2
            ;;
        --target)
            TARGET="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --type TYPE     Deployment type: full, main, display (default: full)"
            echo "  --target TARGET Target: local, remote (default: local)"
            echo "  --help          Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                          # Full local deployment (recommended)"
            echo "  $0 --type main              # Main setup only"
            echo "  $0 --type display           # Display config only"
            echo "  $0 --target remote          # Remote deployment (advanced)"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Set playbook based on deployment type
case $DEPLOY_TYPE in
    "full")
        PLAYBOOK="deploy.yml"
        ;;
    "main")
        PLAYBOOK="main.yml"
        ;;
    "display")
        PLAYBOOK="display-config.yml"
        ;;
    *)
        echo -e "${RED}Invalid deployment type: $DEPLOY_TYPE${NC}"
        echo "Valid types: full, main, display"
        exit 1
        ;;
esac

echo -e "${BLUE}Deployment Configuration:${NC}"
echo "  Type: $DEPLOY_TYPE"
echo "  Target: $TARGET"
echo "  Playbook: $PLAYBOOK"
echo ""

# Change to Ansible directory
cd "$ANSIBLE_DIR"

# Run the playbook
echo -e "${GREEN}Starting deployment...${NC}"
echo ""

if ansible-playbook -i inventory/hosts.yml playbooks/$PLAYBOOK -v; then
    echo ""
    echo -e "${GREEN}=== Deployment Completed Successfully! ===${NC}"
    echo ""
    echo -e "${BLUE}Next Steps:${NC}"
    echo "1. Reboot the system to ensure all services start properly"
    echo "2. Test the displays: source ~/.display-env.sh && test_displays"
    echo "3. Check service status: sudo systemctl status protosuit-system"
    echo "4. View logs: sudo journalctl -u protosuit-system -f"
    echo ""
    echo -e "${BLUE}Useful Commands:${NC}"
    echo "  Start service: sudo systemctl start protosuit-system"
    echo "  Stop service: sudo systemctl stop protosuit-system"
    echo "  Restart service: sudo systemctl restart protosuit-system"
    echo "  View logs: sudo journalctl -u protosuit-system -f"
else
    echo ""
    echo -e "${RED}=== Deployment Failed! ===${NC}"
    echo "Check the error messages above and fix any issues."
    echo "Common issues:"
    echo "  - Missing dependencies (install ansible)"
    echo "  - Permission issues (run with sudo if needed)"
    echo "  - Network connectivity (for remote targets)"
    exit 1
fi
