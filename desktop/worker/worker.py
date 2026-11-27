"""One bounded request per process; stdout is versioned JSON/NDJSON only."""
import hashlib
import json
import platform
import sys
import time

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 4096
STAGES = ("Interpreter", "Protocol", "Checksum")
STEPS_PER_STAGE = 4


def failure(request_id, code, message):
    return {"request_id": request_id, "protocol_version": PROTOCOL_VERSION,
            "command": "health_check", "status": "error", "data": None,
            "error": {"code": code, "message": message}}


def parse_request(raw):
    request_id = None
    try:
        request = json.loads(raw)
    except (ValueError, UnicodeError):
        return None, failure(None, "invalid_request", "Request must be valid JSON.")
    if not isinstance(request, dict):
        return None, failure(None, "invalid_request", "Request must be an object.")
    candidate_id = request.get("request_id")
    if isinstance(candidate_id, str) and 0 < len(candidate_id) <= 128:
        request_id = candidate_id
    fields = {"request_id", "protocol_version", "command"}
    if request.get("command") == "diagnostic_job":
        fields.add("job_id")
    if request_id is None or set(request) != fields:
        return None, failure(request_id, "invalid_request", "Invalid request fields.")
    if type(request["protocol_version"]) is not int or request["protocol_version"] != PROTOCOL_VERSION:
        return None, failure(request_id, "unsupported_version", "Unsupported protocol version.")
    if request["command"] not in ("health_check", "diagnostic_job"):
        return None, failure(request_id, "unsupported_command", "Unsupported command.")
    if request["command"] == "diagnostic_job" and request["job_id"] != request_id:
        return None, failure(request_id, "invalid_request", "Job identity must match request identity.")
    return request, None


def respond(raw):
    request, problem = parse_request(raw)
    if problem:
        return problem
    if request["command"] != "health_check":
        return failure(request["request_id"], "unsupported_command", "Use streaming dispatch for diagnostic_job.")
    return {"request_id": request["request_id"], "protocol_version": PROTOCOL_VERSION,
            "command": "health_check", "status": "ok",
            "data": {"pythonVersion": platform.python_version(),
                     "operatingSystem": platform.system(),
                     "cpuArchitecture": platform.machine(),
                     "workerProtocolVersion": PROTOCOL_VERSION}, "error": None}


def emit(message):
    print(json.dumps(message, sort_keys=True, ensure_ascii=True), flush=True)


def diagnostic(request, send=emit, pause=time.sleep):
    """Twelve actual checks; intentional 1s pacing makes cancellation reviewable."""
    sequence = 0
    completed = 0

    def event(kind, stage, problem=None):
        nonlocal sequence
        sequence += 1
        send({"protocol_version": PROTOCOL_VERSION, "request_id": request["request_id"],
              "job_id": request["job_id"], "command": "diagnostic_job",
              "sequence": sequence, "event": kind, "stage": stage,
              "completed": completed, "total": 12, "error": problem})

    event("started", STAGES[0])
    try:
        for stage in STAGES:
            for _ in range(STEPS_PER_STAGE):
                if stage == "Interpreter":
                    if not platform.python_version() or not platform.system():
                        raise RuntimeError("Interpreter metadata unavailable")
                elif stage == "Protocol":
                    if json.loads(json.dumps({"protocol_version": 1})) != {"protocol_version": 1}:
                        raise RuntimeError("JSON round-trip failed")
                else:
                    if hashlib.sha256(b"abc").hexdigest() != "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad":
                        raise RuntimeError("Checksum self-test failed")
                pause(1)
                completed += 1
                event("progress", stage)
        event("completed", "Finished")
    except Exception as exc:
        print(f"Diagnostic check failed: {exc}", file=sys.stderr)
        event("failed", "Failed", {"code": "diagnostic_failed", "message": str(exc)})
        return 1
    return 0


def main():
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        emit(failure(None, "invalid_request", "Request exceeds size limit."))
        return 0
    request, problem = parse_request(raw)
    if problem:
        emit(problem)
        return 0
    if request["command"] == "diagnostic_job":
        return diagnostic(request)
    emit(respond(raw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
