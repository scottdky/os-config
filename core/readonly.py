#!/usr/bin/env python3
"""Make OS Root Filesystem Readonly.

Configures Raspberry Pi OS to mount as Readonly at boot. Leaves
an initialization script that will apply the RO flags after the
first clean boot.
"""
import sys
import os
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT
from lib.managers import BaseManager
from lib.operations import OperationBase, OperationLogRecord, OperationPipeline
from lib.fstab import Fstab


class ReadonlyOperation(OperationBase):
    """Operation class for setting up a read-only filesystem."""

    READONLY = 'readonly'
    REQUIRED_CONFIGS = {}

    def __init__(self) -> None:
        super().__init__(moduleName='readonly', name=self.READONLY, requiredConfigs=self.REQUIRED_CONFIGS)

    def is_manager_compatible(self, mgr: BaseManager) -> tuple[bool, str]:
        # Only Raspberry Pi OS creates the conditions necessary for these exact changes
        if not mgr.is_raspi_os():
            return False, "Target OS is not Raspberry Pi OS."
        # This setup must be run as an offline image or chroot, doing this mid-air on a running Pi is dicey.
        # But we could optionally relax this later if needed.
        if not mgr.is_os_image():
            return False, "Target must be a mounted OS image."

        return super().is_manager_compatible(mgr)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        """Prompt user for missing configuration values."""
        return {}

    def _setup_packages(self, mgr: BaseManager) -> bool:
        changed = False

        # Turn swap off before removal if present
        if mgr.is_pkg_installed('dphys-swapfile'):
            mgr.run('dphys-swapfile swapoff', sudo=True)

        for pkg in ['triggerhappy', 'logrotate', 'dphys-swapfile', 'rsyslog']:
            changed |= mgr.remove_pkg(pkg, purge=True)

        for pkg in ['busybox-syslogd', 'chrony']:
            changed |= mgr.install_pkg(pkg)

        return changed

    def _move_and_link(self, mgr: BaseManager, target: str, link_dest: str) -> bool:
        """Helper to move a target to a backup cleanly and symlink to a volatile destination.
        Example target: /var/lib/dhcp
        Example link_dest: /tmp/dhcp
        """
        changed = False
        link_parent = os.path.dirname(link_dest) # To check /tmp exists or other mounts

        # If it is already a symlink, assume we're good
        chk_link = mgr.run(f"test -L {target}", sudo=True)
        if chk_link.returnCode == 0:
            return False

        chk_exists = mgr.exists(target)
        if chk_exists:
            target_bck = f"{target}.bck"
            mgr.run(f"mv {target} {target_bck}", sudo=True)

            # Since some systemd setups might fail to start if the symlinked location
            # doesn't exist *before* they start, making the symlink just point to /tmp
            # is best, since /tmp is reliably built before networking starts
            mgr.run(f"ln -s {link_dest} {target}", sudo=True)
            changed = True
        else:
            # Maybe the dir does not exist, just create the symlink directly
            mgr.run(f"ln -s {link_dest} {target}", sudo=True)
            changed = True

        return changed

    def _setup_symlinks(self, mgr: BaseManager) -> bool:
        changed = False

        changed |= self._move_and_link(mgr, '/var/lib/dhcp', '/tmp')
        changed |= self._move_and_link(mgr, '/var/lib/dhcpcd5', '/tmp')

        # Handle spool and cron together before /var/spool is replaced
        if not (mgr.run('test -L /var/spool', sudo=True).returnCode == 0):
            if mgr.exists('/var/spool/cron'):
                mgr.run('mkdir -p /etc/crontab_spool', sudo=True)
                mgr.run('cp -R /var/spool/cron/* /etc/crontab_spool/ 2>/dev/null || true', sudo=True)
            changed |= self._move_and_link(mgr, '/var/spool', '/tmp')
            mgr.run('ln -s /etc/crontab_spool /var/spool/cron', sudo=True)

        # specific file logic for resolv.conf
        if not (mgr.run('test -L /etc/resolv.conf').returnCode == 0):
            mgr.run('mv /etc/resolv.conf /etc/resolv.conf.bck', sudo=True)
            mgr.run('touch /tmp/dhcpcd.resolv.conf', sudo=True)
            mgr.run('ln -s /tmp/dhcpcd.resolv.conf /etc/resolv.conf', sudo=True)
            changed = True

        # specific chrony temp fix
        chrony_dest = '/etc/systemd/system/chronyd.service'
        if mgr.exists(chrony_dest):
            if mgr.set_config_line(chrony_dest, 'PrivateTmp=no', match='PrivateTmp=yes', sudo=True):
                changed = True

        # Fix systemd timesyncd conflict configuration
        timesyncd_conf = '/lib/systemd/system/systemd-timesyncd.service.d/disable-with-time-daemon.conf'
        if mgr.exists(timesyncd_conf):
            if mgr.set_config_line(timesyncd_conf, '#ConditionFileIsExecutable=!/usr/sbin/chronyd', match='ConditionFileIsExecutable=!/usr/sbin/chronyd', sudo=True):
                changed = True

        # Manage chromium
        chromium_cfg = '/home/pi/.config/chromium'
        if mgr.run(f'test -d {chromium_cfg}', sudo=True).returnCode == 0:
            changed |= self._move_and_link(mgr, chromium_cfg, '/tmp')

        return changed

    def _setup_fstab(self, mgr: BaseManager) -> bool:
        """ Setup tmpfs mounts in fstab for directories we want to be volatile.

        This is needed for the first boot, then the RO service will switch to
        remounting root as RO and the tmpfs mounts will ensure those dirs are
        still writable."""
        changed = False

        # setup the tmpfs directories.
        # Also, contrary to the various articles on read-only system, we don't need a tmpfs mount for
        # /run or /var/run. /run is already a tmpfs mount in debian-jessie and /var/run is symlinked to it.
        mounts = [
            ('/tmp', 'tmpfs', 'defaults,nosuid,nodev,noatime,mode=1777'),
            ('/var/log', 'tmpfs', 'defaults,nosuid,nodev,noatime,mode=0755'),
            ('/var/tmp', 'tmpfs', 'defaults,nosuid,nodev,noatime,mode=0755'),
            ('/var/lib/systemd', 'tmpfs', 'defaults,nosuid,nodev,noatime,mode=0755'),
            # preserve timestamps of sudo usage
            ('/var/lib/sudo', 'tmpfs', 'defaults,nosuid,nodev,noatime,mode=0755'),
        ]

        # fix time update issues with chrony by making its lib dir tmpfs
        if mgr.exists('/var/lib/chrony'):
            mounts.append(('/var/lib/chrony', 'tmpfs', 'nosuid,nodev'))

        # samba - these are needed for samba to start (smbd, nmbd)
        if mgr.exists('/var/lib/samba'):
            mounts.extend([
                ('/var/lib/samba', 'tmpfs', 'defaults,nosuid,nodev,noatime,mode=0755'),
                ('/var/cache/samba', 'tmpfs', 'defaults,nosuid,nodev,noatime,mode=0755'),
                ('/run/samba', 'tmpfs', 'defaults,nosuid,nodev,noatime,mode=0755'),
                ('/var/lib/samba/private', 'tmpfs', 'defaults,nosuid,nodev,noatime,mode=0755'),
                ('/var/log/samba', 'tmpfs', 'defaults,nosuid,nodev,noatime,mode=0755'),
            ])

        fstab = Fstab()
        fstab.load(mgr)

        # Build list of active mount points
        mounted_dirs = [line.parts['mount'] for line in fstab.lines if line.parts]

        has_changes = False
        for target, fstype, options in mounts:
            if target not in mounted_dirs:
                # Add the new line for the mount
                # FstabLine parses: device, mount, fstype, options, dump, fsck
                new_line_str = f"tmpfs\t{target}\t{fstype}\t{options}\t0\t0"
                # Need to use the fstab line constructor properly
                from lib.fstab import FstabLine
                fstab.lines.append(FstabLine(new_line_str))
                has_changes = True

        if has_changes:
            fstab.save(mgr)
            changed = True

        return changed

    def _add_bash_commands(self, mgr: BaseManager) -> bool:
        """Add bash alias scripts rw and ro and give them nopasswd execution to 'pi'."""
        changed = False

        # Script contents
        ro_code = "#!/bin/bash\n\nmount -o remount,ro / 2>/dev/null\nmount -o remount,ro /boot/firmware 2>/dev/null\nmount -o remount,ro /boot 2>/dev/null\n"
        rw_code = "#!/bin/bash\n\nmount -o remount,rw / 2>/dev/null\nmount -o remount,rw /boot/firmware 2>/dev/null\nmount -o remount,rw /boot 2>/dev/null\n"

        if mgr.read_file('/usr/local/bin/ro', sudo=True) != ro_code:
            mgr.write_file('/usr/local/bin/ro', ro_code, sudo=True)
            mgr.run('chmod 700 /usr/local/bin/ro', sudo=True)
            changed = True

        if mgr.read_file('/usr/local/bin/rw', sudo=True) != rw_code:
            mgr.write_file('/usr/local/bin/rw', rw_code, sudo=True)
            mgr.run('chmod 700 /usr/local/bin/rw', sudo=True)
            changed = True

        # Sudoers edit
        sudoers_file = '/etc/sudoers.d/010_pi-nopasswd'
        if mgr.exists(sudoers_file):
            content = mgr.read_file(sudoers_file, sudo=True)
            if 'NOPASSWD: ALL' in content:
                mgr.set_config_line(sudoers_file, '#pi ALL=(ALL) NOPASSWD: ALL', match='pi ALL=(ALL) NOPASSWD: ALL', sudo=True)
                changed = True

            # The explicit replacements
            if not 'NOPASSWD: /sbin/halt' in content:
                mgr.append(sudoers_file, 'pi ALL=(ALL) NOPASSWD: /sbin/halt, /sbin/reboot, /usr/local/bin/rw, /usr/local/bin/ro', sudo=True)
                changed = True

        return changed

    def _setup_prompt(self, mgr: BaseManager) -> bool:
        """Setup custom bash prompt indicating readonly/readwrite state."""
        changed = False

        prompt_script = [
            '',
            '# custom prompt via python:',
            'prompt_command() { export PS1=$(~/.bash_prompt.py); }',
            'export PROMPT_COMMAND=prompt_command',
            '',
            '# save all cmds to history - http://northernmost.org/blog/flush-bash_history-after-each-command/',
            "export PROMPT_COMMAND='history -a; '$PROMPT_COMMAND",
            ''
        ]

        tgt_script = '/home/pi/.bash_prompt.py'
        src_script = Path(__file__).resolve().parent / 'resources' / 'bash_prompt.py'

        content_local = src_script.read_text(encoding='utf-8')
        content_remote = mgr.read_file(tgt_script, sudo=True)
        if content_local != content_remote:
            mgr.put(str(src_script), tgt_script, sudo=True)
            mgr.run(f'chmod +x {tgt_script}', sudo=True)
            mgr.run(f'chown pi:pi {tgt_script}', sudo=True)
            changed = True

        bashrc_file = '/home/pi/.bashrc'
        if mgr.exists(bashrc_file):
            bashrc_content = mgr.read_file(bashrc_file, sudo=True)
            if bashrc_content and 'prompt_command' not in bashrc_content:
                # Need to use an explicit join with newlines for append
                mgr.append(bashrc_file, '\n'.join(prompt_script), sudo=True)
                changed = True

        return changed

    def _install_first_boot_service(self, mgr: BaseManager) -> bool:
        changed = False

        # Write payload
        srcScript = Path(__file__).resolve().parents[1] / 'core' / 'resources' / 'enable_ro_fs.py'
        srcService = Path(__file__).resolve().parents[1] / 'core' / 'resources' / 'enable-ro-fs.service'

        tgtScript = '/usr/local/bin/enable_ro_fs.py'
        tgtService = '/etc/systemd/system/enable-ro-fs.service'

        contentScriptLocal = srcScript.read_text(encoding='utf-8')
        contentScriptTarget = mgr.read_file(tgtScript, sudo=True)
        if contentScriptLocal != contentScriptTarget:
            mgr.put(str(srcScript), tgtScript, sudo=True)
            mgr.run(f'chmod +x {tgtScript}', sudo=True)
            changed = True

        contentServiceLocal = srcService.read_text(encoding='utf-8')
        contentServiceTarget = mgr.read_file(tgtService, sudo=True)
        if contentServiceLocal != contentServiceTarget:
            mgr.put(str(srcService), tgtService, sudo=True)
            mgr.systemd_enable('enable-ro-fs.service', servicePath=tgtService, sudo=True)
            changed = True

        return changed

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        """Apply Readonly configuration.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Resolved config values.

        Returns:
            OperationLogRecord: Result record.
        """
        changed = False
        errors: list[str] = []

        print("Setting up Read-Only filesystem pre-requisites...")

        try:
            changed |= self._setup_packages(mgr)
            changed |= self._setup_symlinks(mgr)
            changed |= self._setup_fstab(mgr)
            changed |= self._add_bash_commands(mgr)
            changed |= self._setup_prompt(mgr)
            changed |= self._install_first_boot_service(mgr)
        except Exception as e:
            errors.append(f"Failed configuring read-only pre-requisites: {str(e)}")

        currentState = "System staged for RO switch on next boot." if not errors else "Read-Only configuration failed."

        if changed:
            print("...Done configuring read-only stages.")

        return OperationLogRecord(self.READONLY, changed, None, currentState, errors)

if __name__ == '__main__':
    run_pipeline = OperationPipeline([ReadonlyOperation()])
    run_pipeline.run_cli('Configure Read-Only Filesystem Stage')
