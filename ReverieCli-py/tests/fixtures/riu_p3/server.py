"""Local stdio negative fixture. All effects stay in the explicitly supplied directory."""
import argparse
import json
from pathlib import Path
import sys

SECRET = "PRIVATE_META_MUST_NEVER_REACH_MODEL"
parser = argparse.ArgumentParser()
parser.add_argument("--state", type=Path, required=True)
args = parser.parse_args()
args.state.mkdir(parents=True, exist_ok=True)
count = 0
tools = ["show", "alias", "missing", "bad-mime", "wrong-uri", "network", "oversize", "meta-only", "error"]


def handle(method, params):
    global count
    if method == "initialize":
        return {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}, "resources": {}}, "serverInfo": {"name": "RIU negative fixture", "version": "1"}}
    if method == "tools/list":
        entries = []
        for name in tools:
            uri = f"ui://negative/{name}.html"
            meta = {"openai/outputTemplate": uri} if name == "alias" else {"ui": {"resourceUri": uri}}
            entries.append({"name": name, "description": "Offline P3 fixture " + name, "inputSchema": {"type": "object", "properties": {}}, "_meta": meta})
        entries.extend([
            {"name": "increment", "description": "APP_ONLY_HIDDEN_DESCRIPTOR", "inputSchema": {"type": "object", "properties": {}}, "_meta": {"ui": {"visibility": ["app"]}}},
            {"name": "model-only", "inputSchema": {"type": "object", "properties": {}}, "_meta": {"ui": {"visibility": ["model"]}}},
        ])
        return {"tools": entries}
    if method == "resources/list":
        return {"resources": []}
    if method == "tools/call":
        name = params["name"]
        if name == "increment":
            count += 1
            (args.state / "effects.json").write_text(json.dumps({"count": count}), encoding="utf-8")
        if name == "meta-only":
            return {"_meta": {"private": SECRET}}
        return {"content": [{"type": "text", "text": f"Useful text for {name}; count={count}."}],
                "structuredContent": {"name": name, "count": count}, "isError": name == "error", "_meta": {"private": SECRET}}
    if method == "resources/read":
        uri = params["uri"]
        name = uri.rsplit("/", 1)[-1].removesuffix(".html")
        if name == "missing":
            raise ValueError("UI resource is offline.")
        item = {"uri": uri, "mimeType": "text/html;profile=mcp-app", "text": Path(__file__).with_name("standard.html").read_text(encoding="utf-8")}
        if name == "bad-mime": item["mimeType"] = "text/html"
        if name == "wrong-uri": item["uri"] = "file:///private.html"
        if name == "oversize": item["text"] = "x" * (2 * 1024 * 1024 + 1)
        if name == "network": item["_meta"] = {"ui": {"csp": {"connectDomains": ["https://example.invalid"]}}}
        return {"contents": [item]}
    raise ValueError("Unsupported fixture method: " + method)


for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    try:
        response = {"jsonrpc": "2.0", "id": request["id"], "result": handle(request["method"], request.get("params", {}))}
    except Exception as error:
        response = {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32601, "message": str(error)}}
    print(json.dumps(response), flush=True)
