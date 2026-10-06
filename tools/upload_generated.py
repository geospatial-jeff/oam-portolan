#!/usr/bin/env python3
"""Upload the generated part of the catalog to the same bucket prefix.

The build writes the full catalog to ``build/site/``. Git tracks only the root
and collection documents, which ``tools/publish.py`` publishes from
``catalog/``. The 21,863 item JSON files, their year subcatalogs and each
collection's ``items.parquet`` are generated, too many to commit, and reach the
bucket through this script instead. Fields of the World publishes its
Sentinel-2 item tree the same way.

Every rule shared with ``publish.py`` is imported from it: the sentinel guard,
content types, change detection, the AWS session and the upload pool. This
script adds one thing, the generated file list from ``oam_mirror.export``.

    python3 tools/upload_generated.py            # dry run: what would change
    python3 tools/upload_generated.py --confirm  # upload; needs credentials

It never deletes, exactly as ``publish.py`` never deletes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from publish import (  # noqa: E402
    ROOT,
    Upload,
    aws_session,
    content_type_for,
    is_unchanged,
    load_config,
    remote_index,
    split_s3_uri,
    unedited_sentinels,
    upload_all,
)

from oam_mirror.export import generated_files  # noqa: E402

SITE = ROOT / "build" / "site"


def collect_generated_uploads(config: dict[str, str], site: Path = SITE) -> list[Upload]:
    """Every generated file, keyed under write_prefix at its site-relative path."""
    if not (site / "catalog.json").is_file():
        sys.exit(f"no built site at {site}; run python -m oam_mirror.build first")
    _, prefix = split_s3_uri(config["write_prefix"])
    uploads = []
    for rel in generated_files(str(site)):
        key = f"{prefix}/{rel}" if prefix else rel
        path = site / rel
        uploads.append(Upload(path, key, content_type_for(path)))
    return uploads


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload the generated items, year catalogs and item mirrors.",
        epilog="Dry run by default. Never deletes.",
    )
    parser.add_argument("--confirm", action="store_true", help="actually upload")
    parser.add_argument(
        "--force", action="store_true", help="re-upload everything; skip the remote listing"
    )
    args = parser.parse_args()

    config = load_config()
    stale = unedited_sentinels(config)
    if stale:
        print("catalog.publish.yaml still carries template values:")
        for value in stale:
            print(f"  {value}")
        return 1

    bucket, prefix = split_s3_uri(config["write_prefix"])
    uploads = collect_generated_uploads(config)
    index = {} if args.force else remote_index(bucket, prefix, config)
    changed = [u for u in uploads if args.force or not is_unchanged(u, index)]

    print(f"site:        {SITE}/")
    print(f"target:      s3://{bucket}/{prefix}")
    print(f"aws profile: {config.get('profile') or '(default session)'}")
    print(f"{len(uploads)} generated file(s), {len(changed)} to upload")
    print("this never deletes; removing a file here does not unpublish it")

    if not args.confirm:
        for upload in changed[:20]:
            print(f"  would upload  {upload.key}")
        if len(changed) > 20:
            print(f"  ... and {len(changed) - 20} more")
        print("\ndry run. re-run with --confirm to upload.")
        return 0

    if not changed:
        print("nothing to upload")
        return 0

    try:
        session = aws_session(config)
    except ImportError:
        sys.exit("boto3 is required to upload. Run: pip install boto3")
    except Exception as exc:  # noqa: BLE001 - stop before any upload
        sys.exit(f"cannot build an AWS session: {exc}")

    failed = upload_all(session, bucket, changed)
    if failed:
        print(f"\n{len(failed)} of {len(changed)} file(s) failed:", file=sys.stderr)
        for key in sorted(failed):
            print(f"  {key}", file=sys.stderr)
        return 1
    print(f"\nuploaded {len(changed)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
