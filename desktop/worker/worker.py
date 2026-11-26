"""One request per process; stdout contains exactly one protocol response."""
import json
import platform
import sys

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 4096


def failure(request_id, code, message):
    return {"request_id": request_id, "protocol_version": PROTOCOL_VERSION,
            "command": "health_check", "status": "error", "data": None,
            "error": {"code": code, "message": message}}


def respond(raw):
    request_id = None
    try:
        request = json.loads(raw)
    except (ValueError, UnicodeError):
        return failure(None, "invalid_request", "Request must be valid JSON.")
    if not isinstance(request, dict):
        return failure(None, "invalid_request", "Request must be an object.")
    candidate_id = request.get("request_id")
    if isinstance(candidate_id, str) and 0 < len(candidate_id) <= 128:
        request_id = candidate_id
    if request_id is None or set(request) != {"request_id", "protocol_version", "command"}:
        return failure(request_id, "invalid_request", "Invalid request fields.")
    if type(request["protocol_version"]) is not int or request["protocol_version"] != PROTOCOL_VERSION:
        return failure(request_id, "unsupported_version", "Unsupported protocol version.")
    if request["command"] != "health_check":
        return failure(request_id, "unsupported_command", "Only health_check is supported.")
    return {"request_id": request_id, "protocol_version": PROTOCOL_VERSION,
            "command": "health_check", "status": "ok",
            "data": {"pythonVersion": platform.python_version(),
                     "operatingSystem": platform.system(),
                     "cpuArchitecture": platform.machine(),
                     "workerProtocolVersion": PROTOCOL_VERSION}, "error": None}


def main():
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    result = (failure(None, "invalid_request", "Request exceeds size limit.")
              if len(raw) > MAX_REQUEST_BYTES else respond(raw))
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
