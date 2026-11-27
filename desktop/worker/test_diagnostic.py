import json
import subprocess
import sys
import unittest
from unittest.mock import patch
from test_worker import worker, WORKER


class DiagnosticTests(unittest.TestCase):
    def request(self, **changes):
        request = {"request_id": "job-test", "job_id": "job-test",
                   "protocol_version": 1, "command": "diagnostic_job"}
        request.update(changes)
        return request

    def test_ordered_real_checks_without_pacing(self):
        events = []
        pauses = []
        self.assertEqual(worker.diagnostic(self.request(), events.append, pauses.append), 0)
        self.assertEqual([e["sequence"] for e in events], list(range(1, 15)))
        self.assertEqual([e["completed"] for e in events], [0, *range(1, 13), 12])
        self.assertEqual(events[-1]["event"], "completed")
        self.assertEqual(pauses, [1] * 12)
        self.assertTrue(all(e["job_id"] == "job-test" for e in events))

    def test_diagnostic_request_validation(self):
        for changes in [{"job_id": "other"}, {"protocol_version": 2}, {"extra": True}]:
            request, problem = worker.parse_request(json.dumps(self.request(**changes)))
            self.assertIsNone(request)
            self.assertEqual(problem["status"], "error")

    def test_structured_failure(self):
        events = []
        with patch.object(worker.platform, "python_version", return_value=""):
            self.assertEqual(worker.diagnostic(self.request(), events.append, lambda _: None), 1)
        self.assertEqual(events[-1]["event"], "failed")
        self.assertEqual(events[-1]["error"]["code"], "diagnostic_failed")

    def test_real_stream_flushes_before_exit(self):
        process = subprocess.Popen([sys.executable, "-I", "-B", str(WORKER)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True)
        try:
            process.stdin.write(json.dumps(self.request()))
            process.stdin.close()
            first = json.loads(process.stdout.readline())
            self.assertEqual(first["event"], "started")
            self.assertIsNone(process.poll())
        finally:
            process.kill()
            process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()


if __name__ == "__main__":
    unittest.main()
