#!/usr/bin/env python3
"""Manage injection of custom configuration files into the system.

Allows providing raw configuration files dynamically from config.yaml directly
into the image. Bypasses standard CLI required_configs logic.

Usage: Configure 'custom_files' root array in config.yaml.
"""
import sys
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).resolve().parents[1])) # PROJECT_ROOT

from lib.managers import BaseManager
from lib.operations import OperationBase, OperationLogRecord, OperationPipeline


class CustomFilesOperation(OperationBase):
    FILES = 'files'
    REQUIRED_CONFIGS = {}

    def __init__(self) -> None:
        super().__init__(moduleName='custom_files', name=self.FILES, requiredConfigs=self.REQUIRED_CONFIGS)

    def prompt_missing_values(self, mgr: BaseManager, configsToPrompt: dict[str, Any], allConfigs: dict[str, Any]) -> dict[str, Any]:
        return {}

    def apply(self, mgr: BaseManager, configs: dict[str, Any]) -> OperationLogRecord:
        changed = False
        errors: list[str] = []
        files = configs.get(self.FILES, [])

        if not files:
            return OperationLogRecord(self.FILES, False, None, "No custom files configured", [])

        if not isinstance(files, list):
            errors.append(f"Invalid custom files format. Expected list, got {type(files).__name__}")
            return OperationLogRecord(self.FILES, False, None, "Failed", errors)

        for cfg in files:
            target = cfg.get('target')
            content = cfg.get('content')
            local_source = cfg.get('local_source')
            executable = cfg.get('executable', False)
            enable_service = cfg.get('enable_service', False)

            if not target:
                errors.append("Skipping file entry missing 'target' attribute.")
                continue

            # Route 1: Put Local File
            if hasattr(cfg, 'get') and local_source:
                try:
                    mgr.put(local_source, target, sudo=True)
                    changed = True
                except Exception as e:
                    errors.append(f"Could not copy {local_source} to {target}: {e}")

            # Route 2: Write direct content string block
            elif hasattr(cfg, 'get') and content is not None:
                orig_content = mgr.read_file(target, sudo=True) if mgr.exists(target) else None
                if orig_content != content:
                    mgr.write_file(target, content, sudo=True)
                    changed = True

            else:
                errors.append(f"Target '{target}' specified neither 'content' nor 'local_source'.")

            # Post-injection steps
            if executable:
                mgr.run(f"chmod +x {target}", sudo=True)
                changed = True

            if enable_service and target.endswith('.service'):
                service_name = Path(target).name
                mgr.systemd_enable(service_name, servicePath=target, sudo=True)
                changed = True

        state = "Processed custom files list."
        if errors:
            state = f"Completed with {len(errors)} warnings."

        return OperationLogRecord(self.FILES, changed, None, state, errors)


if __name__ == '__main__':
    pipeline = OperationPipeline([CustomFilesOperation()])
    pipeline.run_cli('Inject custom configuration files')
