import hashlib, platform
from pathlib import Path
from importlib import metadata, resources
from zoneinfo import TZPATH


def runtime_environment():
    content = None
    for path in TZPATH:
        file = Path(path) / "Europe" / "Rome"
        if file.is_file():
            content = file.read_bytes()
            break
    if content is None:
        content = (
            resources.files("tzdata")
            .joinpath("zoneinfo", "Europe", "Rome")
            .read_bytes()
        )
    return {
        "application": "0.7.0",
        "python": platform.python_version(),
        "ortools": metadata.version("ortools"),
        "timezone": "Europe/Rome",
        "tzdb_file_sha256": hashlib.sha256(content).hexdigest(),
    }
