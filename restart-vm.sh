#!/bin/bash

if [ -f .env ]; then
    for env in $(cat .env); do
        export "$env"
    done
fi

GOVC="${GOVC_BIN:-/usr/local/bin/govc}"

if [ -z "$1" ]; then
    echo "Usage: $0 <vm-name>"
    echo "Example: $0 my-vm"
    echo ""
    echo "Set GOVC_FOLDER to folder name (e.g., sp-abhijith)"
    exit 1
fi

VM_NAME="$1"

# Build folder path from GOVC_FOLDER
if [ -z "$GOVC_FOLDER" ]; then
    echo "Error: GOVC_FOLDER env variable not set"
    exit 1
fi

FOLDER_PATH="/Datacenter/vm/$GOVC_FOLDER"

echo "Using folder: $FOLDER_PATH"

# Find the VM
VM=$($GOVC find "$FOLDER_PATH" -name "$VM_NAME" -type m 2>/dev/null)

if [ -z "$VM" ]; then
    echo "No VM found with name: $VM_NAME"
    exit 1
fi

echo "Found VM: $VM"
echo ""
read -p "Continue with restart? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi

echo ""
echo "Powering off VM..."
$GOVC vm.power -off "$VM"

echo "Waiting for VM to power off..."
sleep 5

echo "Powering on VM..."
$GOVC vm.power -on "$VM"

echo "Done"
