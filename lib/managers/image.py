"""Chroot-based image and SD card manager implementations."""

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from types import TracebackType

from .base import BaseManager, CommandResult, DEFAULT_MOUNT_PATH
from .util import get_user_selection


class BaseImageManager(BaseManager):
    """Abstract base class for ARM image management via chroot with QEMU emulation."""

    def __init__(self, mountPath: str = DEFAULT_MOUNT_PATH, forceUnmount: bool = False,
                 allowInteractiveSudo: bool = True, defaultChrootUser: str | None = None,
                 keepMounted: bool = False) -> None:
        super().__init__(allowInteractiveSudo=allowInteractiveSudo)
        self.mountPath = mountPath
        self._mountedByUs = {}
        self._forceUnmount = forceUnmount
        self.keepMounted = keepMounted
        self._hackApplied = False
        self._qemuStaticBinary = 'qemu-arm-static'
        self.defaultChrootUser = defaultChrootUser
        projectRoot = Path(__file__).resolve().parents[2]
        self._scriptDir = str(projectRoot / 'os')

        sudoCheckResult = self.validate_sudo()
        if sudoCheckResult.returnCode != 0:
            raise RuntimeError(f"Sudo validation failed: {sudoCheckResult.stderr}")

        self._validate_target()
        self._perform_mount()
        self._setup_qemu()

    def run(self, command: str, sudo: bool = False) -> CommandResult:
        userspecArg = ''
        if not sudo and self.defaultChrootUser:
            userspecArg = f'--userspec={shlex.quote(self.defaultChrootUser)} '

        chrootCmd = (
            f'chroot {userspecArg}{shlex.quote(self.mountPath)} '
            f'/usr/bin/{self._qemuStaticBinary} /bin/bash -lc {shlex.quote(command)}'
        )
        stdout, stderr, code = self._run_local(chrootCmd, sudo=True)
        if code != 0:
            print(f"Error: {stderr}")
        return CommandResult(stdout, stderr, code)

    def exists(self, remotePath: str) -> bool:
        if remotePath.startswith('/'):
            remotePath = remotePath[1:]
        destPath = os.path.join(self.mountPath, remotePath)
        return os.path.exists(destPath)

    def put(self, localPath: str, remotePath: str, sudo: bool = False) -> None:
        self._put_local(localPath=localPath, remotePath=remotePath, sudo=sudo,
                        base_dir=self.mountPath, ensure_dir_when_not_sudo=True,
                        label='chroot')

    def get(self, remotePath: str, localPath: str, sudo: bool = False) -> None:
        relPath = remotePath[1:] if remotePath.startswith('/') else remotePath
        sourcePath = os.path.join(self.mountPath, relPath)

        if not os.path.exists(sourcePath):
            raise FileNotFoundError(f"File not found in chroot: {sourcePath}")

        if sudo:
            _, stderr, code = self._run_local(
                f'cp {shlex.quote(sourcePath)} {shlex.quote(localPath)}',
                sudo=True
            )
            if code != 0:
                raise IOError(f"Failed to copy {sourcePath} to {localPath}: {stderr}")
        else:
            shutil.copy(sourcePath, localPath)
        print(f"Downloaded (chroot) {remotePath} -> {localPath}")

    def _validate_target(self) -> None:
        raise NotImplementedError("Subclasses must implement _validate_target()")

    def _perform_mount(self) -> None:
        raise NotImplementedError("Subclasses must implement _perform_mount()")

    def _perform_unmount(self) -> None:
        self._run_unmount_script(forceUnmount=self._forceUnmount)

    def _run_unmount_script(self, forceUnmount: bool) -> None:
        scriptPath = os.path.join(self._scriptDir, 'unmnt_image.sh')
        forceFlag = ' force' if forceUnmount else ''
        _, stderr, code = self._run_local(
            f'bash {shlex.quote(scriptPath)} {shlex.quote(self.mountPath)}{forceFlag}'
        )
        if code != 0:
            print(f"Warning: Unmount script errors: {stderr}")

    def _apply_ldpreload_hack(self) -> None:
        try:
            preloadPath = os.path.join(self.mountPath, 'etc/ld.so.preload')
            backupPath = f"{preloadPath}.bck"
            if os.path.exists(preloadPath) and not os.path.exists(backupPath):
                _, stderr, code = self._run_local(
                    f'mv {shlex.quote(preloadPath)} {shlex.quote(backupPath)}',
                    sudo=True
                )
                if code == 0:
                    self._hackApplied = True
                    print("Applied ld.so.preload hack for chroot")
                else:
                    print(f"Warning: Could not apply ld.so.preload hack: {stderr}")
        except Exception as e:
            print(f"Warning: Exception applying ld.so.preload hack: {e}")

    def _undo_ldpreload_hack(self) -> None:
        if not self._hackApplied:
            return
        try:
            preloadPath = os.path.join(self.mountPath, 'etc/ld.so.preload')
            backupPath = f"{preloadPath}.bck"
            if os.path.exists(backupPath):
                _, stderr, code = self._run_local(
                    f'mv {shlex.quote(backupPath)} {shlex.quote(preloadPath)}',
                    sudo=True
                )
                if code == 0:
                    self._hackApplied = False
                    print("Restored ld.so.preload")
                else:
                    print(f"Warning: Could not restore ld.so.preload: {stderr}")
        except Exception as e:
            print(f"Warning: Exception restoring ld.so.preload: {e}")

    def _setup_qemu(self) -> None:
        try:
            self._qemuStaticBinary = self._detect_qemu_static_binary()
            stdout, _, code = self._run_local(f'which {shlex.quote(self._qemuStaticBinary)}')
            if code != 0:
                print(
                    f"Warning: {self._qemuStaticBinary} not found. "
                    "Install with: apt-get install qemu-user-static"
                )
                return

            qemuPath = stdout.strip()
            if qemuPath:
                destPath = os.path.join(self.mountPath, f'usr/bin/{self._qemuStaticBinary}')
                destDirResult = self._ensure_local_directory(os.path.dirname(destPath), sudo=True)
                if destDirResult.returnCode != 0:
                    print(f"Warning: Could not create QEMU destination directory: {destDirResult.stderr}")
                    return
                _, _, copyCode = self._run_local(
                    f'rsync -aq {shlex.quote(qemuPath)} {shlex.quote(destPath)}',
                    sudo=True
                )
                if copyCode != 0:
                    self._run_local(f'cp {shlex.quote(qemuPath)} {shlex.quote(destPath)}', sudo=True)
        except Exception as e:
            print(f"Warning: Could not setup QEMU: {e}")

    def _detect_qemu_static_binary(self) -> str:
        targetBashPath = os.path.join(self.mountPath, 'usr/bin/bash')
        stdout, stderr, code = self._run_local(
            f'readelf -h {shlex.quote(targetBashPath)}',
            sudo=True
        )

        if code != 0:
            print(f"Warning: Could not detect target architecture from {targetBashPath}: {stderr}")
            return 'qemu-arm-static'

        for line in stdout.splitlines():
            strippedLine = line.strip()
            if strippedLine.startswith('Machine:'):
                if 'AArch64' in strippedLine:
                    return 'qemu-aarch64-static'
                if 'ARM' in strippedLine:
                    return 'qemu-arm-static'

        print("Warning: Unknown target architecture in ELF header, defaulting to qemu-arm-static")
        return 'qemu-arm-static'

    def close(self) -> None:
        if self.keepMounted:
            print(f"Keeping mounts active at {self.mountPath} (keepMounted=True)")
            return
        if self._is_mount_active() or any(self._mountedByUs.values()):
            self._unmount()

    def _is_mount_active(self) -> bool:
        _, _, code = self._run_local(f'findmnt -T {shlex.quote(self.mountPath)}', sudo=True)
        return code == 0

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None,
                 exc_tb: TracebackType | None) -> bool:
        try:
            self.close()
        except Exception as cleanup_error:
            print(f"Warning: Error during cleanup: {cleanup_error}")
        return False

    def _unmount(self) -> None:
        try:
            self._undo_ldpreload_hack()
            self._perform_unmount()
            print(f"Unmounted: {self.mountPath}")
            self._mountedByUs.clear()
        except Exception as e:
            print(f"Error during unmount: {e}")
            raise


