"""Local host manager implementation."""

import os
import shlex
import shutil

from .base import BaseManager, CommandResult


class LocalManager(BaseManager):
    """Execute operations on localhost"""

    def __init__(self, allowInteractiveSudo: bool = True) -> None:
        super().__init__(allowInteractiveSudo=allowInteractiveSudo)

    def run(self, command: str, sudo: bool = False) -> CommandResult:
        """Execute a command on localhost"""
        commandResult = self.run_local(command, sudo=sudo)
        if commandResult.returnCode != 0:
            print(f"Error: {commandResult.stderr}")
        return commandResult

    def exists(self, remotePath: str) -> bool:
        """Check if local file/directory exists"""
        return os.path.exists(remotePath)

    def put(self, localPath: str, remotePath: str, sudo: bool = False) -> None:
        """Copy file locally"""
        self._put_local(localPath, remotePath, sudo=sudo)

    def get(self, remotePath: str, localPath: str, sudo: bool = False) -> None:
        """Copy file from local system to another local path"""
        if sudo:
            copyResult = self.run_local(
                f'cp {shlex.quote(remotePath)} {shlex.quote(localPath)}',
                sudo=True
            )
            if copyResult.returnCode != 0:
                raise IOError(f"Failed to copy {remotePath} to {localPath}: {copyResult.stderr}")
        else:
            shutil.copy(remotePath, localPath)
        print(f"Downloaded {remotePath} -> {localPath}")


__all__ = ['LocalManager']
