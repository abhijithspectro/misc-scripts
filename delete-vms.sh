#!/bin/bash

if [ -f .env ]; then
    for env in $(cat .env); do
        export "$env"
    done
fi

GOVC="${GOVC_BIN:-/usr/local/bin/govc}"

if [ -z "$1" ]; then
    echo "Usage: $0 <name-pattern>"
    echo "Example: $0 flannel"
    echo ""
    echo "Set GOVC_FOLDER to folder name (e.g., sp-abhijith)"
    exit 1
fi

PATTERN="$1"

# Build folder path from GOVC_FOLDER
if [ -z "$GOVC_FOLDER" ]; then
    echo "Error: GOVC_FOLDER env variable not set"
    exit 1
fi

FOLDER_PATH="/Datacenter/vm/$GOVC_FOLDER"

echo "Using folder: $FOLDER_PATH"

# Find VMs and folders matching pattern within the specified folder
OBJECTS=$($GOVC find "$FOLDER_PATH" -name "*${PATTERN}*" -type m 2>/dev/null; $GOVC find "$FOLDER_PATH" -name "*${PATTERN}*" -type f 2>/dev/null)

if [ -z "$OBJECTS" ]; then
    echo "No VMs or folders found matching pattern: $PATTERN"
    exit 0
fi

echo "Objects to be deleted:"
echo "$OBJECTS"
echo ""
read -p "Continue with deletion? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi

echo ""
echo "Powering off VMs first..."
echo "$OBJECTS" | while read -r obj; do
    # Check if it's a VM (folders end with /)
    if [[ ! "$obj" =~ /$ ]]; then
        echo "Powering off: $obj"
        $GOVC vm.power -off "$obj" 2>/dev/null || true
    fi
done

echo ""
echo "Deleting objects..."
echo "$OBJECTS" | while read -r obj; do
    echo "Deleting: $obj"
    $GOVC object.destroy "$obj"
done

echo "Done"
