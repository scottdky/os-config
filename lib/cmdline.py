#!/usr/bin/env python

from lib.managers.base import BaseManager

"""
Cmdline - a parser for editing the /boot/cmdline.txt file

Usage: load the current cmdline.txt file. Add/delete/replace tokens and write back out
Example:
    contents = loadCmdlineFile(mgr) # makes a backup
    cmds = Cmdline(contents)
    cmds.add('logo.nologo')
    consoles = cmds.find('console')
    if consoles:
        cmds.remove(consoles[0])
    loglevel = cmds.findone('loglevel')
    if loglevel:
        cmds.replace(loglevel, 'loglevel=2')
    # now get the updated contents
    contents = cmds.contents()
    saveCmdlineFile(mgr, contents)
"""

class Cmdline:
    def __init__(self, contents: str):
        self.parts = contents.strip().split() if contents else []

    def inList(self, txt: str) -> bool:
        """Return true if txt is found in any of the tokens"""
        return any(txt in s for s in self.parts)

    def find(self, txt: str) -> list[str]:
        """Return list of tokens containing txt"""
        return [s for s in self.parts if txt in s]

    def findone(self, txt: str) -> str | None:
        """Return the first token containing txt, or None"""
        toks = self.find(txt)
        return toks[0] if toks else None

    def index(self, tok: str) -> int:
        """Return index of token. Returns -1 if not found."""
        try:
            return self.parts.index(tok)
        except ValueError:
            return -1

    def add(self, tok: str) -> bool:
        """Add token

        Returns True if the token was added, False if it was already present.
        """
        if not self.findone(tok):
            self.parts.append(tok)
            return True
        return False

    def remove(self, tok: str) -> bool:
        """Remove token

        Returns True if the token was removed, False if it was not found.
        """
        try:
            self.parts.remove(tok)
            return True
        except ValueError:
            return False

    def replace(self, tok: str, newtok: str) -> None:
        """Replace an existing token with a new token."""
        pos = self.index(tok)
        if pos >= 0:
            self.parts[pos] = newtok

    def contents(self) -> str:
        """Retrieve all the parts as a single string joined by spaces"""
        return ' '.join(self.parts)

def _get_cmdline_path(mgr: BaseManager) -> str:
    """Helper to detect if we should use /boot/firmware or /boot."""
    if mgr.exists('/boot/firmware/cmdline.txt'):
        return '/boot/firmware/cmdline.txt'
    return '/boot/cmdline.txt'

def loadCmdlineFile(mgr: BaseManager, backup: str | None = '.bck') -> str:
    """Return the contents of the cmdline.txt file, making a backup (if desired) in the process.
    To skip the backup, set backup=None
    """
    fname = _get_cmdline_path(mgr)
    
    if not mgr.exists(fname):
        return ""
        
    contents = mgr.read_file(fname, sudo=True)
    if backup:
        mgr.write_file(f"{fname}{backup}", contents, sudo=True)
        
    return contents

def saveCmdlineFile(mgr: BaseManager, contents: str) -> None:
    """Given the new contents of the cmdline.txt file, replace the existing file with it."""
    fname = _get_cmdline_path(mgr)
    mgr.write_file(fname, contents.strip(), sudo=True)
