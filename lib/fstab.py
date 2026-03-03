#!/usr/bin/env python

"""
Fstab - an fstab parser, based loosely on http://python-fstab.sourcearchive.com/documentation/1.4-0ubuntu1/fstab_8py-source.html

Usage: load a current fstab file into Fstab. Examine each parsed line and modify as desired. Retrieve the contents and write back out.

Fstab columns:   <device> <mount point>   <fs type>  <options>       <dump>  <fsck>
"""

from builtins import object
class FstabLine(object):
    def __init__(self, raw):
        self.raw = raw.strip()
        #print 'raw line {}'.format(self.raw)
        if not self.raw or self.raw[0] == '#':
            self.parts = None
        else:
            self.createParts(raw.split())
            
    def createParts(self, cols):
        """Create a dictionary of the fstab colums"""
        if len(cols) != 6: # 6 is the number of cols in a proper fstab entry
            return None
        parts = {}
        parts['device'] = cols[0]
        parts['mount'] = cols[1]
        parts['fstype'] = cols[2]
        parts['options'] = cols[3]
        parts['dump'] = cols[4]
        parts['fsck'] = cols[5]
        self.parts = parts
    
    def content(self):
        """Get the newest version of the line"""
        if not self.parts: # nothing has changed
            return self.raw
        
        parts = []
        parts.append(self.parts['device'])
        parts.append(self.parts['mount'])
        parts.append(self.parts['fstype'])
        parts.append(self.parts['options'])
        parts.append(self.parts['dump'])
        parts.append(self.parts['fsck'])
        return '\t'.join(parts)
        

class Fstab(object):

    """Edit an /etc/fstab file."""

    def __init__(self):
        self.lines = []
        self.fstabPath = None

    def load(self, filepath):
        """Read in a new file.
        Par filename is the full path to the fstab file
        """
        self.fstabPath = filepath
        lines = []
        with open(filepath, "r") as f:
            for line in f:
                lines.append(FstabLine(line))
        self.lines = lines

    def contents(self):
        """Get the current file contents with modifications. Return as a string"""
        buffer = ''
        for line in self.lines:
            buffer += line.content() + '\n'
        return buffer
    
