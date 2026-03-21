#!/usr/bin/env python3

"""
Build a bash prompt without going blind!
Ref - https://stackoverflow.com/questions/2179493/adding-backslashes-without-escaping-python
"""

#from subprocess import call
import os

COLORS = {
    'Black': 30,
    'Blue': 34,
    'Cyan': 36,
    'Green': 32,
    'Purple': 35,
    'Red': 31,
    'White': 37,
    'Yellow': 33,
}

BACKGND_COLORS = {
    'Black': 40,
    'Blue': 44,
    'Cyan': 46,
    'Green': 42,
    'Purple': 45,
    'Red': 41,
    'White': 47,
    'Yellow': 43,
}

STYLES = {
    'Normal': 0,
    'Bold': 1,
    'Dim': 2,
    'Underline': 4,
    'Blink': 5,
    'Reverse': 7,
    'Hidden': 8
}

def makeColor(color, style=None):
    """Make the bash magical color string with optional styiing."""
    return '\\[\\033[{1}{0}m\\]'.format(color, '{};'.format(style) if style else '')


def main():
    OVERLAYSTR = 'oly'
    # NOTE: this code checks for overlay fs
    with open('/proc/cmdline') as f:
        content = f.readlines()
    fsmode = OVERLAYSTR if 'boot=overlay' in content[0] else None
    if not fsmode: # no overlay
        # NOTE: this line checks the mount point type - ro or rw
        fsmode = os.popen('findmnt / -no OPTIONS').read()[:2]

    path = os.getcwd()

    # \[\033[01;32m\]\u@\h${fs_mode:+($fs_mode)}\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$

    pr = ''

    # add python virtualenv prefix
    if 'VIRTUAL_ENV' in os.environ:
        venv = os.environ["VIRTUAL_ENV"]
        pre = venv.split('/')[-1]
        pr += f'({pre})'

    # show user@hostname
    pr += makeColor(COLORS['Green'])
    pr += '\\u@\\h'  # user@host

    # add read/write mode
    if fsmode in ['ro', OVERLAYSTR]:
        pr += makeColor(COLORS['Green'])
    else:
        pr += makeColor(COLORS['Red'], STYLES['Bold'])
    pr += '({})'.format(fsmode) # mode - rw or ro or OVERLAYSTR
    pr += makeColor('00')
    pr += ':'

    # add current working path/dir
    pr += makeColor(COLORS['Blue'])
    #pr += '\w'  # cwd path
    pr += path[:5]+'.../'+'/'.join(path.split('/')[-2:]) if len(path.split('/')) > 3 else path # last 2 dirs
    pr += makeColor('00')
    pr += '\$ '

    return pr

if __name__ == "__main__":
    print(main())
