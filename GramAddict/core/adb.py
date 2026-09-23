"""Thin boundary for adb calls: argument lists, never a host shell."""
import shlex
import subprocess
from typing import Optional


class AdbError(Exception):
    pass


def adb(device_id: Optional[str], *args, check: bool = False):
    cmd = ["adb"] + (["-s", device_id] if device_id else []) + [str(a) for a in args]
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8"
    )
    if check and result.returncode != 0:
        # args may hold secrets (device password), so keep them out of the message
        raise AdbError(f"adb exited with {result.returncode}: {result.stderr.strip()}")
    return result


def device_quote(value) -> str:
    """Quote a value for the phone's shell: `adb shell` joins its args and runs them there."""
    return shlex.quote(str(value))
