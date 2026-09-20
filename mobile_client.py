from __future__ import annotations

import argparse
import json
from urllib.request import Request, urlopen


def request(base_url: str, token: str, path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(base_url.rstrip("/") + path, data=data, headers=headers, method="POST" if data else "GET")
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a task to a Gemini agent mobile bridge")
    parser.add_argument("base_url", help="Example: http://127.0.0.1:8765")
    parser.add_argument("task", nargs="*", help="Task to execute; multiple words are joined")
    parser.add_argument("--token", required=True)
    parser.add_argument("--capabilities", action="store_true")
    args, extras = parser.parse_known_args()
    if args.capabilities:
        print(json.dumps(request(args.base_url, args.token, "/capabilities"), indent=2))
        return
    task = " ".join(args.task + extras).strip()
    if not task:
        parser.error("task is required unless --capabilities is used")
    print(json.dumps(request(args.base_url, args.token, "/command", {"task": task}), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
