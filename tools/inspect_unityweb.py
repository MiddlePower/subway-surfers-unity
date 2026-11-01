#!/usr/bin/env python3
"""Read-only inspection of a Unity WebGL .data.unityweb archive.

Run: py tools/inspect_unityweb.py Build/SanFrancisco/SanFrancisco.data.unityweb
Optional: append --json
For Brotli compression: py -m pip install brotli
"""
import argparse
import gzip
import json
import struct
from pathlib import Path

MAGIC = b"UnityWebData1.0\x00"
TERMS = (b"Coin", b"coin", b"Collect", b"Pickup", b"Score", b"Currency")


def decode_container(data: bytes) -> tuple[bytes, str]:
    if data.startswith(MAGIC):
        return data, "uncompressed"
    if data.startswith(b"\x1f\x8b"):
        return gzip.decompress(data), "gzip"
    try:
        import brotli
    except ImportError as err:
        raise RuntimeError(
            "Not a raw/gzip UnityWebData container. If this is Brotli-compressed, "
            "run: py -m pip install brotli"
        ) from err
    try:
        decoded = brotli.decompress(data)
    except Exception as err:
        raise ValueError("Unrecognized UnityWebData compression or invalid file") from err
    return decoded, "brotli"


def inspect_bytes(raw: bytes) -> dict:
    if not raw.startswith(MAGIC):
        raise ValueError("Decompressed data lacks the UnityWebData1.0 signature")
    if len(raw) < 20:
        raise ValueError("Truncated UnityWebData header")
    data_start = struct.unpack_from("<I", raw, 16)[0]
    if data_start < 20 or data_start > len(raw):
        raise ValueError("Invalid archive header length")
    cursor = 20
    entries = []
    while cursor < data_start:
        if cursor + 12 > data_start:
            raise ValueError("Truncated archive file record")
        offset, size, name_len = struct.unpack_from("<III", raw, cursor)
        cursor += 12
        if name_len > 16384 or cursor + name_len > data_start:
            raise ValueError("Invalid archive file name")
        name = raw[cursor:cursor + name_len].decode("utf-8", errors="replace")
        cursor += name_len
        if offset < data_start or offset + size > len(raw):
            raise ValueError("File points outside the archive")
        payload = raw[offset:offset + size]
        hits = {term.decode(): payload.count(term) for term in TERMS if term in payload}
        entries.append({
            "name": name,
            "bytes": size,
            "candidate_gameplay_metadata": (
                "metadata" in name.lower() or name.lower().endswith(".assets")
            ),
            "keyword_hits": hits,
        })
    if cursor != data_start:
        raise ValueError("Archive file table alignment mismatch")
    return {"contained_files": entries, "file_count": len(entries)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    raw = args.path.read_bytes()
    unpacked, compression = decode_container(raw)
    result = inspect_bytes(unpacked)
    result.update({
        "compression": compression,
        "compressed_bytes": len(raw),
        "uncompressed_bytes": len(unpacked),
    })
    if args.json:
        print(json.dumps(result, indent=2))
        return
    print(f"Compression: {compression}")
    print(f"Size: {len(raw):,} bytes -> {len(unpacked):,} bytes")
    print(f"Contained files: {result['file_count']}")
    for entry in result["contained_files"]:
        flags = " [METADATA CANDIDATE]" if entry["candidate_gameplay_metadata"] else ""
        print(f" - {entry['name']} ({entry['bytes']:,} bytes){flags}")
        if entry["keyword_hits"]:
            print(f"   text matches: {entry['keyword_hits']}")
    print("NOTE: Keyword matches do not prove a coin handler can be patched.")


if __name__ == "__main__":
    main()
