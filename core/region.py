#CMD: region - Set locale and timezone

"""
Set locale and timezone on localhost, remote SSH, or ARM images/SD cards.

This module follows a two-phase architecture:
1. Configuration Phase: Gather all needed configs (YAML + prompts)
2. Execution Phase: Execute operations with configs (no prompts)

Usage:
    # Standalone - run as script (supports: all, locale, timezone)
    python region.py              # All operations (default)
    python region.py locale       # Only set locale
    python region.py timezone     # Only set timezone

    # Programmatic - single operation
    from lib.managers import create_manager
    from lib.config import load_and_validate_config
    from core import region

    configs = load_and_validate_config('region', region.REQUIRED_CONFIGS)
    with create_manager('ssh', hostName='192.168.1.100', userName='pi') as mgr:
        if configs.get('locale'):
            region.set_locale(mgr, configs['locale'])
        if configs.get('timezone'):
            region.set_timezone(mgr, configs['timezone'])

    # Orchestrated - multiple operations
    # See example_master_script.py for full pattern
    region_cfg = load_and_validate_config('region', region.REQUIRED_CONFIGS)
    hostname_cfg = load_and_validate_config('hostname', hostname.REQUIRED_CONFIGS)
    with create_manager('chroot', autoMount=True, imagePath='/dev/sdb') as mgr:
        if region_cfg.get('locale'):
            region.set_locale(mgr, region_cfg['locale'])
        if hostname_cfg.get('hostname'):
            hostname.set_host(mgr, hostname_cfg['hostname'])

Configuration:
    Add to config.yaml:
    region:
        locale: en_US.UTF-8       # if missing, prompt when region operation runs
        timezone: US/Pacific      # if missing, prompt when region operation runs

References:
    https://serverfault.com/questions/362903/how-do-you-set-a-locale-non-interactively-on-debian-ubuntu
"""
import os
import sys
import argparse

# pylint: disable=wrong-import-position
# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) # PROJECT_ROOT
from lib.managers import BaseManager, interactive_create_manager
from lib.config import load_and_validate_config
# pylint: enable=wrong-import-position

# Available locales and timezones
AVAILABLE_LOCALES = [
    'en_US.UTF-8',
    'en_GB.UTF-8',
    'en_CA.UTF-8',
    'en_AU.UTF-8',
]

# Source: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
AVAILABLE_TIMEZONES = [
    'US/Alaska',         # -09:00  -08:00  Link to America/Anchorage
    'US/Aleutian',       # -10:00  -09:00  Link to America/Adak
    'US/Arizona',        # -07:00  -07:00  Link to America/Phoenix
    'US/Central',        # -06:00  -05:00  Link to America/Chicago
    'US/Eastern',        # -05:00  -04:00  Link to America/New_York
    'US/East-Indiana',   # -05:00  -04:00  Link to America/Indiana/Indianapolis
    'US/Hawaii',         # -10:00  -10:00  Link to Pacific/Honolulu
    'US/Indiana-Starke', # -06:00  -05:00  Link to America/Indiana/Knox
    'US/Michigan',       # -05:00  -04:00  Link to America/Detroit
    'US/Mountain',       # -07:00  -06:00  Link to America/Denver
    'US/Pacific',        # -08:00  -07:00  Link to America/Los_Angeles
]

# Configuration schema for this module
REQUIRED_CONFIGS = {
    'locale': {
        'type': 'str',
        'prompt': 'Enter locale (press Enter to keep default: {default})',
        'default': 'en_US.UTF-8',  # None = optional (will skip if empty)
    },
    'timezone': {
        'type': 'str',
        'prompt': 'Enter timezone (press Enter to keep default: {default})',
        'default': 'US/Central',  # None = optional (will skip if empty)
    },
}


