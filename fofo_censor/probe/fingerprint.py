"""Content fingerprinting (design §6.1 step 2).

A fingerprint lets a filter-map sidecar be matched back to its source later (and,
in Phase 2, to a stream being played). For the MVP this is a cheap, stable hash
of structural metadata plus sampled byte regions of the file — not a perceptual
hash. A perceptual/frame-hash upgrade can replace this without changing callers.
"""

from __future__ import annotations

import hashlib
import os


def fingerprint_file(path: str, *, sample_bytes: int = 1 << 20) -> str:
    """Return a hex fingerprint from file size + head/middle/tail byte samples."""
    size = os.path.getsize(path)
    h = hashlib.sha256()
    h.update(str(size).encode())

    with open(path, "rb") as fh:
        # Head
        h.update(fh.read(sample_bytes))
        # Middle
        if size > sample_bytes * 2:
            fh.seek(size // 2)
            h.update(fh.read(sample_bytes))
        # Tail
        if size > sample_bytes:
            fh.seek(max(0, size - sample_bytes))
            h.update(fh.read(sample_bytes))

    return h.hexdigest()
