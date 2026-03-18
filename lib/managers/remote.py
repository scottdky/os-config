"""Remote SSH manager implementation."""

import os

import paramiko

from .base import BaseManager, CommandResult


class SSHManager(BaseManager):
    """Execute operations on remote host via SSH"""

    def __init__(self, hostName: str, userName: str | None = None,
                 keyFilename: str | None = None, password: str | None = None,
                 allowInteractiveSudo: bool = True) -> None:
        super().__init__(allowInteractiveSudo=allowInteractiveSudo)
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        self.connect_kwargs = {'hostname': hostName}
        if userName:
            self.connect_kwargs['username'] = userName
        if keyFilename:
            self.connect_kwargs['key_filename'] = keyFilename
        if password:
            self.connect_kwargs['password'] = password

        self.sftp = None

    def __enter__(self) -> "SSHManager":
        self.client.connect(**self.connect_kwargs)
        self.sftp = self.client.open_sftp()
        return self

    def run(self, command: str, sudo: bool = False) -> CommandResult:
        """Execute a command on remote host"""
        if sudo:
            command = f'sudo -S {command}'

        _, stdout, stderr = self.client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()

        output = stdout.read().decode()
        error = stderr.read().decode()

        if exit_status != 0:
            print(f"Error: {error}")
        return CommandResult(output, error, exit_status)

    def exists(self, remotePath: str) -> bool:
        """Check if remote file/directory exists"""
        try:
            self.sftp.stat(remotePath)
            return True
        except FileNotFoundError:
            return False

    def put(self, localPath: str, remotePath: str, sudo: bool = False) -> None:
        """Upload file to remote host"""
        if sudo:
            tempPath = f'/tmp/{os.path.basename(remotePath)}'
            self.sftp.put(localPath, tempPath)
            self.run(f'mv {tempPath} {remotePath}', sudo=True)
        else:
            self.sftp.put(localPath, remotePath)
        print(f"Uploaded {localPath} -> {remotePath}")

    def get(self, remotePath: str, localPath: str, sudo: bool = False) -> None:
        """Download file from remote host"""
        if sudo:
            tempPath = f'/tmp/{os.path.basename(remotePath)}'
            self.run(f'cp {remotePath} {tempPath}', sudo=True)
            self.run(f'chmod 644 {tempPath}', sudo=True)
            self.sftp.get(tempPath, localPath)
            self.run(f'rm {tempPath}', sudo=False)
        else:
            self.sftp.get(remotePath, localPath)
        print(f"Downloaded {remotePath} -> {localPath}")

    def close(self) -> None:
        """Close SSH connection"""
        if self.sftp:
            self.sftp.close()
        self.client.close()


__all__ = ['SSHManager']
