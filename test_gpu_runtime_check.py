"""No real torch imports or GPU operations: all backend behavior is mocked."""
import contextlib
import importlib
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

import gpu_runtime_check as check


def backend(count=1, available=True, build="fixture-cuda"):
    torch = Mock()
    torch.__version__ = "fixture-torch"
    torch.version = SimpleNamespace(cuda=build)
    torch.cuda.is_available.return_value = available
    torch.cuda.device_count.return_value = count
    torch.cuda.get_device_name.side_effect = lambda i: f"Fixture GPU {i}"
    result = Mock(device="cuda:0")
    result.cpu.return_value.tolist.return_value = [5, 3, -3, 7]
    a, b = Mock(device="cuda:0"), Mock(device="cuda:0")
    a.__add__ = Mock(return_value=result)
    torch.tensor.side_effect = [a, b]
    return torch, a, b, result


class RuntimeTests(unittest.TestCase):
    def run_check(self, args=(), torch=None, error=None):
        torch = torch if torch is not None else backend()[0]
        with patch.object(check.importlib, "import_module", return_value=torch,
                          side_effect=error) as load, contextlib.redirect_stdout(io.StringIO()) as output:
            code = check.main(list(args))
        load.assert_called_once_with("torch")
        return code, output.getvalue()

    def test_missing_torch(self):
        code, text = self.run_check(error=ModuleNotFoundError("missing", name="torch"))
        self.assertEqual(code, 1)
        self.assertIn("not installed", text)

    def test_import_failure(self):
        for error in (OSError("DLL failure"), ModuleNotFoundError("dependency", name="other")):
            self.assertEqual(self.run_check(error=error)[0], 3)

    def test_cpu_only(self):
        torch = backend(build=None)[0]
        self.assertEqual(self.run_check(torch=torch)[0], 1)
        torch.tensor.assert_not_called()

    def test_cuda_unavailable_no_fallback(self):
        torch = backend(available=False)[0]
        self.assertEqual(self.run_check(["--device", "cuda:0"], torch)[0], 1)
        torch.tensor.assert_not_called()

    def test_successful_arithmetic(self):
        torch, a, b, result = backend()
        code, text = self.run_check(torch=torch)
        self.assertEqual(code, 0)
        self.assertIn("PASS: tiny CUDA", text)
        self.assertIn("Fixture GPU 0", text)
        self.assertEqual(torch.tensor.call_args_list, [
            call([1, -2, 3, 0], dtype=torch.int64, device="cuda:0"),
            call([4, 5, -6, 7], dtype=torch.int64, device="cuda:0")])
        a.__add__.assert_called_once_with(b)
        torch.cuda.synchronize.assert_called_once_with("cuda:0")
        result.cpu.assert_called_once_with()

    def test_multiple_gpus_selection(self):
        torch, a, b, result = backend(count=2)
        for tensor in (a, b, result):
            tensor.device = "cuda:1"
        code, text = self.run_check(["--device", "cuda:1"], torch)
        self.assertEqual(code, 0)
        self.assertIn("Fixture GPU 1", text)
        torch.cuda.synchronize.assert_called_once_with("cuda:1")
        self.assertTrue(all(c.kwargs["device"] == "cuda:1" for c in torch.tensor.call_args_list))

    def test_invalid_index(self):
        for count in (0, 1):
            torch = backend(count=count)[0]
            self.assertEqual(self.run_check(["--device", "cuda:2"], torch)[0], 2)
            torch.tensor.assert_not_called()

    def test_invalid_syntax_does_not_import(self):
        for device in ("cpu", "cuda", "cuda:-1", "cuda:x"):
            with patch.object(check.importlib, "import_module") as load, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exc:
                    check.main(["--device", device])
                self.assertEqual(exc.exception.code, 2)
                load.assert_not_called()

    def test_incorrect_result(self):
        torch, _, _, result = backend()
        result.cpu.return_value.tolist.return_value = [0]
        code, text = self.run_check(torch=torch)
        self.assertEqual(code, 3)
        self.assertIn("arithmetic mismatch", text)

    def test_sync_failure(self):
        torch, _, _, result = backend()
        torch.cuda.synchronize.side_effect = RuntimeError("sync")
        self.assertEqual(self.run_check(torch=torch)[0], 3)
        result.cpu.assert_not_called()

    def test_allocation_failure(self):
        torch = backend()[0]
        torch.tensor.side_effect = RuntimeError("allocation")
        self.assertEqual(self.run_check(torch=torch)[0], 3)
        torch.cuda.synchronize.assert_not_called()

    def test_operation_and_transfer_failures(self):
        for stage in ("add", "transfer"):
            torch, a, _, result = backend()
            if stage == "add":
                a.__add__.side_effect = RuntimeError("kernel")
            else:
                result.cpu.side_effect = RuntimeError("transfer")
            self.assertEqual(self.run_check(torch=torch)[0], 3)

    def test_initialization_failure(self):
        torch = backend()[0]
        torch.cuda.get_device_name.side_effect = RuntimeError("initialization")
        self.assertEqual(self.run_check(torch=torch)[0], 3)
        torch.tensor.assert_not_called()

    def test_check_only_no_execution(self):
        torch, a, _, result = backend()
        code, text = self.run_check(["--check-only"], torch)
        self.assertEqual(code, 0)
        self.assertIn("GPU execution UNVERIFIED", text)
        self.assertNotIn("PASS:", text)
        torch.tensor.assert_not_called()
        torch.cuda.synchronize.assert_not_called()
        a.__add__.assert_not_called()
        result.cpu.assert_not_called()

    def test_wrong_device_rejected(self):
        torch, _, _, result = backend()
        result.device = "cpu"
        self.assertEqual(self.run_check(torch=torch)[0], 3)

    def test_module_import_is_lazy(self):
        with patch.object(check.importlib, "import_module", side_effect=AssertionError("heavy import")),                 contextlib.redirect_stdout(io.StringIO()) as output:
            importlib.reload(check)
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
