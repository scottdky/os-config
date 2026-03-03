#!/usr/bin/env python
from builtins import object
import os

from fabric.api import *
from fabric.contrib.files import *

"""
Cmdline - a parser for editing the /boot/cmdline.txt file

Usage: load the current cmdline.txt file. Add/delete/replace tokens and write back out

Example:
    contents = loadCmdlineFile(rootpath) # makes a backup
    cmds = Cmdline(contents)
    cmds.add('logo.nologo')
    consoles = cmds.find('console')
    if consoles:
        cmds.remove(consoles[0])
    loglevel = cmds.findone('loglevel')
    cmds.replace(loglevel, 'loglevel=2')
    # now get the updated contents
    contents = cmds.contents()
    saveCmdlineFile(rootpath, contents)
"""


class Cmdline(object):
    def __init__(self, contents):
        #self.contents = contents.strip()
        self.parts = contents.strip().split()

    def inList(self, txt):
        """Return true if txt is found in any of the tokens"""
        return any(txt in s for s in self.parts)

    def find(self, txt):
        """Return list of tokens containing txt"""
        return [s for s in self.parts if txt in s]

    def findone(self, txt):
        toks = self.find(txt)
        return toks[0] if toks else None

    def index(self, tok):
        """Return index of token. Returns -1 if not found."""
        return self.parts.index(tok) if tok in self.parts else -1

    def add(self, tok):
        """Add token

        Returns True if the token was added, False if it was already present.
        """
        if not self.findone(tok):
            self.parts.append(tok)
            return True
        else:
            return False

    def remove(self, tok: str) -> bool:
        """Remove token

        Returns True if the token was removed, False if it was not found.
        """
        try:
            self.parts.remove(tok)
            return True
        except:
            return False

    def replace(self, tok, newtok):
        pos = self.index(tok)
        if pos >= 0:
            self.parts[pos] = newtok

    def contents(self):
        """Retrieve all the parts as a string"""
        return ' '.join(self.parts)


def loadCmdlineFile(rootpath, backup='.bck'):
    """Return the contents of the /boot/cmdline.txt file, making a backup (if desired) in the process.
    To skip the backup, set backup=None"""
    fname = '{}/boot/cmdline.txt'.format(rootpath)
    if backup:
        sudo('cp {} {}'.format(fname, fname + backup))  # make a backup
    if env.host_string == 'localhost': # file is mounted locally
        with open(fname, 'r') as f: contents = f.read()
    else:
        localfname = '/tmp/cmdline.txt'
        get(remote_path=fname, local_path=localfname) # fabric func - copies remote file
        with open(localfname, 'r') as f: contents = f.read()
    return contents

def saveCmdlineFile(rootpath, contents):
    """Given the new contents of the /boot/cmdline.txt file, replace the existing file with it."""
    fname = '{}/boot/cmdline.txt'.format(rootpath)
    if env.host_string == 'localhost': # file is mounted locally
        run("echo '{}' | sudo tee {}".format(contents, fname))  # completely rewrite the file
    else:
        localfname = '/tmp/cmdline.txt'
        run("echo '{}' | sudo tee {}".format(contents, localfname))  # copy out to a file
        put(local_path=localfname, remote_path=fname, use_sudo=True)


