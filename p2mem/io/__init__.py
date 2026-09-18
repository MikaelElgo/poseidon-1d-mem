"""
p2mem.io - File-ingestion layer for the Poseidon 2 MEM project.

Increment 2 adds the LAS-ingestion module (`p2mem.io.las`) and its
inventory-report builder (`p2mem.io.inventory`). No other file formats
(deviation surveys, checkshots, formation tops) are ingested by this
package yet - those are explicitly out of scope for this increment.
"""

from __future__ import annotations

__all__ = ["las", "inventory"]
