#!/usr/bin/env python3
"""
Set locale and timezone on localhost, remote SSH, or ARM images/SD cards.

This module follows a two-phase architecture:
1. Configuration Phase: Gather all needed configs (YAML + prompts)
2. Execution Phase: Execute operations with configs (no prompts)

Usage:
    # Standalone - run as script (supports: all, locale, timezone)
    python region.py              # Interactive operation menu
    python region.py locale       # Only set locale
    python region.py timezone     # Only set timezone

    # Programmatic - single operation
    from lib.managers import create_manager
    from core.region import LocaleOperation

    with create_manager('ssh', hostName='192.168.1.100', userName='pi') as mgr:
        LocaleOperation().execute(mgr)

    # Orchestrated - multiple operations
    # See example_master_script.py for full operation-based pattern.

Configuration:
    Add to config.yaml:
    region:
        locale: en_US.UTF-8       # if missing, prompt when region operation runs
        timezone: US/Pacific      # if missing, prompt when region operation runs

References:
    https://serverfault.com/questions/362903/how-do-you-set-a-locale-non-interactively-on-debian-ubuntu
"""
import sys
import shlex
from pathlib import Path
from typing import Any

# pylint: disable=wrong-import-position
# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT
from lib.managers import BaseManager, CommandExecutionError
from lib.operations import OperationBase, OperationLogRecord, OperationPipeline
# pylint: enable=wrong-import-position

class TimezoneOperation(OperationBase):
    """Single operation class for timezone configuration."""
    # Source: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
    AVAILABLE_TIMEZONES = {
        'US/Alaska':  'America/Anchorage',   # -09:00  -08:00
        'US/Aleutian': 'America/Adak',       # -10:00  -09:00
        'US/Arizona': 'America/Phoenix',     # -07:00  -07:00
        'US/Central': 'America/Chicago',     # -06:00  -05:00
        'US/Eastern': 'America/New_York',    # -05:00  -04:00
        'US/East-Indiana': 'America/Indiana/Indianapolis',   # -05:00  -04:00
        'US/Hawaii': 'Pacific/Honolulu',      # -10:00  -10:00
        'US/Indiana-Starke': 'America/Indiana/Knox', # -06:00  -05:00
        'US/Michigan': 'America/Detroit',    # -05:00  -04:00
        'US/Mountain': 'America/Denver',     # -07:00  -06:00
        'US/Pacific': 'America/Los_Angeles', # -08:00  -07:00
    }

    TIMEZONE = 'timezone'

    REQUIRED_CONFIGS = {
            'type': 'str',
            'prompt': 'Choose timezone (press Enter to keep default: {default})',
    }

    def __init__(self) -> None:
        requiredConfigs: dict[str, dict[str, Any]] = {self.TIMEZONE: self.REQUIRED_CONFIGS}
        super().__init__(moduleName='region', name=self.TIMEZONE, requiredConfigs=requiredConfigs)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        """Prompt user to select a timezone if missing from config.

        Args:
            mgr (BaseManager): Active manager instance.
            configsToPrompt (dict[str, Any]): Unresolved keys to prompt.

        Returns:
            dict[str, Any]: Prompted values for unresolved keys.
        """
        currTz = self.get_current_timezone(mgr)
        choices = list(self.AVAILABLE_TIMEZONES.keys())
        choices.append('Other')
        sel = self.prompt_menu_value(self.REQUIRED_CONFIGS['prompt'], choices, currTz)
        if sel == len(choices) - 1:  # 'Other' selected
            tz = input('Enter custom timezone (e.g., "Europe/London"): ').strip()
        elif sel >= 0:
            selectedTz = choices[sel]
            tz = self.AVAILABLE_TIMEZONES[selectedTz]
        else:
            tz = None
        return {self.TIMEZONE: tz if tz else currTz}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        """Apply timezone operation using existing region implementation.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Resolved config values.

        Returns:
            OperationLogRecord: Timezone operation record.
        """
        newTimezone = str(configs[self.TIMEZONE])
        return TimezoneOperation.set_timezone(mgr, newTimezone)

    @staticmethod
    def get_current_timezone(mgr: BaseManager) -> str:
        """Get current timezone from target system.

        Args:
            mgr (BaseManager): Manager instance for command execution.

        Returns:
            str: Current timezone (for example, `America/Chicago`) or empty string.
        """
        isImage = mgr.is_os_image()

        if isImage:
            timezoneResult = mgr.run('cat /etc/timezone', sudo=True)
            if timezoneResult.returnCode == 0:
                return timezoneResult.stdout.strip()
            return ''
        else:
            # Use timedatectl for live systems
            result = mgr.run('timedatectl show --property=Timezone --value', sudo=False)
            if result.returnCode == 0:
                return result.stdout.strip()
            return ''

    @staticmethod
    def set_timezone(mgr: BaseManager, newTimezone: str) -> OperationLogRecord:
        """Set the system timezone.

        Args:
            mgr (BaseManager): Manager instance for command execution.
            newTimezone (str): The timezone to set (e.g., 'US/Pacific').

        Returns:
            OperationLogRecord: Timezone operation record.
        """
        previousTimezone = TimezoneOperation.get_current_timezone(mgr)
        currentTimezone = previousTimezone
        changed = False
        errors: list[str] = []

        isImage = mgr.is_os_image()
        isRaspi = mgr.is_raspi_os()

        # Validate timezone exists
        tzPath = f'/usr/share/zoneinfo/{newTimezone}'
        _, _, tzCheckCode = mgr.run(f'test -f {tzPath}', sudo=True)
        if tzCheckCode != 0:
            errMsg = f'Timezone {newTimezone} not found at {tzPath}'
            print(errMsg)
            errors.append(errMsg)
            return OperationLogRecord(TimezoneOperation.TIMEZONE, changed, previousTimezone, currentTimezone, errors)

        if previousTimezone == newTimezone:
            print(f"Timezone is already set to {newTimezone}, no change needed.")
            return OperationLogRecord(TimezoneOperation.TIMEZONE, changed, previousTimezone, currentTimezone, errors)

        try:
            if isImage:
                mgr.run_or_raise(f'echo {shlex.quote(newTimezone)} > /etc/timezone', sudo=True, errorPrefix='Failed to set /etc/timezone')
                mgr.run_or_raise(f'ln -snf {shlex.quote(tzPath)} /etc/localtime', sudo=True, errorPrefix='Failed to update /etc/localtime symlink')
            elif not isImage and isRaspi:
                mgr.run_or_raise(f'raspi-config nonint do_change_timezone {shlex.quote(newTimezone)}', sudo=True, errorPrefix='Failed to set Pi timezone')
            else:
                mgr.run_or_raise(f'timedatectl set-timezone {shlex.quote(newTimezone)}', sudo=True, errorPrefix='Failed to set Debian timezone')

        except CommandExecutionError as e:
            print(str(e))
            errors.append(str(e))

        currentTimezone = TimezoneOperation.get_current_timezone(mgr)
        if not errors and currentTimezone == newTimezone:
            changed = True
            print(f"Timezone changed from {previousTimezone} to {newTimezone}")
        elif not errors:
            errMsg = f'Timezone verification mismatch: expected {newTimezone}, got {currentTimezone}'
            print(errMsg)
            errors.append(errMsg)

        return OperationLogRecord(TimezoneOperation.TIMEZONE, changed, previousTimezone, currentTimezone, errors)




