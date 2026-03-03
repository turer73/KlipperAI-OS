"""Subprocess wrapper."""
from __future__ import annotations

import subprocess

from .logger import get_logger

logger = get_logger()


def run_cmd(
    cmd: list[str],
    timeout: int = 600,
    check: bool = False,
) -> tuple[bool, str]:
    """Komut calistir, (basari, cikti) dondur."""
    logger.debug("CMD: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
        if not success:
            logger.debug("CMD FAIL (rc=%d): %s", result.returncode, output[:200])
        return success, output
    except subprocess.TimeoutExpired:
        logger.error("CMD TIMEOUT: %s", " ".join(cmd))
        return False, "timeout"
    except FileNotFoundError:
        logger.error("CMD NOT FOUND: %s", cmd[0])
        return False, "not found"