class ImageFileManager(BaseImageManager):
    NETWORK_FILESYSTEM_TYPES = {
        'nfs', 'nfs4', 'cifs', 'smb', 'smb2', 'smb3', 'sshfs', 'fuse.sshfs',
        'fuse', 'glusterfs', 'ceph', 'ceph-fuse', '9p', 'afp', 'davfs2'
    }
    STAGE_THRESHOLD_BYTES = int(2.5 * 1024 * 1024 * 1024)
    FIXTURE_PATH_FRAGMENT = os.path.normpath('tests/integration/fixtures')

    def __init__(self, imagePath: str, mountPath: str = DEFAULT_MOUNT_PATH,
                 forceUnmount: bool = False, allowInteractiveSudo: bool = True,
                 defaultChrootUser: str | None = None, keepMounted: bool = False) -> None:
        self.imagePath = imagePath
        self._stagedImagePath = None
        super().__init__(
            mountPath=mountPath,
            forceUnmount=forceUnmount,
            allowInteractiveSudo=allowInteractiveSudo,
            defaultChrootUser=defaultChrootUser,
            keepMounted=keepMounted,
        )

    def close(self) -> None:
        try:
            super().close()
        finally:
            self._cleanup_staged_image()

    def _validate_target(self) -> None:
        if not os.path.exists(self.imagePath):
            raise ValueError(f"Image file does not exist: {self.imagePath}")
        mode = os.stat(self.imagePath).st_mode
        if not stat.S_ISREG(mode):
            raise ValueError(f"Not a regular file: {self.imagePath}")

    def _perform_mount(self) -> None:
        existingMount = self._find_existing_loop_mount()
        if existingMount:
            print(f"Image already loop-mounted at: {existingMount}")
            print("Reusing existing mount (will not unmount on cleanup)")
            self.mountPath = existingMount
            self._mountedByUs = {}
            self._apply_ldpreload_hack()
            return

        imagePathForMount = self._prepare_image_path_for_mount()
        scriptPath = os.path.join(self._scriptDir, 'mnt_image.sh')
        stdout, stderr, code = self._run_local(
            f'bash {shlex.quote(scriptPath)} {shlex.quote(imagePathForMount)} {shlex.quote(self.mountPath)}'
        )
        if code != 0:
            self._cleanup_staged_image()
            raise RuntimeError(f"Failed to mount image: {stderr}")

        _, verifyErr, verifyCode = self._run_local(f'findmnt -T {self.mountPath}')
        if verifyCode != 0:
            self._run_unmount_script(forceUnmount=True)
            self._cleanup_staged_image()
            raise RuntimeError(
                f"Image mount verification failed at {self.mountPath}. "
                f"Script output: {stdout}\n{stderr}\n{verifyErr}"
            )

        print(f"Mounted image: {self.imagePath} -> {self.mountPath}")
        self._mountedByUs = {'root': True, 'boot': True}
        self._apply_ldpreload_hack()

    def _perform_unmount(self) -> None:
        try:
            super()._perform_unmount()
        finally:
            self._cleanup_staged_image()

    def _find_existing_loop_mount(self) -> str | None:
        try:
            absImagePath = os.path.abspath(self.imagePath)
            stdout, _, code = self._run_local(f'losetup -j {absImagePath}')
            if code != 0 or not stdout.strip():
                return None

            for line in stdout.splitlines():
                if not line.strip():
                    continue
                loopDev = line.split(':')[0].strip()
                with open('/proc/mounts', 'r', encoding='utf-8') as f:
                    for mountLine in f:
                        fields = mountLine.split()
                        if len(fields) < 2:
                            continue
                        sourceDev = fields[0]
                        isExactLoop = (sourceDev == loopDev)
                        isLoopPartition = (
                            sourceDev.startswith(f"{loopDev}p") and
                            sourceDev[len(loopDev) + 1:].isdigit()
                        )
                        if isExactLoop or isLoopPartition:
                            mountpoint = fields[1]
                            if not mountpoint.endswith('/boot'):
                                return mountpoint

            return None
        except Exception as e:
            print(f"Warning: Error checking for existing loop mount: {e}")
            return None

    def _prepare_image_path_for_mount(self) -> str:
        absImagePath = os.path.abspath(self.imagePath)
        if not self._is_network_mounted_path(absImagePath):
            return absImagePath

        imageSizeBytes = os.path.getsize(absImagePath)
        shouldAutoStage = (
            self._is_in_integration_fixtures(absImagePath) or
            imageSizeBytes <= self.STAGE_THRESHOLD_BYTES
        )

        if shouldAutoStage:
            return self._stage_image_to_temp(absImagePath, imageSizeBytes)

        memoryAvailableBytes = self._get_available_memory_bytes()
        tmpFreeBytes = self._get_tmp_available_bytes()
        if not self._confirm_stage_large_image(imageSizeBytes, memoryAvailableBytes, tmpFreeBytes):
            raise RuntimeError(
                f"Image is on a network mount and is too large for automatic staging: {absImagePath}. "
                f"Size={self._format_bytes(imageSizeBytes)}, threshold={self._format_bytes(self.STAGE_THRESHOLD_BYTES)}"
            )
        return self._stage_image_to_temp(absImagePath, imageSizeBytes)

    def _is_network_mounted_path(self, path: str) -> bool:
        targetPath = shlex.quote(path)
        stdout, _, code = self._run_local(f'findmnt -n -o FSTYPE --target {targetPath}')
        if code != 0:
            return False
        fsType = stdout.strip().lower()
        if not fsType:
            return False
        return fsType in self.NETWORK_FILESYSTEM_TYPES or fsType.startswith('fuse.')

    def _is_in_integration_fixtures(self, path: str) -> bool:
        normalizedPath = os.path.normpath(os.path.abspath(path))
        return self.FIXTURE_PATH_FRAGMENT in normalizedPath

    def _stage_image_to_temp(self, sourcePath: str, imageSizeBytes: int) -> str:
        tmpFreeBytes = self._get_tmp_available_bytes()
        if tmpFreeBytes is not None and tmpFreeBytes < imageSizeBytes:
            raise RuntimeError(
                f"Insufficient free space in {tempfile.gettempdir()} for staging. "
                f"Required={self._format_bytes(imageSizeBytes)}, available={self._format_bytes(tmpFreeBytes)}"
            )

        fd, stagedPath = tempfile.mkstemp(prefix='os-config-image-', suffix='.img', dir=tempfile.gettempdir())
        os.close(fd)
        print(
            f"Staging image to local temp for mount: {sourcePath} -> {stagedPath} "
            f"({self._format_bytes(imageSizeBytes)})"
        )
        shutil.copy2(sourcePath, stagedPath)
        self._stagedImagePath = stagedPath
        return stagedPath

    def _cleanup_staged_image(self) -> None:
        if not self._stagedImagePath:
            return
        stagedPath = self._stagedImagePath
        self._stagedImagePath = None
        try:
            if os.path.exists(stagedPath):
                os.remove(stagedPath)
        except OSError as e:
            print(f"Warning: Could not remove staged image {stagedPath}: {e}")

    def _confirm_stage_large_image(self, imageSizeBytes: int, memoryAvailableBytes: int | None,
                                   tmpFreeBytes: int | None) -> bool:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print(
                "Large network-mounted image detected, but no interactive terminal is available "
                "to confirm staging."
            )
            return False

        memoryText = self._format_bytes(memoryAvailableBytes) if memoryAvailableBytes is not None else 'unknown'
        tmpText = self._format_bytes(tmpFreeBytes) if tmpFreeBytes is not None else 'unknown'

        print("\nLarge image is on a network-mounted filesystem.")
        print(f"- Image size: {self._format_bytes(imageSizeBytes)}")
        print(f"- Available memory: {memoryText}")
        print(f"- Free space in {tempfile.gettempdir()}: {tmpText}")
        print("Staging copies the image to local temp before mounting.")

        while True:
            response = input("Proceed with local staging? [y/N]: ").strip().lower()
            if response in ('y', 'yes'):
                return True
            if response in ('', 'n', 'no'):
                return False
            print("Please respond with 'y' or 'n'.")

    @staticmethod
    def _get_available_memory_bytes() -> int | None:
        try:
            with open('/proc/meminfo', 'r', encoding='utf-8') as memInfo:
                for line in memInfo:
                    if line.startswith('MemAvailable:'):
                        parts = line.split()
                        if len(parts) >= 2 and parts[1].isdigit():
                            return int(parts[1]) * 1024
        except OSError:
            return None
        return None

    @staticmethod
    def _get_tmp_available_bytes() -> int | None:
        try:
            return shutil.disk_usage(tempfile.gettempdir()).free
        except OSError:
            return None

    @staticmethod
    def _format_bytes(sizeBytes: int | None) -> str:
        if sizeBytes is None:
            return 'unknown'
        value = float(sizeBytes)
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        unitIndex = 0
        while value >= 1024 and unitIndex < len(units) - 1:
            value /= 1024
            unitIndex += 1
        return f"{value:.2f} {units[unitIndex]}"


