"""Partition management operation for the OS Config pipeline.

This operation allows expanding the raw disk image, resizing existing partitions
(if they are the trailing partition), and creating new formatted partitions to
distribute custom file layouts like /home or /data.
"""

import sys
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT

from lib.operations import OperationBase, OperationLogRecord
from lib.managers.base import BaseManager
from lib.fstab import Fstab, FstabLine
from lib.partition_utils import (
    expand_image_file,
    expand_partition,
    add_partition,
    resolve_partition_num,
    is_last_partition,
    check_partition_exists
)

class PartitionOperation(OperationBase):
    """Modify disk topology and partition limits."""

    def __init__(self) -> None:
        super().__init__(
            moduleName="core",
            name="partition",
            requiredConfigs={}
        )

    def gather_config(self, mgr: BaseManager) -> dict[str, Any]:
        """Resolve and validate partition settings from YAML."""
        # Optional so we don't strictly require it, we use defaults
        return self._config.get('partition', {})

    def prompt_missing_values(self, mgr: BaseManager, configs: dict[str, Any]) -> dict[str, Any]:
        """Prompt for any missing config values."""
        return configs

    def is_manager_compatible(self, mgr: BaseManager) -> tuple[bool, str]:
        if not mgr.is_os_image():
            return False, "Partition operations are only supported on unmounted Image/SD blocks."
        return True, ""

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord | bool:
        logs = []
        changed = False

        # -----------------------------------------------------
        # PHASE 0: Resolve Identifiers
        # -----------------------------------------------------
        # We must figure out what partition numbers map to "mount: /", "label: data"
        # BEFORE we unmount the system!
        resolved_resizes = []
        for p in configs.get('resize_partitions', []):
            try:
                part_num = resolve_partition_num(mgr, p)
                resolved_resizes.append({
                    "num": part_num,
                    "size_mb": p.get('size_mb', 0)
                })
            except Exception as e:
                logs.append(f"Skipping resize for {p}: {e}")

        # -----------------------------------------------------
        # PHASE 1: Disk Geometry (Unmounted)
        # -----------------------------------------------------
        new_partitions = []
        deferred_resizes = []
        with mgr.temporarily_unmounted():
            # 1. Expand the raw .img file
            expand_amount = configs.get('image_expand_mb', 0)
            if expand_amount > 0 and hasattr(mgr, 'imagePath'):
                expand_image_file(mgr, expand_amount)
                changed = True
                logs.append(f"Expanded image file by {expand_amount}MB")

            # 2. Resize Existing Partitions
            for res_p in resolved_resizes:
                part_num = res_p["num"]
                if not is_last_partition(mgr, part_num):
                    logs.append(f"Ignored resize: partition {part_num} is not the last partition.")
                    continue

                if res_p["size_mb"] == 0 and hasattr(mgr, 'imagePath'):
                    deferred_resizes.append(part_num)
                    logs.append(f"Deferred partition {part_num} resize to boot-time.")
                    changed = True
                    continue

                try:
                    expand_partition(mgr, part_num, size_mb=res_p["size_mb"])
                    changed = True
                    logs.append(f"Resized partition {part_num} " + (f"by {res_p['size_mb']}MB" if res_p['size_mb'] else "to 100%"))
                except Exception as e:
                    logs.append(f"Error resizing partition {part_num}: {e}")

            # 3. Add New Partitions
            for p in configs.get('add_partitions', []):
                label = p.get('label')
                if not label:
                    logs.append("Create skipped: no label provided.")
                    continue

                if check_partition_exists(mgr, label):
                    logs.append(f"Create skipped: partition '{label}' already exists.")
                    continue

                try:
                    size_mb = p.get('size_mb', 0)
                    fs = p.get('fs', 'ext4')

                    device_path = add_partition(mgr, label, size_mb=size_mb, fs=fs)

                    new_partitions.append({
                        "label": label,
                        "device_path": device_path,
                        "fs": fs,
                        "copy_source": p.get('copy_source')
                    })
                    changed = True
                    logs.append(f"Created partition '{label}' ({size_mb}MB, {fs})")
                except Exception as e:
                    logs.append(f"Error creating partition {label}: {e}")

        # -----------------------------------------------------
        # PHASE 2: Filesystem Integration (Remounted)
        # -----------------------------------------------------
        from lib.partition_utils import inject_custom_resize
        for part_num in deferred_resizes:
            try:
                inject_custom_resize(mgr, part_num)
                logs.append(f"Injected custom boot-time resize for partition {part_num}.")
            except Exception as e:
                logs.append(f"Failed to inject custom resize for partition {part_num}: {e}")

        if not new_partitions:
            return OperationLogRecord(self.name, changed, errors=logs)

        fstab = Fstab()
        fstab.load(mgr)

        for p in new_partitions:
            label = p["label"]

            # Step A: Data copying for special locations (like /home)
            if p["copy_source"]:
                src = p["copy_source"]
                tmp_mount = f"/mnt/tmp_migrate_{label}"
                mgr.run(f"mkdir -p {tmp_mount}", sudo=True)
                mgr.run(f"mount LABEL={label} {tmp_mount} || mount {p['device_path']} {tmp_mount}", sudo=True)

                rsync_result = mgr.run(f"rsync -a {src}/ {tmp_mount}/", sudo=True)
                if rsync_result.returnCode != 0:
                    logs.append(f"Warning: rsync failed copying {src} to {label} partition")

                mgr.run(f"umount {tmp_mount}", sudo=True)

            # Step B: Register in /etc/fstab
            # Ensure it's not already in fstab from a previous broken run
            if not fstab.inList(f"LABEL={label}"):
                new_line = f"LABEL={label}\t/{label}\t{p['fs']}\tdefaults,noatime\t0\t2"
                fstab.lines.append(FstabLine(new_line))

        if new_partitions:
            fstab.save(mgr)

        return OperationLogRecord(self.name, changed, errors=logs)


if __name__ == '__main__':
    from lib.operations import OperationPipeline
    
    pipeline = OperationPipeline([PartitionOperation()])
    pipeline.run_cli("Partition and Filesystem Configuration")

