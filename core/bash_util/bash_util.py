#!/usr/bin/env python3
"""
Pure Python implementation using paramiko instead of Fabric
"""
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT

from lib.managers import interactive_create_manager

# Updated bash.py implementation
BASE_PATH = Path(__file__).resolve().parent # PROJECT_ROOT/core

def reload_aliases(ssh):
    ssh.put(str(BASE_PATH / 'bash_aliases.txt'), '.bash_aliascore')

def reload_cdargs(ssh):
    ssh.put(str(BASE_PATH / 'cdarg_list.txt'), '.cdargs')

def install_aliases(ssh):
    s = ['', 'if [ -f ~/.bash_aliascore ]; then', '  . ~/.bash_aliascore', 'fi # endif .bash_aliascore']
    ssh.append('.bashrc', s)
    print('appended bash_aliascore to .bashrc')
    reload_aliases(ssh)

def mod_screen(ssh):
    """Add configs to screen startup to improve scrolling"""
    ssh.append('~/.screenrc', 'termcapinfo xterm* ti@:te@')
    ssh.append('~/.screenrc', 'scrollback 10000')

def install_cdargs(ssh):
    ssh.run('apt -y install cdargs', sudo=True)
    s = ['', '# start cdargs (cdb)', 'source /usr/share/doc/cdargs/examples/cdargs-bash.sh']
    ssh.append('.bashrc', s)
    reload_cdargs(ssh)

def install(ssh):
    install_aliases(ssh)
    mod_screen(ssh)
    install_cdargs(ssh)

def reload(ssh):
    reload_aliases(ssh)
    reload_cdargs(ssh)


if __name__ == "__main__":
    manager = interactive_create_manager()
    if manager:
        with manager as mgr:
            hostResult = mgr.run('hostname')
            print(f"Connected to: {hostResult.stdout.strip()}")

    # import argparse

    # parser = argparse.ArgumentParser(description='Bash setup script')
    # parser.add_argument('host', help='SSH host')
    # parser.add_argument('command', choices=['install', 'reload', 'install_aliases',
    #                                         'install_cdargs', 'reload_aliases', 'reload_cdargs'])
    # parser.add_argument('-u', '--user', help='SSH username')
    # parser.add_argument('-k', '--key', help='SSH key file path')
    # args = parser.parse_args()

    # # Execute command
    # with SSHManager(args.host, userName=args.user, keyFilename=args.key) as ssh:
    #     globals()[args.command](ssh)

    print("Done!")
