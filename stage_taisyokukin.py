"""Stage only a verified success; never stage stale or externally changed RSS."""
import hashlib
import json
from pathlib import Path
import subprocess

from scrape_taisyokukin_topics import OUTPUT_FILE, read_baseline, validate_candidate


def stage(directory=Path(".")):
    receipt = json.loads((directory / "taisyokukin-status.json").read_text())
    if receipt.get("schema") != 1 or receipt.get("complete") is not True:
        raise ValueError("invalid generation receipt")
    result = receipt["result"]
    if result.get("status") not in {"updated", "unchanged"} or result.get("file") != OUTPUT_FILE:
        raise ValueError("generation did not succeed")
    head = subprocess.check_output(["git", "show", "HEAD:" + OUTPUT_FILE], cwd=directory)
    current = (directory / OUTPUT_FILE).read_bytes()
    if hashlib.sha256(head).hexdigest() != result["baseline_sha256"]:
        raise ValueError("HEAD baseline changed")
    if hashlib.sha256(current).hexdigest() != result["sha256"]:
        raise ValueError("RSS changed after generation")
    _, old = read_baseline(head)
    validate_candidate(current, old)
    subprocess.run(["git", "add", "--", OUTPUT_FILE], cwd=directory, check=True)


if __name__ == "__main__":
    stage()
