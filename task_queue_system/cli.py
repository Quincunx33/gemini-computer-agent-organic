import argparse
import json
import urllib.request
import urllib.error
import sys

DEFAULT_URL = "http://localhost:8899"

def api_request(method: str, endpoint: str, data: dict = None, port: int = 8899):
    url = f"http://localhost:{port}{endpoint}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            return resp.status, json.loads(resp_body) if resp_body else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_body)
        except:
            err_json = {"error": err_body}
        return e.code, err_json
    except urllib.error.URLError as e:
        print(f"Error connecting to server at {url}: {e.reason}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Task Queue System CLI Client")
    parser.add_argument("--port", type=int, default=8899, help="Server port (default: 8899)")
    
    subparsers = parser.add_subparsers(dest="command", required=True)

    # submit
    sub_submit = subparsers.add_parser("submit", help="Submit a new task")
    sub_submit.add_argument("--name", required=True, help="Task handler name")
    sub_submit.add_argument("--payload", default="{}", help="JSON payload string")
    sub_submit.add_argument("--priority", type=int, default=0, help="Priority (integer)")
    sub_submit.add_argument("--retries", type=int, default=3, help="Max retries")
    sub_submit.add_argument("--delay", type=float, default=0.05, help="Retry delay in seconds")

    # list
    subparsers.add_parser("list", help="List all tasks")

    # get
    sub_get = subparsers.add_parser("get", help="Get task details by ID")
    sub_get.add_argument("id", help="Task ID")

    # cancel
    sub_cancel = subparsers.add_parser("cancel", help="Cancel a pending or running task")
    sub_cancel.add_argument("id", help="Task ID")

    # metrics
    subparsers.add_parser("metrics", help="View queue metrics")

    # health
    subparsers.add_parser("health", help="Check server health")

    args = parser.parse_args()

    if args.command == "submit":
        try:
            payload_dict = json.loads(args.payload)
        except json.JSONDecodeError:
            print("Error: --payload must be valid JSON", file=sys.stderr)
            sys.exit(1)

        data = {
            "name": args.name,
            "payload": payload_dict,
            "priority": args.priority,
            "max_retries": args.retries,
            "retry_delay": args.delay
        }
        status, resp = api_request("POST", "/api/tasks", data, port=args.port)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "list":
        status, resp = api_request("GET", "/api/tasks", port=args.port)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "get":
        status, resp = api_request("GET", f"/api/tasks/{args.id}", port=args.port)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "cancel":
        status, resp = api_request("DELETE", f"/api/tasks/{args.id}", port=args.port)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "metrics":
        status, resp = api_request("GET", "/api/metrics", port=args.port)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "health":
        status, resp = api_request("GET", "/api/health", port=args.port)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

if __name__ == "__main__":
    main()
