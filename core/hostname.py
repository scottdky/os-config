#CMD: hostname setup Name & Pass

"""
Set hostname, username, and password on localhost, remote SSH, or ARM images/SD cards.

This module follows a two-phase architecture:
1. Configuration Phase: Gather all needed configs (YAML + prompts)
2. Execution Phase: Execute operations with configs (no prompts)

Usage:
    # Standalone - run as script (supports: all, hostname, username, password)
    python hostname.py              # Interactive operation menu
    python hostname.py hostname     # Only set hostname
    python hostname.py password     # Only set password

    # Programmatic - single operation
    from lib.managers import create_manager
    from lib.config import resolve_config_values, validate_and_prompt
    from core import hostname

    configs, missingKeys = resolve_config_values('hostname', hostname.REQUIRED_CONFIGS)
    with create_manager('ssh', hostName='192.168.1.100', userName='pi') as mgr:
        defaults = {
            'hostname': hostname.get_current_hostname(mgr),
            'username': hostname.get_current_user(mgr),
        }
        configs = validate_and_prompt(
            hostname.REQUIRED_CONFIGS,
            configs,
            keysToPrompt=missingKeys,
            defaultOverrides=defaults,
        )
        if configs.get('hostname'):
            hostname.set_host(mgr, configs['hostname'])
        if configs.get('password'):
            hostname.set_pass(mgr, 'pi', configs['password'])

    # Orchestrated - multiple operations
    # See example_master_script.py for full pattern
    hostname_cfg, missingKeys = resolve_config_values('hostname', hostname.REQUIRED_CONFIGS)
    network_cfg = load_and_validate_config('network', network.REQUIRED_CONFIGS)
    with create_manager('chroot', autoMount=True, imagePath='/dev/sdb') as mgr:
        hostname_cfg = validate_and_prompt(
            hostname.REQUIRED_CONFIGS,
            hostname_cfg,
            keysToPrompt=missingKeys,
            defaultOverrides={'hostname': hostname.get_current_hostname(mgr)},
        )
        if hostname_cfg.get('hostname'):
            hostname.set_host(mgr, hostname_cfg['hostname'])
        if network_cfg.get('ssid'):
            network.configure_wifi(mgr, network_cfg)

Configuration:
    Add to config.yaml:
    hostname:
        hostname: newhost      # if missing, prompt after manager is ready
        username: newuser      # if missing, prompt after manager is ready
        password: s3cr3t       # if missing, secure prompt is required
"""
import os
import sys
import argparse

# pylint: disable=wrong-import-position
# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) # PROJECT_ROOT
from lib.managers import BaseManager, interactive_create_manager, get_user_selection
from lib.config import resolve_config_values, validate_and_prompt
# pylint: enable=wrong-import-position


# Configuration schema for this module
REQUIRED_CONFIGS = {
    'hostname': {
        'type': 'str',
        'prompt': 'Enter new hostname (press Enter to keep default: {default})',
    },
    'username': {
        'type': 'str',
        'prompt': 'Enter new username (press Enter to keep default: {default})',
    },
    'password': {
        'type': 'str',
        'prompt': 'Enter password for user',
        'secure': True,
    },
}


def set_host(mgr: BaseManager, newName: str) -> bool:
    """Set the hostname on the target system.

    Args:
        mgr (BaseManager): Manager instance for command execution.
        newName (str): The new hostname to set.

    Returns:
        bool: True if hostname was changed, False if already set.
    """
    hostNameResult = mgr.run('cat /etc/hostname')
    oldName = hostNameResult.stdout.strip()

    if oldName == newName:
        print(f"Hostname is already {newName}, no change needed.")
        return False

    mgr.sed('/etc/hostname', oldName, newName, sudo=True)
    mgr.sed('/etc/hosts', oldName, newName, sudo=True)
    print(f"Changed hostname from {oldName} to {newName}")
    return True


def set_pass(mgr: BaseManager, userName: str, password: str) -> bool:
    """Set password for a user on the target system.

    Args:
        mgr (BaseManager): Manager instance for command execution.
        userName (str): Username to change password for.
        password (str): The password to set (plaintext).

    Returns:
        bool: True if password was changed, False otherwise.
    """
    # Use chpasswd command to set password
    # This works for all manager types (local, ssh, chroot)
    # See: https://unix.stackexchange.com/questions/272414/bash-script-to-change-password-in-chroot
    _, stderr, code = mgr.run(f"echo '{userName}:{password}' | chpasswd", sudo=True)

    if code == 0:
        print(f"Password changed for user {userName}")
        return True
    else:
        print(f"Error changing password: {stderr}")
        return False


