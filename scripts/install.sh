#!/bin/bash
KLIPPER_PATH="${HOME}/klipper"
KLIPPER_EXTENSION_PATH="${HOME}/klipper_probe_z_calibrate"
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
link_extension()
{
    echo "Linking extension to Klipper..."
    ln -sf "${KLIPPER_EXTENSION_PATH}/probe_z_calibrate.py" "${KLIPPER_PATH}/klippy/extras/probe_z_calibrate.py"
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
link_extension
restart_klipper