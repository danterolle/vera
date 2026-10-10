"""Bundled, versioned resources used by deterministic VERA workflows."""

from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any


def resource(relative_path: str) -> Any:
    target = files(__package__)
    for part in PurePosixPath(relative_path).parts:
        target = target.joinpath(part)
    return target
