#!/usr/bin/env python

"""
Fstab - an fstab parser, loosely based on older fstab editors.

Usage: load a current fstab file into Fstab. Examine each parsed line and modify as desired. Retrieve the contents and write back out.

Fstab columns:   <device> <mount point>   <fs type>  <options>       <dump>  <fsck>
"""

from typing import Dict, List, Optional
from lib.managers.base import BaseManager

class FstabLine:
    def __init__(self, raw: str):
        self.raw: str = raw.strip()
        self.parts: Optional[Dict[str, str]] = None
        
        if not self.raw or self.raw.startswith('#'):
            return
            
        self.createParts(self.raw.split())
            
    def createParts(self, cols: List[str]) -> None:
        """Create a dictionary of the fstab colums"""
        if len(cols) < 6: # typically 6 cols in a proper fstab entry
            return
            
        self.parts = {
            'device': cols[0],
            'mount': cols[1],
            'fstype': cols[2],
            'options': cols[3],
            'dump': cols[4],
            'fsck': cols[5]
        }
    
    def content(self) -> str:
        """Get the newest version of the line"""
        if not self.parts: # a comment or blank line
            return self.raw
        
        return '\t'.join([
            self.parts['device'],
            self.parts['mount'],
            self.parts['fstype'],
            self.parts['options'],
            self.parts['dump'],
            self.parts['fsck']
        ])
        

class Fstab:
    """Edit an /etc/fstab file."""

    def __init__(self):
        self.lines: List[FstabLine] = []
        self.fstabPath: str = '/etc/fstab'

    def load(self, mgr: BaseManager, filepath: str = '/etc/fstab') -> None:
        """Read in the fstab file using the provided manager."""
        self.fstabPath = filepath
        self.lines = []
        
        if not mgr.exists(self.fstabPath):
            return
            
        content = mgr.read_file(self.fstabPath, sudo=True)
        if content:
            for line in content.splitlines():
                self.lines.append(FstabLine(line))

    def contents(self) -> str:
        """Get the current file contents with modifications. Return as a string"""
        buffer = []
        for line in self.lines:
            buffer.append(line.content())
        return '\n'.join(buffer) + '\n'

    def save(self, mgr: BaseManager) -> None:
        """Write the configured fstab contents back to the target partition."""
        mgr.write_file(self.fstabPath, self.contents(), sudo=True)
