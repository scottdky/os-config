#!/usr/bin/env python3
"""Run-once script to apply final read-only filesystem edits across Raspberry Pi on first boot."""

import sys
import subprocess
import os

def remount_ro() -> None:
    print("Remounting / and /boot/firmware to read-only...")
    subprocess.run(["mount", "-o", "remount,ro", "/"], check=False)
    subprocess.run(["mount", "-o", "remount,ro", "/boot/firmware"], check=False)
    subprocess.run(["mount", "-o", "remount,ro", "/boot"], check=False)

def enable_ro() -> None:
    # Disable swap
    subprocess.run(['dphys-swapfile', 'swapoff'], check=False)
    subprocess.run(['systemctl', 'disable', 'dphys-swapfile'], check=False)

    # 1. Update /etc/fstab to 'ro' for vfat and ext4
    print("Updating /etc/fstab...")
    try:
        with open("/etc/fstab", "r", encoding="utf-8") as f:
            lines = f.readlines()

        changed = False
        out_lines = []
        for line in lines:
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                out_lines.append(line)
                continue

            parts = line_str.split()
            if len(parts) >= 4 and parts[2] in ["vfat", "ext4"]:
                opts = parts[3].split(",")
                if "rw" in opts:
                    opts.remove("rw")
                if "defaults" in opts:
                    opts.remove("defaults")
                if "ro" not in opts:
                    opts.insert(0, "ro")
                    parts[3] = ",".join(opts)
                    line = " ".join(parts) + "\n"
                    changed = True
            out_lines.append(line)

        if changed:
            with open("/etc/fstab", "w", encoding="utf-8") as f:
                f.writelines(out_lines)
    except Exception as e:
        print(f"Error modifying fstab: {e}")

    # 2. Append ro and noswap to cmdline.txt
    print("Updating cmdline.txt...")
    for cmd_path in ["/boot/firmware/cmdline.txt", "/boot/cmdline.txt"]:
        if os.path.exists(cmd_path):
            try:
                with open(cmd_path, "r", encoding="utf-8") as f:
                    cmd_contents = f.read().strip()

                cmds = cmd_contents.split()
                added = False
                for t in ["fastboot", "noswap", "ro"]:
                    if t not in cmds:
                        cmds.append(t)
                        added = True

                if added:
                    with open(cmd_path, "w", encoding="utf-8") as f:
                        f.write(" ".join(cmds) + "\n")
            except Exception as e:
                print(f"Error modifying {cmd_path}: {e}")

    # 3. Disable this service so it only runs once
    print("Disabling enable-ro-fs.service...")
    subprocess.run(["systemctl", "disable", "enable-ro-fs.service"], check=False)

    print("Transition complete.")

if __name__ == "__main__":
    enable_ro()
    remount_ro()
    sys.exit(0)