def set_locale(mgr: BaseManager, newLocale: str) -> bool:
    """Set the system locale.

    Args:
        mgr (BaseManager): Manager instance for command execution.
        newLocale (str): The locale to set (e.g., 'en_US.UTF-8').

    Returns:
        bool: True if locale was changed, False if already set or on error.
    """
    configPath = '/etc/locale.gen'

    # Validate locale exists in /usr/share/i18n/SUPPORTED
    validateCmd = f"grep -E '^{newLocale}( |$)' /usr/share/i18n/SUPPORTED"
    _, _, validateCode = mgr.run(validateCmd, sudo=True)
    if validateCode != 0:
        print(f"Locale {newLocale} not found in /usr/share/i18n/SUPPORTED")
        return False

    # Check if already set as primary locale
    currentLocale, _, _ = mgr.run("locale | grep LANG= | cut -d= -f2", sudo=True)
    currentLocale = currentLocale.strip().strip('"')

    if currentLocale == newLocale:
        print(f"Locale is already set to {newLocale}, no change needed.")
        return False

    # Read current locale.gen
    existingContent, _, _ = mgr.run(f'cat {configPath}', sudo=True)
    lines = existingContent.splitlines()

    # Comment out ALL existing uncommented locales (raspi_config approach)
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Skip already commented lines and empty lines
        if stripped.startswith('#') or not stripped:
            continue
        # Comment out any active locale lines
        if ' UTF-8' in line or '.UTF-8' in line:
            lines[i] = f'# {line}'

    # Uncomment the target locale
    modified = False
    for i, line in enumerate(lines):
        # Match pattern: "# en_US.UTF-8 UTF-8" or "# en_US.UTF-8"
        if line.strip().startswith(f'# {newLocale}'):
            lines[i] = line.replace('# ', '', 1)
            modified = True
            break

    if not modified:
        print(f"Locale {newLocale} not found in {configPath}")
        return False

    # Write modified content back
    newContent = '\n'.join(lines) + '\n'
    mgr.write_file(configPath, newContent, sudo=True)

    # Regenerate locales and update system (raspi_config approach)
    mgr.run('locale-gen', sudo=True)
    mgr.run(f'update-locale --no-checks LANG={newLocale}', sudo=True)
    mgr.run(f'update-locale --no-checks LC_ALL={newLocale}', sudo=True)
    mgr.run(f'update-locale --no-checks LANGUAGE={newLocale}', sudo=True)

    print(f"Locale set to {newLocale}")
    return True


def set_timezone(mgr: BaseManager, newTimezone: str) -> bool:
    """Set the system timezone.

    Args:
        mgr (BaseManager): Manager instance for command execution.
        newTimezone (str): The timezone to set (e.g., 'US/Pacific').

    Returns:
        bool: True if timezone was changed, False if already set or on error.
    """
    # Validate timezone exists
    tzPath = f'/usr/share/zoneinfo/{newTimezone}'
    _, _, tzCheckCode = mgr.run(f'test -f {tzPath}', sudo=True)
    if tzCheckCode != 0:
        print(f"Timezone {newTimezone} not found at {tzPath}")
        return False

    # Get current timezone
    currentTz, _, _ = mgr.run('cat /etc/timezone', sudo=True)
    currentTz = currentTz.strip()

    if currentTz == newTimezone:
        print(f"Timezone is already set to {newTimezone}, no change needed.")
        return False

    # Set new timezone (raspi_config approach)
    mgr.run(f"echo '{newTimezone}' > /etc/timezone", sudo=True)
    mgr.run('dpkg-reconfigure -f noninteractive tzdata', sudo=True)

    print(f"Timezone changed from {currentTz} to {newTimezone}")
    return True


if __name__ == '__main__':
    """Run interactively when executed as a script."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Configure system locale and timezone')
    parser.add_argument('operation', nargs='?', default='all',
                       choices=['locale', 'timezone', 'all'],
                       help='Operation to perform (default: all)')
    args = parser.parse_args()

    # Determine which configs to query based on operation
    if args.operation == 'all':
        configsToQuery = REQUIRED_CONFIGS
    else:
        # Only query the specific config needed
        configsToQuery = {args.operation: REQUIRED_CONFIGS[args.operation]}

    # Load configuration from YAML and prompt for missing values
    allConfigs = load_and_validate_config('region', configsToQuery)

    # Create and execute with manager
    manager = interactive_create_manager()
    if manager:
        with manager:
            changed = False

            # Execute based on operation
            if args.operation in ('locale', 'all') and allConfigs.get('locale'):
                changed |= set_locale(manager, allConfigs['locale'])

            if args.operation in ('timezone', 'all') and allConfigs.get('timezone'):
                changed |= set_timezone(manager, allConfigs['timezone'])

            if changed:
                print('...Done\n')
            else:
                print('No changes made.')
    else:
        print("No manager selected. Exiting.")


