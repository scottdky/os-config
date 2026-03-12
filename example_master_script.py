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
    passwordOp = PasswordOperation()

    with manager:
        print("--- Hostname Configuration ---")
        hostnameConfig = hostnameOp.gather_config(manager)
        usernameConfig = usernameOp.gather_config(manager)
        passwordConfig = passwordOp.gather_config(manager)

        # Future modules would gather configs here:
        # print("\n--- Network Configuration ---")
        # networkConfig = NetworkOperation().gather_config(manager)

        # Phase 2: Execute ALL operations (no prompts)
        print("\n" + "=" * 60)
        print("=== EXECUTION PHASE ===")
        print("=" * 60 + "\n")

        print("\n--- Executing Hostname Setup ---")
        changed = False

        changed |= hostnameOp.apply(manager, hostnameConfig)
        changed |= usernameOp.apply(manager, usernameConfig)
        changed |= passwordOp.apply(manager, passwordConfig)

        if changed:
            print("Hostname configuration complete")
        else:
            print("No hostname changes made")

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
