#!/usr/bin/env python3
"""Example master script showing how to orchestrate multiple operations.

This demonstrates the two-phase config architecture:
- Phase 1: Gather ALL configurations upfront via operation classes
- Phase 2: Execute ALL operations (no prompts, pure execution)
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.managers import interactive_create_manager
from core.hostname import HostnameOperation, PasswordOperation, UsernameOperation
from core.region import LocaleOperation, TimezoneOperation


def run_full_setup():
    """Orchestrate multiple setup operations with config gathered upfront."""

    print("=" * 60)
    print("MULTI-OPERATION SETUP")
    print("=" * 60)

    # Phase 1: Gather ALL configs upfront
    print("\n=== CONFIGURATION PHASE ===")
    print("Please provide all configuration values upfront.\n")

    # Create manager
    manager = interactive_create_manager()
    if not manager:
        print("No manager selected. Exiting.")
        return

    hostnameOp = HostnameOperation()
    usernameOp = UsernameOperation()
    #passwordOp = PasswordOperation()
    timzoneOp = TimezoneOperation()

    with manager:
        print("--- Hostname Configuration ---")
        hostnameConfig = hostnameOp.gather_config(manager)
        usernameConfig = usernameOp.gather_config(manager)
        #passwordConfig = passwordOp.gather_config(manager)
        timezoneConfig = timzoneOp.gather_config(manager)

        # Future modules would gather configs here:
        # print("\n--- Network Configuration ---")
        # networkConfig = NetworkOperation().gather_config(manager)

        # Phase 2: Execute ALL operations (no prompts)
        print("\n" + "=" * 60)
        print("=== EXECUTION PHASE ===")
        print("=" * 60 + "\n")

        print("\n--- Executing Hostname Setup ---")
        hostnameRecord = hostnameOp.apply(manager, hostnameConfig)
        usernameRecord = usernameOp.apply(manager, usernameConfig)
        #passwordRecord = passwordOp.apply(manager, passwordConfig)
        timezoneRecord = timzoneOp.apply(manager, timezoneConfig)
        records = [hostnameRecord, usernameRecord, timezoneRecord]  # Exclude passwordRecord

        changed = any(record.changed for record in records)
        errors = [err for record in records for err in record.errors]

        if changed:
            print("The following changes were made:")
            for record in records:
                if record.changed:
                    print(f"- {record.operationName}: {record.summary()}")
            print("These operations did not result in any changes:")
            for record in records:
                if not record.changed:
                    print(f"- {record.operationName}: {record.summary()}")
        else:
            print("No changes made")

        if errors:
            print('Encountered errors during hostname setup:')
            for record in records:
                if record.errors:
                    for error in record.errors:
                        print(f'- {record.operationName}: {error}')

        # Future modules would execute here:
        # print("\n--- Executing Network Setup ---")
        # if network_cfg.get('ssid'):
        #     network.configure_wifi(manager, network_cfg)
        #
        # print("\n--- Executing Serial Port Setup ---")
        # if serial_cfg.get('enable_uart'):
        #     serialport.configure(manager, serial_cfg)

    print("\n" + "=" * 60)
    print("ALL OPERATIONS COMPLETE")
    print("=" * 60)


if __name__ == '__main__':
    run_full_setup()