def set_user(mgr: BaseManager, oldUser: str, newUser: str) -> bool:
    """Rename a user account on the target system.

    Additional info (multi-line): changes the username and home directory.
    Note that the user should not be logged in when this is run.

    Args:
        mgr (BaseManager): Manager instance for command execution.
        oldUser (str): Current username to rename.
        newUser (str): New username.

    Returns:
        bool: True if user was renamed successfully, False otherwise.

    Reference:
        https://raspberrypi.stackexchange.com/questions/12827/change-default-username
    """
    _, stderr, code = mgr.run(f'usermod -m -l {newUser} -d /home/{newUser} {oldUser}', sudo=True)

    if code == 0:
        print(f"Renamed user from {oldUser} to {newUser}")
        return True
    else:
        print(f"Error renaming user: {stderr}")
        return False


def get_current_user(mgr: BaseManager) -> str:
    """Get the first non-root user from the target system.

    Args:
        mgr (BaseManager): Manager instance for command execution.

    Returns:
        str: Username (defaults to 'pi' if unable to determine).
    """
    userListResult = mgr.run("getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 {print $1}'", sudo=False)
    if userListResult.returnCode == 0 and userListResult.stdout.strip():
        return userListResult.stdout.strip().split('\n')[0]
    return 'pi'  # Default fallback


def get_current_hostname(mgr: BaseManager) -> str:
    """Get current hostname from target system.

    Args:
        mgr (BaseManager): Manager instance for command execution.

    Returns:
        str: Current hostname, or empty string if unavailable.
    """
    hostNameResult = mgr.run('cat /etc/hostname', sudo=False)
    if hostNameResult.returnCode == 0:
        return hostNameResult.stdout.strip()
    return ''


if __name__ == '__main__':
    # Run interactively when executed as a script.
    CHOICES = ['hostname', 'username', 'password', 'all']
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Configure hostname, username, and password')
    parser.add_argument('operation', nargs='?', choices=CHOICES,
                       help='Operation to perform (if omitted, interactive menu is shown)')
    args = parser.parse_args()

    operation = args.operation
    if operation is None:
        index = get_user_selection(CHOICES, "Select operation to perform:")
        if index is None:
            print('No operation selected. Exiting.')
            sys.exit(0)
        operation = CHOICES[index]

    # Determine which configs to query based on operation
    if operation == 'all':
        configsToQuery = REQUIRED_CONFIGS
    else:
        # Only query the specific config needed
        configsToQuery = {operation: REQUIRED_CONFIGS[operation]}

    # Pre-mount resolution: determine unresolved required keys without prompting
    allConfigs, missingKeys = resolve_config_values('hostname', configsToQuery)

    # Create and execute with manager
    manager = interactive_create_manager()
    if manager:
        with manager:
            # Post-mount prompting with target-derived defaults
            defaultOverrides = {}
            if 'hostname' in missingKeys:
                defaultOverrides['hostname'] = get_current_hostname(manager)
            if 'username' in missingKeys:
                defaultOverrides['username'] = get_current_user(manager)

            allConfigs = validate_and_prompt(
                configsToQuery,
                allConfigs,
                keysToPrompt=missingKeys,
                defaultOverrides=defaultOverrides,
            )

            changed = False

            # Execute based on operation
            if operation in ('hostname', 'all') and allConfigs.get('hostname'):
                changed |= set_host(manager, allConfigs['hostname'])

            if operation in ('username', 'all') and allConfigs.get('username'):
                origUser = get_current_user(manager)
                changed |= set_user(manager, origUser, allConfigs['username'])

            if operation in ('password', 'all') and allConfigs.get('password'):
                targetUserName = allConfigs.get('username') or get_current_user(manager)
                changed |= set_pass(manager, targetUserName, allConfigs['password'])

            if changed:
                print('...Done\n')
            else:
                print('No changes made.')
    else:
        print("No manager selected. Exiting.")
