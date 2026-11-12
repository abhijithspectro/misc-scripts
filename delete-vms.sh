#!/bin/bash

if [ -z "$1" ]; then
    echo "Usage: $0 <vm-name-pattern>"
    echo "Example: $0 abhi-pal"
    exit 1
fi

PATTERN="$1"

# Find VMs matching pattern
VMSTOML=$(govc ls -l "/Datacenter/vm/**/*${PATTERN}*" 2>/dev/null | grep VirtualMachine | awk '{print $1}')

if [ -z "$VMSTOML" ]; then
    echo "No VMs found matching pattern: $PATTERN"
    exit 0
fi

echo "VMs to be deleted:"
echo "$VMSTOML"
echo ""
read -p "Continue with deletion? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi

echo "$VMSTOML" | while read -r vm; do
    echo "Deleting: $vm"
    govc vm.destroy "$vm"
done

echo "Done"
