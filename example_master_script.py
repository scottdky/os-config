#!/usr/bin/env python3
"""Example master script showing how to orchestrate multiple operations.

This demonstrates the two-phase config architecture:
- Phase 1: Gather ALL configurations upfront (all user prompts happen here)
- Phase 2: Execute ALL operations (no prompts, pure execution)
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.managers import interactive_create_manager
from lib.config import load_and_validate_config
from core import hostname


def run_full_setup():
    """Orchestrate multiple setup operations with config gathered upfront."""

    print("=" * 60)
    print("MULTI-OPERATION SETUP")
    print("=" * 60)

    # Phase 1: Gather ALL configs upfront
    print("\n=== CONFIGURATION PHASE ===")
    print("Please provide all configuration values upfront.\n")

    # Gather hostname module configs
    print("--- Hostname Configuration ---")
    hostname_cfg = load_and_validate_config('hostname', hostname.REQUIRED_CONFIGS)

    # Future modules would gather configs here:
    # print("\n--- Network Configuration ---")
    # network_cfg = load_and_validate_config('network', network.REQUIRED_CONFIGS)
    #
    # print("\n--- Serial Port Configuration ---")
    # serial_cfg = load_and_validate_config('serialport', serialport.REQUIRED_CONFIGS)

    # Phase 2: Execute ALL operations (no prompts)
    print("\n" + "=" * 60)
    print("=== EXECUTION PHASE ===")
    print("=" * 60 + "\n")

    # Create manager
    manager = interactive_create_manager()
    if not manager:
        print("No manager selected. Exiting.")
        return

    # Execute all operations
    with manager:
        print("\n--- Executing Hostname Setup ---")
        changed = False

        if hostname_cfg.get('hostname'):
            changed |= hostname.set_host(manager, hostname_cfg['hostname'])

        if hostname_cfg.get('username'):
            origUser = hostname.get_current_user(manager)
            changed |= hostname.set_user(manager, origUser, hostname_cfg['username'])

        if hostname_cfg.get('password'):
            userName = hostname_cfg.get('username') or hostname.get_current_user(manager)
            changed |= hostname.set_pass(manager, userName, hostname_cfg['password'])

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
