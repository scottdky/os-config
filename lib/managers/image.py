"""Chroot-based image and SD card manager implementations."""

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType

from .base import BaseManager, CommandResult, DEFAULT_MOUNT_PATH
from .util import get_single_selection


class BaseImageManager(BaseManager):
    """Abstract base class for ARM image management via chroot with QEMU emulation."""

    def __init__(self, mountPath: str = DEFAULT_MOUNT_PATH,
                 allowInteractiveSudo: bool = True, defaultChrootUser: str | None = None,
                 keepMounted: bool = False) -> None:
        super().__init__(allowInteractiveSudo=allowInteractiveSudo)
        self.mountPath = mountPath
        self._mountedByUs = {}
        self.keepMounted = keepMounted
        self._hackApplied = False
        self._qemuStaticBinary = 'qemu-arm-static'
        self.defaultChrootUser = defaultChrootUser
        projectRoot = Path(__file__).resolve().parents[2]
        self._scriptDir = str(projectRoot / 'os')

        sudoCheckResult = self.validate_sudo()
        if sudoCheckResult.returnCode != 0:
            raise RuntimeError(f"Sudo validation failed: {sudoCheckResult.stderr}")

    def __enter__(self) -> "BaseImageManager":
        self._validate_target()
        self._perform_mount()
        self._setup_qemu()
        return self

    def is_os_image(self) -> bool:
        """Check if the target is an OS image (img file or sdcard)"""
        return True

    def run(self, command: str, sudo: bool = False) -> CommandResult:
        userspecArg = ''
        if not sudo and self.defaultChrootUser:
            userspecArg = f'--userspec={shlex.quote(self.defaultChrootUser)} '

        chrootCmd = (
            f'chroot {userspecArg}{shlex.quote(self.mountPath)} '
            f'/usr/bin/{self._qemuStaticBinary} /bin/bash -lc {shlex.quote(command)}'
        )
        commandResult = self.run_local(chrootCmd, sudo=True)
        if commandResult.returnCode != 0:
            print(f"Error: {commandResult.stderr}")
        return commandResult

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
            _, stderr, code = self.run_local(
                f'cp {shlex.quote(sourcePath)} {shlex.quote(localPath)}',
                sudo=True
            )
            if code != 0:
                raise IOError(f"Failed to copy {sourcePath} to {localPath}: {stderr}")
        else:
            shutil.copy(sourcePath, localPath)
        print(f"Downloaded (chroot) {remotePath} -> {localPath}")

    def systemd_unmask(self, serviceName: str, sudo: bool = False) -> bool:
        """Unmask a systemd service directly on the filesystem for offline images.

        Args:
            serviceName (str): Name of the service (e.g. 'hwclock.service').
            sudo (bool): Whether to run as sudo.

        Returns:
            bool: True if the command succeeded.
        """

        paths = [
            f"/etc/systemd/system/{serviceName}",
            f"/lib/systemd/system/{serviceName}",
            f"/usr/lib/systemd/system/{serviceName}"
        ]
        targetPaths = " ".join(paths)
        res = self.run(f"rm -f {targetPaths}", sudo=sudo)
        return res.returnCode == 0

    def systemd_mask(self, serviceName: str, sudo: bool = False) -> bool:
        """Mask a systemd service directly on the filesystem for offline images.

        Args:
            serviceName (str): Name of the service.
            sudo (bool): Whether to run as sudo.

        Returns:
            bool: True if the command succeeded.
        """
        linkPath = f"/etc/systemd/system/{serviceName}"
        res = self.run(f"ln -sf /dev/null {linkPath}", sudo=sudo)
        return res.returnCode == 0

    def systemd_enable(self, serviceName: str, servicePath: str | None = None, targetName: str = "sysinit.target", now: bool = False, sudo: bool = False) -> bool:
        """Enable a systemd service by manually linking it for offline images.

        Note: The BaseManager implementation uses systemctl. Subclasses (like offline ImageManager) may override this to use file links directly.

        Args:
            serviceName (str): Name of the service (e.g. 'hwclock.service').
            servicePath (str | None): Absolute target path of the unit file (used by offline overrides).
            targetName (str): Systemd target to hook into. (used by offline overrides).
            now (bool): Whether to pass --now (ignored in offline manager).
            sudo (bool): Whether to run as sudo.

        Returns:
            bool: True if the command succeeded.
        """
        if not servicePath:
            # Fallback if no target path is supplied for symlink, look up common paths
            servicePath = f"/lib/systemd/system/{serviceName}"

        wantsDir = f"/etc/systemd/system/{targetName}.wants"
        self.run(f"mkdir -p {wantsDir}", sudo=sudo)

        linkPath = f"{wantsDir}/{serviceName}"
        res = self.run(f"ln -sf {servicePath} {linkPath}", sudo=sudo)
        return res.returnCode == 0

    def systemd_disable(self, serviceName: str, targetName: str = "sysinit.target", now: bool = False, sudo: bool = False) -> bool:
        """Disable a systemd service by removing its wants link for offline images.

        Args:
            serviceName (str): Name of the service.
            targetName (str): Systemd target it hooks into.
            now (bool): Whether to pass --now (ignored in offline manager).
            sudo (bool): Whether to run as sudo.

        Returns:
            bool: True if the command succeeded.
        """
        linkPath = f"/etc/systemd/system/{targetName}.wants/{serviceName}"
        res = self.run(f"rm -f {linkPath}", sudo=sudo)
        return res.returnCode == 0

    def systemd_is_enabled(self, serviceName: str, sudo: bool = False) -> bool:
        """Check if a systemd service is enabled by querying symlink state or calling systemctl softly."""
        # Check standard wants paths first since systemctl might complain without dbus
        wantsOut = self.run(f"find /etc/systemd/system/*.wants -name {shlex.quote(serviceName)} 2>/dev/null", sudo=sudo)
        if wantsOut.returnCode == 0 and wantsOut.stdout.strip():
            return True

        # Fallback to systemctl without dbus
        res = self.run(f"systemctl --quiet is-enabled {serviceName}", sudo=sudo)
        return res.returnCode == 0

    def systemd_is_active(self, serviceName: str, sudo: bool = False) -> bool:
        """Check if a systemd service is currently active. Never true for offline mounts."""
        return False

    def _validate_target(self) -> None:
        raise NotImplementedError("Subclasses must implement _validate_target()")

    def _perform_mount(self) -> None:
        raise NotImplementedError("Subclasses must implement _perform_mount()")

    def _perform_unmount(self, forceUnmount: bool = False) -> CommandResult:
        return self._run_unmount_script(forceUnmount=forceUnmount)

    def _run_unmount_script(self, forceUnmount: bool = False) -> CommandResult:
        scriptPath = os.path.join(self._scriptDir, 'unmnt_image.sh')
        forceFlag = ' force' if forceUnmount else ''
        return self.run_local(
            f'bash {shlex.quote(scriptPath)} {shlex.quote(self.mountPath)}{forceFlag}'
        )

    def _apply_ldpreload_hack(self) -> None:
        try:
            preloadPath = os.path.join(self.mountPath, 'etc/ld.so.preload')
            backupPath = f"{preloadPath}.bck"
            if os.path.exists(preloadPath) and not os.path.exists(backupPath):
                _, stderr, code = self.run_local(
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
                _, stderr, code = self.run_local(
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
            stdout, _, code = self.run_local(f'which {shlex.quote(self._qemuStaticBinary)}')
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
                _, _, copyCode = self.run_local(
                    f'rsync -aq {shlex.quote(qemuPath)} {shlex.quote(destPath)}',
                    sudo=True
                )
                if copyCode != 0:
                    self.run_local(f'cp {shlex.quote(qemuPath)} {shlex.quote(destPath)}', sudo=True)
        except Exception as e:
            print(f"Warning: Could not setup QEMU: {e}")

    def _detect_qemu_static_binary(self) -> str:
        targetBashPath = os.path.join(self.mountPath, 'usr/bin/bash')
        stdout, stderr, code = self.run_local(
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

    @contextmanager
    def temporarily_unmounted(self):
        """Temporarily tears down chroot + loop bindings for low-level disk operations."""
        # Unwind the ld.so.preload hack first
        self._undo_ldpreload_hack()
        self._perform_unmount(forceUnmount=True)
        try:
            yield
        finally:
            self._perform_mount()
            self._setup_qemu()

    def close(self) -> None:
        if self.keepMounted:
            print(f"Keeping mounts active at {self.mountPath} (keepMounted=True)")
            return
        if self._is_mount_active() and any(self._mountedByUs.values()):
            self._unmount()

    def _handle_existing_mount(self, existingMount: str) -> None:
        """Prompt user to keep or unmount an existing mount on exit."""
        self.mountPath = existingMount
        self._apply_ldpreload_hack()

        if self.keepMounted:
            print("Reusing existing mount (will keep mounted on cleanup due to keepMounted=True)")
            self._mountedByUs = {'root': False}
            return

        if self._supports_interactive_unmount_prompt():
            val = input(f"Image is already mounted at {existingMount}. Keep it mounted on exit? [Y/n]: ").strip().lower()
            if val in ['n', 'no', 'false', '0']:
                print("Will unmount on cleanup.")
                self._mountedByUs = {'root': True}
                return

        print("Reusing existing mount (will not unmount on cleanup)")
        self._mountedByUs = {'root': False}

    def _is_mount_active(self) -> bool:
        _, _, code = self.run_local(f'findmnt -T {shlex.quote(self.mountPath)}', sudo=True)
        return code == 0

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None,
                 exc_tb: TracebackType | None) -> bool:
        try:
            self.close()
        except Exception as cleanup_error:
            print(f"Warning: Error during cleanup: {cleanup_error}")
        return False

    def _unmount(self) -> None:
        self._undo_ldpreload_hack()

        if self._attempt_unmount(forceUnmount=False):
            return

        if not self._supports_interactive_unmount_prompt():
            print(
                f"Warning: Failed to unmount {self.mountPath}. "
                "Resolve active usages and rerun cleanup manually."
            )
            return

        self._prompt_and_retry_unmount()

    def _attempt_unmount(self, forceUnmount: bool = False) -> bool:
        """Attempt one unmount pass and return whether mount is no longer active."""
        unmountResult = self._perform_unmount(forceUnmount=forceUnmount)
        isStillMounted = self._is_mount_active()
        if not isStillMounted:
            print(f"Unmounted: {self.mountPath}")
            self._mountedByUs.clear()
            return True

        mode = 'force' if forceUnmount else 'normal'
        stderrText = unmountResult.stderr.strip()
        if stderrText:
            print(f"Warning: {mode} unmount failed for {self.mountPath}: {stderrText}")
        else:
            print(f"Warning: {mode} unmount failed for {self.mountPath}.")
        return False

    @staticmethod
    def _supports_interactive_unmount_prompt() -> bool:
        """Return True when stdin/stdout are interactive terminals."""
        return sys.stdin.isatty() and sys.stdout.isatty()

    def _prompt_and_retry_unmount(self) -> None:
        """Prompt user through retry/force/exit choices after unmount failure."""
        print(
            "Resolve processes/files using the mount path, then press Enter to retry unmount."
        )

        while True:
            input('Press Enter to retry unmount...')
            if self._attempt_unmount(forceUnmount=False):
                return

            actionIdx = get_single_selection(
                ['Try again', 'Force unmount', 'Exit without unmounting'],
                title='Unmount still failed. Choose next action:',
                addExit=False,
            )

            if actionIdx == 0:
                continue

            if actionIdx == 1:
                if self._attempt_unmount(forceUnmount=True):
                    return
                continue

            print(f"Leaving mount active at {self.mountPath}.")
            return


class ImageFileManager(BaseImageManager):
    NETWORK_FILESYSTEM_TYPES = {
        'nfs', 'nfs4', 'cifs', 'smb', 'smb2', 'smb3', 'sshfs', 'fuse.sshfs',
        'fuse', 'glusterfs', 'ceph', 'ceph-fuse', '9p', 'afp', 'davfs2'
    }
    STAGE_THRESHOLD_BYTES = int(2.5 * 1024 * 1024 * 1024)
    FIXTURE_PATH_FRAGMENT = os.path.normpath('tests/integration/fixtures')

    def __init__(self, imagePath: str, mountPath: str = DEFAULT_MOUNT_PATH,
                 allowInteractiveSudo: bool = True,
                 defaultChrootUser: str | None = None, keepMounted: bool = False) -> None:
        self.imagePath = imagePath
        self._stagedImagePath = None
        super().__init__(
            mountPath=mountPath,
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
        existingTargetMount = self._find_existing_mount_at_target_path()
        if existingTargetMount:
            self._handle_existing_mount(existingTargetMount)
            return

        existingMount = self._find_existing_loop_mount()
        if existingMount:
            self._handle_existing_mount(existingMount)
            return

        imagePathForMount = self._prepare_image_path_for_mount()
        self._preflight_mountability(imagePathForMount)
        scriptPath = os.path.join(self._scriptDir, 'mnt_image.sh')
        stdout, stderr, code = self.run_local(
            f'bash {shlex.quote(scriptPath)} {shlex.quote(imagePathForMount)} {shlex.quote(self.mountPath)}'
        )
        if code != 0:
            self._cleanup_staged_image()
            raise RuntimeError(f"Failed to mount image: {stderr}")

        _, verifyErr, verifyCode = self.run_local(f'findmnt -T {self.mountPath}')
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

    def _find_existing_mount_at_target_path(self) -> str | None:
        """Return target mount path when already active, otherwise None."""
        stdout, _, code = self.run_local(
            f'findmnt -n -o TARGET --target {shlex.quote(self.mountPath)}',
            sudo=True,
        )
        if code != 0:
            return None

        mountedTarget = stdout.strip().splitlines()[0] if stdout.strip() else ''
        if os.path.realpath(mountedTarget) == os.path.realpath(self.mountPath):
            return self.mountPath
        return None

    def _perform_unmount(self, forceUnmount: bool = False) -> CommandResult:
        try:
            return super()._perform_unmount(forceUnmount=forceUnmount)
        finally:
            self._cleanup_staged_image()

    def _find_existing_loop_mount(self) -> str | None:
        try:
            absImagePath = os.path.abspath(self.imagePath)
            stdout, _, code = self.run_local(f'losetup -j {absImagePath}')
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
        stdout, _, code = self.run_local(f'findmnt -n -o FSTYPE --target {targetPath}')
        if code != 0:
            return False
        fsType = stdout.strip().lower()
        if not fsType:
            return False
        return fsType in self.NETWORK_FILESYSTEM_TYPES or fsType.startswith('fuse.')

    def _preflight_mountability(self, imagePath: str) -> None:
        """Validate that an image path is mountable before calling mount scripts."""
        absImagePath = os.path.abspath(imagePath)

        if self._is_network_mounted_path(absImagePath):
            raise RuntimeError(
                f"Image is on a network-backed filesystem: {absImagePath}. "
                "Please place a local copy on a local drive and retry."
            )

        probeResult = self.run_local(
            f'losetup -f --show --read-only {shlex.quote(absImagePath)}',
            sudo=True,
        )

        loopDevice = probeResult.stdout.strip() if probeResult.returnCode == 0 else ''
        if not loopDevice:
            raise RuntimeError(
                f"Mountability probe failed for image: {absImagePath}. "
                "Unable to attach loop device. Place the image on a local drive and retry."
            )

        self.run_local(f'losetup -d {shlex.quote(loopDevice)}', sudo=True)

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
                 allowInteractiveSudo: bool = True,
                 defaultChrootUser: str | None = None, keepMounted: bool = False) -> None:
        self.devicePath = devicePath
        super().__init__(
            mountPath=mountPath,
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

        if partitions.get('root_mountpoint'):
            self._handle_existing_mount(partitions['root_mountpoint'])
            return

        scriptPath = os.path.join(self._scriptDir, 'mnt_sdcard.sh')
        stdout, stderr, code = self.run_local(
            f'bash {shlex.quote(scriptPath)} {shlex.quote(self.devicePath)} {shlex.quote(self.mountPath)}'
        )
        if code != 0:
            raise RuntimeError(f"Failed to mount SD card: {stderr}")

        _, verifyErr, verifyCode = self.run_local(f'findmnt -T {shlex.quote(self.mountPath)}', sudo=True)
        if verifyCode != 0:
            self._run_unmount_script(forceUnmount=True)
            raise RuntimeError(
                f"SD card mount verification failed at {self.mountPath}. "
                f"Script output: {stdout}\n{stderr}\n{verifyErr}"
            )

        print(f"Mounted SD card: {self.devicePath} -> {self.mountPath}")
        self._mountedByUs['root'] = True
        self._mountedByUs['boot'] = bool(partitions.get('boot'))
        self._apply_ldpreload_hack()
        return

    def _detect_partitions(self) -> dict:
        stdout, stderr, code = self.run_local(
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

        selectedIdx = get_single_selection(options, title="Select USB device:", addExit="Abort (back to main menu)")
        if selectedIdx is None:
            return None

        selectedDevice = devices[selectedIdx]
        print(f"\nSelected: {selectedDevice['device']} - {selectedDevice['size']} {selectedDevice['vendor']} {selectedDevice['model']}")
        confirmedIdx = get_single_selection(["No (back to main menu)", "Yes"], title="Confirm device selection?", addExit=False)
        if confirmedIdx != 1:
            return None

        return cls(
            devicePath=selectedDevice['device'],
            mountPath=mountPath,
            allowInteractiveSudo=allowInteractiveSudo,
            defaultChrootUser=defaultChrootUser,
        )


__all__ = ['BaseImageManager', 'ImageFileManager', 'SDCardManager']
