import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys
import unittest

WORKER = Path(__file__).with_name("worker.py")
spec = importlib.util.spec_from_file_location("health_worker", WORKER)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerTests(unittest.TestCase):
    def request(self, **changes):
        value = {"request_id": "test-1", "protocol_version": 1, "command": "health_check"}
        value.update(changes)
        return json.dumps(value)

    def test_health(self):
        result = worker.respond(self.request())
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["request_id"], "test-1")
        self.assertEqual(result["data"]["pythonVersion"], platform.python_version())
        self.assertEqual(result["data"]["operatingSystem"], platform.system())
        self.assertEqual(result["data"]["cpuArchitecture"], platform.machine())
        self.assertEqual(result["data"]["workerProtocolVersion"], 1)
        self.assertIsNone(result["error"])

    def test_malformed(self):
        for raw in ["{", "null", "[]", "{}", self.request(request_id="")]:
            self.assertEqual(worker.respond(raw)["error"]["code"], "invalid_request")

    def test_unsupported_command(self):
        self.assertEqual(worker.respond(self.request(command="export"))["error"]["code"], "unsupported_command")

    def test_version_mismatch(self):
        for version in [0, 2, True, "1"]:
            self.assertEqual(worker.respond(self.request(protocol_version=version))["error"]["code"], "unsupported_version")

    def test_extra_fields_rejected(self):
        self.assertEqual(worker.respond(self.request(path="anything"))["status"], "error")

    def test_real_one_shot_stdout(self):
        result = subprocess.run([sys.executable, "-I", "-B", str(WORKER)],
                                input=self.request(), capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertEqual(json.loads(result.stdout)["status"], "ok")

    def test_real_oversized_request(self):
        result = subprocess.run([sys.executable, "-I", "-B", str(WORKER)],
                                input=" " * 5000, capture_output=True, text=True, timeout=5)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "invalid_request")


if __name__ == "__main__":
    unittest.main()
