"""One-off Foursquare Places API smoke test. Reads FOURSQUARE_API_KEY from
backend/.env and issues a single text-search request. Prints PASS/FAIL with
diagnostic info. Run: cd backend && uv run python foursquare_smoke_test.py
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def load_env(env_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()  # noqa: PLW2901
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def redact(s: str) -> str:
    if len(s) <= 6:  # noqa: PLR2004
        return "*" * len(s)
    return s[:3] + "*" * (len(s) - 6) + s[-3:]


def try_request(url: str, headers: dict[str, str], label: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


def main() -> int:
    env_path = Path(__file__).parent / ".env"
    env = load_env(env_path)

    key = env.get("FOURSQUARE_API_KEY", "")
    if not key:
        print("FAIL: FOURSQUARE_API_KEY missing from backend/.env")
        return 1

    print(f"key:     {redact(key)} (len={len(key)})")
    print(f"prefix:  {key[:4]!r}  (expected 'fsq3' for v3 Service Key)")
    print()

    params = urllib.parse.urlencode({"query": "ramen", "near": "Tokyo", "limit": "3"})

    # New endpoint per 2025 migration (old api.foursquare.com/v3 returns 410).
    # Try several auth + version combos to isolate which is wrong.
    new_url = f"https://places-api.foursquare.com/places/search?{params}"
    old_url = f"https://api.foursquare.com/v3/places/search?{params}"
    attempts = [
        (
            "new + Bearer + version",
            new_url,
            {
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
                "X-Places-Api-Version": "2025-06-17",
            },
        ),
        (
            "new + Bearer, no version",
            new_url,
            {"Authorization": f"Bearer {key}", "Accept": "application/json"},
        ),
        (
            "new + raw token, no version",
            new_url,
            {"Authorization": key, "Accept": "application/json"},
        ),
        (
            "old v3 + raw token (legacy)",
            old_url,
            {"Authorization": key, "Accept": "application/json"},
        ),
        (
            "old v3 + Bearer (legacy)",
            old_url,
            {"Authorization": f"Bearer {key}", "Accept": "application/json"},
        ),
    ]

    for label, url, headers in attempts:
        print(f"--- {label} ---")
        status, body = try_request(url, headers, label)
        print(f"status: {status}")
        snippet = body[:500] + ("..." if len(body) > 500 else "")  # noqa: PLR2004
        print(f"body:   {snippet}")
        print()

        if status == 200:  # noqa: PLR2004
            try:
                data = json.loads(body)
                results = data.get("results", [])
                print(f"PASS — got {len(results)} results")
                for r in results[:3]:
                    name = r.get("name", "?")
                    addr = (r.get("location") or {}).get("formatted_address", "?")
                    print(f"  - {name}  |  {addr}")
                return 0
            except json.JSONDecodeError as e:
                print(f"FAIL: 200 but body not JSON: {e}")
                return 1

    print("FAIL: all attempts rejected. likely causes:")
    print("  - key revoked / not yet active")
    print("  - key is for a different service (not Foursquare v3)")
    print("  - key is legacy CLIENT_SECRET (v3 needs new Service Key, fsq3...)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