class LocaleOperation(OperationBase):
    # Available locales and timezones
    AVAILABLE_LOCALES = [
        'en_US.UTF-8',
        'en_GB.UTF-8',
        'en_CA.UTF-8',
        'en_AU.UTF-8',
    ]

    LOCALE = 'locale'
    REQUIRED_CONFIGS = {
        'type': 'str',
        'prompt': 'Enter locale (press Enter to keep default: {default})',
        # 'default': 'en_US.UTF-8',  # None = optional (will skip if empty)
    }

    def __init__(self) -> None:
        requiredConfigs: dict[str, dict[str, Any]] = {self.LOCALE: self.REQUIRED_CONFIGS}
        super().__init__(moduleName='region', name=self.LOCALE, requiredConfigs=requiredConfigs)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        """Prompt user to select a timezone if missing from config.

        Args:
            mgr (BaseManager): Active manager instance.
            configsToPrompt (dict[str, Any]): Unresolved keys to prompt.

        Returns:
            dict[str, Any]: Prompted values for unresolved keys.
        """
        currLocale = self.get_current_locale(mgr)
        sel = self.prompt_menu_value(self.REQUIRED_CONFIGS['prompt'], self.AVAILABLE_LOCALES, currLocale)
        if sel == len(self.AVAILABLE_LOCALES) - 1:  # 'Other' selected
            locale = input('Enter custom locale (e.g., "en_GB.UTF-8"): ').strip()
        elif sel >= 0:
            locale = self.AVAILABLE_LOCALES[sel]
        else:
            locale = None
        return {self.LOCALE: locale if locale else currLocale}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        """Apply locale operation using existing region implementation.

        Args:
            mgr (BaseManager): Active manager instance.
            configs (dict[str, Any]): Resolved config values.

        Returns:
            OperationLogRecord: Locale operation record.
        """
        newLocale = str(configs[self.LOCALE])
        return LocaleOperation.set_locale(mgr, newLocale)


    @staticmethod
    def get_current_locale(mgr: BaseManager) -> str:
        """Get current locale from target system using file-first source of truth.

        Additional info (multi-line): Reads persistent target config first and only
        falls back to runtime command output when config files are unavailable.

        Args:
            mgr (BaseManager): Manager instance for command execution.

        Returns:
            str: Current locale (for example, `en_GB.UTF-8`) or empty string.
        """
        isImage = mgr.is_os_image()

        if isImage:
            localeFileResult = mgr.run("grep '^LANG=' /etc/default/locale | cut -d= -f2", sudo=True)
            if localeFileResult.returnCode == 0 and localeFileResult.stdout.strip():
                return localeFileResult.stdout.strip().strip('"')

            localeConfResult = mgr.run("grep '^LANG=' /etc/locale.conf | cut -d= -f2", sudo=True)
            if localeConfResult.returnCode == 0 and localeConfResult.stdout.strip():
                return localeConfResult.stdout.strip().strip('"')

            return ''
        else:
            # Live evaluation
            result = mgr.run('localectl show --property=SystemLocale', sudo=False)
            if result.returnCode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith('LANG='):
                        return line.split('=', 1)[1]
            return ''

    @staticmethod
    def set_locale(mgr: BaseManager, newLocale: str) -> OperationLogRecord:
        """Set the system locale.

        Args:
            mgr (BaseManager): Manager instance for command execution.
            newLocale (str): The locale to set (e.g., 'en_US.UTF-8').

        Returns:
            OperationLogRecord: Locale operation record.
        """
        previousLocale = LocaleOperation.get_current_locale(mgr)
        currentLocale = previousLocale
        changed = False
        errors: list[str] = []

        isImage = mgr.is_os_image()
        isRaspi = mgr.is_raspi_os()

        if previousLocale == newLocale:
            print(f"Locale is already set to {newLocale}, no change needed.")
            return OperationLogRecord(LocaleOperation.LOCALE, changed, previousLocale, currentLocale, errors)

        localeLineResult = mgr.run(f"grep -E '^{newLocale}( |$)' /usr/share/i18n/SUPPORTED", sudo=True)
        localeLine = localeLineResult.stdout.strip()
        if localeLineResult.returnCode != 0 or not localeLine:
            errMsg = f'Locale {newLocale} not found in /usr/share/i18n/SUPPORTED'
            print(errMsg)
            errors.append(errMsg)
            return OperationLogRecord(LocaleOperation.LOCALE, changed, previousLocale, currentLocale, errors)

        newLang = localeLine.split()[0]
        try:
            if isImage:
                mgr.run_or_raise(
                    "if [ -L /etc/locale.gen ] && [ \"$(readlink /etc/locale.gen)\" = \"/usr/share/i18n/SUPPORTED\" ]; then rm -f /etc/locale.gen; fi",
                    sudo=True, errorPrefix='Failed to prepare /etc/locale.gen')
                mgr.run_or_raise(
                    f"printf '%s\\n' {shlex.quote(localeLine)} > /etc/locale.gen", sudo=True, errorPrefix='Failed to write /etc/locale.gen')
                mgr.run_or_raise(f'locale-gen {shlex.quote(newLang)}', sudo=True, errorPrefix='Failed to generate locale')
                mgr.run_or_raise('update-locale --no-checks LANG', sudo=True, errorPrefix='Failed to clear LANG')
                mgr.run_or_raise(f'update-locale --no-checks LANG={shlex.quote(newLang)}', sudo=True, errorPrefix='Failed to set LANG')
            elif not isImage and isRaspi:
                mgr.run_or_raise(f'raspi-config nonint do_change_locale {shlex.quote(newLang)}', sudo=True, errorPrefix='Failed to set Pi locale')
            else:
                mgr.run_or_raise(f'localectl set-locale LANG={shlex.quote(newLang)}', sudo=True, errorPrefix='Failed to set Debian locale')

        except CommandExecutionError as e:
            print(str(e))
            errors.append(str(e))

        currentLocale = LocaleOperation.get_current_locale(mgr)
        if not errors:
            if currentLocale and currentLocale != newLocale:
                errMsg = f'Locale verification mismatch: expected {newLocale}, got {currentLocale}'
                print(errMsg)
                errors.append(errMsg)
            else:
                changed = True
                currentLocale = currentLocale if currentLocale else newLocale
                print(f"Locale set to {newLocale}")

        return OperationLogRecord(LocaleOperation.LOCALE, changed, previousLocale, currentLocale, errors)

if __name__ == '__main__':
    pipeline = OperationPipeline([TimezoneOperation(), LocaleOperation()])
    pipeline.run_cli('Configure system timezone and locale')
