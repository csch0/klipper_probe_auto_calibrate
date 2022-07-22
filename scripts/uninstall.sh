#!/bin/bash
KLIPPER_PATH="${HOME}/klipper"
KLIPPER_EXTENSION_PATH="${HOME}/klipper_probe_auto_calibrate"
SYSTEMDDIR="/etc/systemd/system"

# helper functions
verify_ready()
{
    if [ "$EUID" -eq 0 ]; then
        echo "This script must not run as root"
        exit -1
    fi
}

# link the extension
unlink_extension()
{
    echo "Unlinking extension from Klipper..."
    rm "${KLIPPER_PATH}/klippy/extras/probe_auto_calibrate.py"
}

# restarting Klipper
restart_klipper()
{
    echo "Restarting Klipper..."
    sudo systemctl restart klipper
}

# Force script to exit if an error occurs
set -e

# Parse command line arguments
while getopts "k:" arg; do
    case $arg in
        k) KLIPPER_PATH=$OPTARG;;
    esac
done

# Run steps
verify_ready
unlink_extension
restart_klipper