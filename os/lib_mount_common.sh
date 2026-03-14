#!/usr/bin/env bash

require_command() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Error: required command not found: $cmd"
        exit 1
    fi
}

prepare_mount_dirs() {
    local mountPath="$1"
    sudo mkdir -p "$mountPath" "$mountPath/boot" "$mountPath/dev" "$mountPath/dev/pts"
}

bind_system_dirs() {
    local mountPath="$1"
    sudo mount -o bind /dev "$mountPath/dev"
    sudo mount -o bind /dev/pts "$mountPath/dev/pts"
}

verify_mount_target() {
    local targetPath="$1"
    local label="$2"
    if ! findmnt -T "$targetPath" >/dev/null 2>&1; then
        echo "$label mount verification failed for $targetPath"
        return 1
    fi
    return 0
}