class SDCardManager(BaseImageManager):
    """Execute operations on a mounted SD card via chroot with QEMU emulation."""

    def __init__(self, devicePath: str, mountPath: str = DEFAULT_MOUNT_PATH,
                 forceUnmount: bool = False, allowInteractiveSudo: bool = True,
                 defaultChrootUser: str | None = None, keepMounted: bool = False) -> None:
        self.devicePath = devicePath
        self._bootMountPath = None
        super().__init__(
            mountPath=mountPath,
            forceUnmount=forceUnmount,
            allowInteractiveSudo=allowInteractiveSudo,
            defaultChrootUser=defaultChrootUser,
            keepMounted=keepMounted,
        )

    def _validate_target(self) -> None:
        if not os.path.exists(self.devicePath):
            raise ValueError(f"Device does not exist: {self.devicePath}")
        mode = os.stat(self.devicePath).st_mode
        if not stat.S_ISBLK(mode):
            raise ValueError(f"Not a block device: {self.devicePath}")

    def _perform_mount(self) -> None:
        partitions = self._detect_partitions()
        if not partitions.get('root'):
            raise RuntimeError("Could not find root partition (ext4)")

        rootPartition = partitions['root']
        bootPartition = partitions.get('boot')

        if partitions.get('root_mountpoint'):
            print(f"Root partition already mounted at: {partitions['root_mountpoint']}")
            print("Reusing existing mount (will not unmount on cleanup)")
            self.mountPath = partitions['root_mountpoint']
            self._mountedByUs['root'] = False
        else:
            mkdirResult = self._ensure_local_directory(self.mountPath, sudo=True)
            if mkdirResult.returnCode != 0:
                raise RuntimeError(f"Failed to create mount directory {self.mountPath}: {mkdirResult.stderr}")
            _, stderr, code = self._run_local(f'mount {rootPartition} {self.mountPath}', sudo=True)
            if code != 0:
                raise RuntimeError(f"Failed to mount root partition: {stderr}")
            print(f"Mounted root: {rootPartition} -> {self.mountPath}")
            self._mountedByUs['root'] = True

        if bootPartition:
            self._bootMountPath = os.path.join(self.mountPath, 'boot')
            if partitions.get('boot_mountpoint'):
                print(f"Boot partition already mounted at: {partitions['boot_mountpoint']}")
                self._mountedByUs['boot'] = (partitions['boot_mountpoint'] == self._bootMountPath)
            else:
                mkdirResult = self._ensure_local_directory(self._bootMountPath, sudo=True)
                if mkdirResult.returnCode != 0:
                    print(f"Warning: Failed to create boot mount directory: {mkdirResult.stderr}")
                    self._mountedByUs['boot'] = False
                else:
                    _, stderr, code = self._run_local(
                        f'mount {bootPartition} {self._bootMountPath}',
                        sudo=True
                    )
                    if code != 0:
                        print(f"Warning: Failed to mount boot partition: {stderr}")
                        self._mountedByUs['boot'] = False
                    else:
                        print(f"Mounted boot: {bootPartition} -> {self._bootMountPath}")
                        self._mountedByUs['boot'] = True

        self._apply_ldpreload_hack()

    def _detect_partitions(self) -> dict:
        stdout, stderr, code = self._run_local(
            f'lsblk --json -o NAME,SIZE,FSTYPE,MOUNTPOINT,LABEL {self.devicePath}'
        )
        if code != 0:
            raise RuntimeError(f"Failed to run lsblk: {stderr}")

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse lsblk output: {e}") from e

        result = {}
        if 'blockdevices' in data and data['blockdevices']:
            device = data['blockdevices'][0]
            if 'children' in device:
                for partition in device['children']:
                    partName = partition.get('name', '')
                    fstype = partition.get('fstype', '')
                    mountpoint = partition.get('mountpoint')
                    if fstype in ['vfat', 'fat32', 'fat16']:
                        result['boot'] = f"/dev/{partName}"
                        result['boot_mountpoint'] = mountpoint
                    elif fstype == 'ext4':
                        result['root'] = f"/dev/{partName}"
                        result['root_mountpoint'] = mountpoint
        return result

    @classmethod
    def detect_usb_devices(cls) -> list[dict]:
        result = subprocess.run(
            ['lsblk', '--json', '-o', 'NAME,SIZE,VENDOR,MODEL,TRAN,RM,LABEL,MOUNTPOINT,TYPE'],
            capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            print(f"Warning: Failed to run lsblk: {result.stderr}")
            return []
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        devices = []
        if 'blockdevices' in data:
            for device in data['blockdevices']:
                isRemovable = device.get('rm') in (True, '1', 1)
                if device.get('type') == 'disk' and isRemovable and device.get('tran') == 'usb':
                    mountpoints = []
                    if 'children' in device:
                        for child in device['children']:
                            mp = child.get('mountpoint')
                            if mp:
                                mountpoints.append(mp)
                    devices.append({
                        'device': f"/dev/{device['name']}",
                        'size': device.get('size', 'Unknown'),
                        'vendor': (device.get('vendor', '') or 'Unknown').strip(),
                        'model': (device.get('model', '') or 'Unknown').strip(),
                        'label': device.get('label', ''),
                        'mounted': len(mountpoints) > 0,
                        'mountpoints': mountpoints
                    })
        return devices

    @classmethod
    def from_interactive_selection(cls, mountPath: str = DEFAULT_MOUNT_PATH,
                                   allowInteractiveSudo: bool = True,
                                   defaultChrootUser: str | None = None) -> 'SDCardManager | None':
        devices = cls.detect_usb_devices()
        if not devices:
            raise RuntimeError("No USB devices found")

        print("\n=== USB Devices Found ===")
        options = []
        for i, dev in enumerate(devices, 1):
            mountStatus = "mounted" if dev['mounted'] else "unmounted"
            mountInfo = f" at {', '.join(dev['mountpoints'])}" if dev['mountpoints'] else ""
            option = f"{dev['device']} - {dev['size']} {dev['vendor']} {dev['model']} [{mountStatus}{mountInfo}]"
            options.append(option)
            print(f"{i}. {option}")

        selectedIdx = get_user_selection(options, title="Select USB device:", addExit="Abort (back to main menu)")
        if selectedIdx is None:
            return None

        selectedDevice = devices[selectedIdx]
        print(f"\nSelected: {selectedDevice['device']} - {selectedDevice['size']} {selectedDevice['vendor']} {selectedDevice['model']}")
        confirmedIdx = get_user_selection(["No (back to main menu)", "Yes"], title="Confirm device selection?", addExit=False)
        if confirmedIdx != 1:
            return None

        return cls(
            devicePath=selectedDevice['device'],
            mountPath=mountPath,
            allowInteractiveSudo=allowInteractiveSudo,
            defaultChrootUser=defaultChrootUser,
        )


__all__ = ['BaseImageManager', 'ImageFileManager', 'SDCardManager']
