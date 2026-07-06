"""Upload locally prewarmed XHS artifacts to Azure Blob Storage.

This intentionally uses only the Python standard library plus the Azure CLI
token already available after ``az login``. It uploads selected XHS artifacts
only, so browser profiles, cookies, storage state, and diagnostic auth files are
not accidentally copied.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import http.client
import json
import mimetypes
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import formatdate
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ACCOUNT = "plusonexhs"
DEFAULT_CONTAINER = "xhs-prewarm"
DEFAULT_MEDIA_DIR = ROOT / "backend" / "media" / "xhs"
DEFAULT_DATA_DIR = ROOT / "data" / "xhs"
DEFAULT_CACHE_FILE = ROOT / "tmp-xhs-prewarm-cache.jsonl"
DEFAULT_REPORTS_GLOB = "tmp-xhs-prewarm-*-report.json"
STORAGE_RESOURCE = "https://storage.azure.com/"
API_VERSION = "2023-11-03"
HTTP_OK = 200
HTTP_NOT_FOUND = 404
DRY_RUN_SAMPLE_LIMIT = 20


@dataclass(frozen=True, slots=True)
class UploadItem:
    local_path: Path
    blob_name: str
    size: int


@dataclass(slots=True)
class UploadResult:
    action: str
    item: UploadItem
    message: str = ""


class AzureCliTokenProvider:
    """Fetch and refresh an Azure Storage bearer token from ``az``."""

    def __init__(self, subscription: str | None = None) -> None:
        self._subscription = subscription
        self._lock = threading.Lock()
        self._token = ""
        self._expires_at = datetime.now(UTC)

    def token(self) -> str:
        with self._lock:
            if self._token and datetime.now(UTC) < self._expires_at - timedelta(minutes=5):
                return self._token
            self._refresh_locked()
            return self._token

    def _refresh_locked(self) -> None:
        az_executable = shutil.which("az") or shutil.which("az.cmd")
        if az_executable is None:
            raise RuntimeError("Azure CLI not found. Install it, then run `az login`.")
        cmd = [
            az_executable,
            "account",
            "get-access-token",
            "--resource",
            STORAGE_RESOURCE,
            "--output",
            "json",
        ]
        if self._subscription:
            cmd.extend(["--subscription", self._subscription])
        try:
            completed = subprocess.run(  # noqa: S603 - fixed az CLI argv, no shell.
                cmd,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Azure CLI executable disappeared. Run `az login` and retry."
            ) from exc
        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(f"Azure CLI token fetch failed. Run `az login`. {details}") from exc

        payload = json.loads(completed.stdout)
        token = str(payload.get("accessToken") or "")
        if not token:
            raise RuntimeError("Azure CLI returned no accessToken. Run `az login` again.")
        self._token = token
        self._expires_at = _parse_token_expiry(payload)


class BlobUploader:
    def __init__(
        self,
        account: str,
        container: str,
        token_provider: AzureCliTokenProvider,
        *,
        max_retries: int,
    ) -> None:
        self._account = account
        self._container = container
        self._token_provider = token_provider
        self._max_retries = max_retries
        self._host = f"{account}.blob.core.windows.net"

    def create_container_if_missing(self) -> None:
        status, _, body = self._request(
            "PUT",
            f"/{quote(self._container)}?restype=container",
            headers={"Content-Length": "0"},
        )
        if status in (201, 202, 409):
            return
        raise RuntimeError(f"create container failed: HTTP {status} {body[:300]}")

    def remote_size(self, blob_name: str) -> int | None:
        status, headers, body = self._request("HEAD", self._blob_path(blob_name))
        if status == HTTP_NOT_FOUND:
            return None
        if status != HTTP_OK:
            raise RuntimeError(f"HEAD {blob_name} failed: HTTP {status} {body[:300]}")
        raw = headers.get("content-length")
        return int(raw) if raw is not None else None

    def upload(self, item: UploadItem) -> None:
        content_type = _content_type(item.local_path)
        with item.local_path.open("rb") as stream:
            status, _, body = self._request(
                "PUT",
                self._blob_path(item.blob_name),
                headers={
                    "Content-Length": str(item.size),
                    "Content-Type": content_type,
                    "x-ms-blob-type": "BlockBlob",
                },
                body=stream,
            )
        if status not in (201, 202):
            raise RuntimeError(f"upload {item.blob_name} failed: HTTP {status} {body[:300]}")

    def _blob_path(self, blob_name: str) -> str:
        return f"/{quote(self._container)}/{quote(blob_name, safe='/~')}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        body: Any = None,
    ) -> tuple[int, dict[str, str], str]:
        headers = dict(headers or {})
        headers.update(
            {
                "Authorization": f"Bearer {self._token_provider.token()}",
                "x-ms-date": formatdate(timeval=None, localtime=False, usegmt=True),
                "x-ms-version": API_VERSION,
            }
        )

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            conn = http.client.HTTPSConnection(self._host, timeout=120)
            try:
                if hasattr(body, "seek"):
                    body.seek(0)
                conn.request(method, path, body=body, headers=headers)
                response = conn.getresponse()
                raw_body = response.read().decode("utf-8", errors="replace")
                response_headers = {k.lower(): v for k, v in response.getheaders()}
                if response.status in (429, 500, 502, 503, 504) and attempt < self._max_retries:
                    time.sleep(min(2**attempt, 20))
                    continue
                return response.status, response_headers, raw_body
            except (TimeoutError, OSError, http.client.HTTPException) as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                time.sleep(min(2**attempt, 20))
            finally:
                conn.close()
        assert last_error is not None
        raise last_error


def _parse_token_expiry(payload: dict[str, Any]) -> datetime:
    expires_on = payload.get("expires_on")
    if expires_on is not None:
        try:
            return datetime.fromtimestamp(int(expires_on), tz=UTC)
        except (TypeError, ValueError, OSError):
            pass
    raw = str(payload.get("expiresOn") or "")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC) + timedelta(minutes=30)


def _content_type(path: Path) -> str:
    if path.suffix.lower() == ".jsonl":
        return "application/jsonl"
    if path.suffix.lower() == ".webp":
        return "image/webp"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _normalise_prefix(prefix: str) -> str:
    return prefix.strip().strip("/")


def _blob_join(prefix: str, *parts: str) -> str:
    clean = [p.strip("/").replace("\\", "/") for p in parts if p.strip("/")]
    if prefix:
        clean.insert(0, prefix)
    return "/".join(clean)


def _iter_files(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*") if p.is_file())


def collect_upload_items(args: argparse.Namespace) -> list[UploadItem]:
    prefix = _normalise_prefix(args.prefix)
    items: list[UploadItem] = []

    media_dir = args.media_dir.resolve()
    for path in _iter_files(media_dir):
        rel = path.relative_to(media_dir).as_posix()
        items.append(UploadItem(path, _blob_join(prefix, "media", "xhs", rel), path.stat().st_size))

    data_dir = args.data_dir.resolve()
    for path in _iter_files(data_dir):
        rel = path.relative_to(data_dir).as_posix()
        items.append(UploadItem(path, _blob_join(prefix, "data", "xhs", rel), path.stat().st_size))

    cache_file = args.cache_file.resolve()
    if cache_file.exists() and cache_file.is_file():
        items.append(
            UploadItem(
                cache_file,
                _blob_join(prefix, "cache", cache_file.name),
                cache_file.stat().st_size,
            )
        )

    if args.include_reports:
        for path in sorted(args.root.glob(args.reports_glob)):
            if path.is_file():
                items.append(
                    UploadItem(path, _blob_join(prefix, "reports", path.name), path.stat().st_size)
                )

    return items


def upload_one(uploader: BlobUploader, item: UploadItem, overwrite: str) -> UploadResult:
    try:
        if overwrite != "always":
            remote_size = uploader.remote_size(item.blob_name)
            if remote_size is not None:
                if overwrite == "never":
                    return UploadResult("skipped", item, "exists")
                if overwrite == "if-size-diff" and remote_size == item.size:
                    return UploadResult("skipped", item, "same size")
        uploader.upload(item)
        return UploadResult("uploaded", item)
    except Exception as exc:
        return UploadResult("failed", item, str(exc))


def run(args: argparse.Namespace) -> int:
    items = collect_upload_items(args)
    total_size = sum(item.size for item in items)
    print(
        f"planned files={len(items)} size={total_size / 1024 / 1024:.2f} MiB "
        f"account={args.account} container={args.container}",
        flush=True,
    )
    if args.dry_run:
        for item in items[:DRY_RUN_SAMPLE_LIMIT]:
            print(f"DRY {item.local_path} -> {item.blob_name}", flush=True)
        if len(items) > DRY_RUN_SAMPLE_LIMIT:
            print(f"... {len(items) - DRY_RUN_SAMPLE_LIMIT} more", flush=True)
        return 0

    token_provider = AzureCliTokenProvider(subscription=args.subscription)
    uploader = BlobUploader(
        args.account,
        args.container,
        token_provider,
        max_retries=args.max_retries,
    )
    if args.create_container:
        uploader.create_container_if_missing()

    counts = {"uploaded": 0, "skipped": 0, "failed": 0}
    uploaded_bytes = 0
    lock = threading.Lock()

    def record(result: UploadResult) -> None:
        nonlocal uploaded_bytes
        with lock:
            counts[result.action] += 1
            if result.action == "uploaded":
                uploaded_bytes += result.item.size
            done = sum(counts.values())
            if result.action == "failed":
                print(
                    f"FAILED {result.item.local_path} -> {result.item.blob_name}: {result.message}",
                    flush=True,
                )
            elif args.verbose or done % 100 == 0 or done == len(items):
                print(
                    f"progress {done}/{len(items)} "
                    f"uploaded={counts['uploaded']} skipped={counts['skipped']} "
                    f"failed={counts['failed']} uploaded_mb={uploaded_bytes / 1024 / 1024:.2f}",
                    flush=True,
                )

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [executor.submit(upload_one, uploader, item, args.overwrite) for item in items]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            record(result)
            if args.fail_fast and result.action == "failed":
                executor.shutdown(cancel_futures=True)
                break

    print(
        f"done uploaded={counts['uploaded']} skipped={counts['skipped']} "
        f"failed={counts['failed']} uploaded_mb={uploaded_bytes / 1024 / 1024:.2f}",
        flush=True,
    )
    return 1 if counts["failed"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upload local XHS prewarm artifacts to Azure Blob Storage."
    )
    parser.add_argument("--account", default=os.getenv("AZURE_STORAGE_ACCOUNT", DEFAULT_ACCOUNT))
    parser.add_argument(
        "--container", default=os.getenv("AZURE_STORAGE_CONTAINER", DEFAULT_CONTAINER)
    )
    parser.add_argument("--subscription", default=os.getenv("AZURE_SUBSCRIPTION_ID"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--media-dir", type=Path, default=DEFAULT_MEDIA_DIR)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--cache-file", type=Path, default=DEFAULT_CACHE_FILE)
    parser.add_argument(
        "--prefix", default="", help="Optional blob prefix, e.g. backups/2026-07-06"
    )
    parser.add_argument("--include-reports", action="store_true")
    parser.add_argument("--reports-glob", default=DEFAULT_REPORTS_GLOB)
    parser.add_argument(
        "--overwrite",
        choices=("if-size-diff", "always", "never"),
        default="if-size-diff",
        help="Default resumes safely by skipping blobs with the same byte size.",
    )
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--no-create-container", dest="create_container", action="store_false")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.set_defaults(create_container=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
