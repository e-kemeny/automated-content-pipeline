"""All inference and media operations are mocked; fixtures are tiny byte files."""
import contextlib
import hashlib
import importlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

import vision_inference as experiment


def metadata(duration="100", streams=None):
    if streams is None:
        streams = [dict(codec_type="video", width=320, height=180, index=0)]
    return dict(format=dict(duration=duration), streams=streams)


def backend():
    torch, vision, images = MagicMock(), MagicMock(), MagicMock()
    torch.__version__, vision.__version__ = "fixture-torch", "fixture-vision"
    torch.version.cuda = "fixture-cuda"
    torch.cuda.is_available.return_value = True
    torch.cuda.device_count.return_value = 1
    torch.cuda.get_device_name.return_value = "Fixture GPU"
    torch.cuda.max_memory_allocated.return_value = 2 * 1024**2
    model, weights = MagicMock(), MagicMock()
    model.to.return_value = model
    model.eval.return_value = model
    weights.url = "https://download.pytorch.org/models/resnet18-fixture.pth"
    weights.meta = dict(categories=["one", "two", "three", "four"])
    scores, indices = Mock(), Mock()
    scores.cpu.return_value.tolist.return_value = [0.6, 0.3, 0.1]
    indices.cpu.return_value.tolist.return_value = [2, 0, 1]
    model.return_value.__getitem__.return_value.softmax.return_value.topk.return_value = (scores, indices)
    return torch, vision, images, model, weights


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / "fixture.mp4"
        self.video.write_bytes(b"not actual media; mocked probe")
        self.output = self.root / "results" / "vision.json"

    def run_mocked(self, **kwargs):
        torch, vision, images, model, weights = backend()
        def extracted(video, timestamp, index, target):
            target.write_bytes(b"mock frame")
        with (
            patch.object(experiment, "probe_format_streams", return_value=metadata()),
            patch.object(experiment.shutil, "which", return_value="tool"),
            patch.object(experiment.importlib, "import_module",
                         side_effect=[torch, vision, images]),
            patch.object(experiment, "load_model", return_value=(model, weights)) as load,
            patch.object(experiment, "extract_frame", side_effect=extracted) as extract,
        ):
            result = experiment.run_experiment(self.video, self.output, **kwargs)
        return result, torch, model, weights, load, extract

    def test_sampling(self):
        for actual, expected in zip(experiment.sample_timestamps(100, 5), [100*i/6 for i in range(1, 6)]):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(experiment.sample_timestamps(10, 1), [5])

    def test_invalid_count(self):
        for count in (0, -1, 101, True, 1.5):
            with self.assertRaises(ValueError):
                experiment.sample_timestamps(10, count)

    def test_invalid_duration(self):
        for duration in (0, -1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                experiment.sample_timestamps(duration, 5)

    def test_missing_video(self):
        with patch.object(experiment, "probe_format_streams") as probe:
            with self.assertRaisesRegex(ValueError, "Missing video"):
                experiment.inspect_video(self.root/"missing.mp4")
            probe.assert_not_called()

    def test_missing_media_tools(self):
        for missing in ("ffmpeg", "ffprobe"):
            with patch.object(experiment.shutil, "which", side_effect=lambda tool: None if tool == missing else "tool"):
                with self.assertRaisesRegex(ValueError, missing):
                    experiment.inspect_video(self.video)

    def test_probe_validation(self):
        for value in (metadata("nan"), metadata("0"), metadata(streams=[]),
                      metadata(streams=[dict(codec_type="audio")]), {},
                      metadata(streams=[dict(codec_type="video", disposition=dict(attached_pic=1))])):
            with (patch.object(experiment.shutil, "which", return_value="tool"),
                  patch.object(experiment, "probe_format_streams", return_value=value)):
                with self.assertRaises(ValueError):
                    experiment.inspect_video(self.video)

    def test_valid_video_no_audio_required(self):
        with (patch.object(experiment.shutil, "which", return_value="tool"),
              patch.object(experiment, "probe_format_streams", return_value=metadata())):
            self.assertEqual(experiment.inspect_video(self.video)["duration_seconds"], 100)

    def test_extraction_command(self):
        target = self.root/"frame.png"
        def fake_run(*args, **kwargs):
            target.write_bytes(b"png")
        with patch.object(experiment.subprocess, "run", side_effect=fake_run) as run:
            experiment.extract_frame(self.video, 50.0, 0, target)
        run.assert_called_once_with(
            ["ffmpeg", "-v", "error", "-nostdin", "-n", "-ss", "50.0",
             "-i", str(self.video), "-map", "0:0", "-frames:v", "1",
             "-pix_fmt", "rgb24", str(target)],
            check=True, capture_output=True, text=True, timeout=60)

    def test_extraction_failures(self):
        for error in (subprocess.CalledProcessError(1, ["ffmpeg"]),
                      subprocess.TimeoutExpired([], 60), OSError("missing"), None):
            with patch.object(experiment.subprocess, "run", side_effect=error):
                with self.assertRaisesRegex(RuntimeError, "Frame extraction failed"):
                    experiment.extract_frame(self.video, 50, 0, self.root/"absent.png")

    def weight_backend(self):
        torch, vision, _, _, _ = backend()
        torch.hub.get_dir.return_value = str(self.root/"hub")
        weights = vision.models.ResNet18_Weights.IMAGENET1K_V1
        digest = hashlib.sha256(b"fixture weights").hexdigest()[:8]
        weights.url = f"https://download.pytorch.org/models/resnet18-{digest}.pth"
        return torch, vision, weights

    def test_missing_weights_never_downloads(self):
        torch, vision, _ = self.weight_backend()
        with self.assertRaisesRegex(FileNotFoundError, "--allow-model-download"):
            experiment.load_model(torch, vision, False)
        torch.hub.load_state_dict_from_url.assert_not_called()
        vision.models.resnet18.assert_not_called()

    def test_download_opt_in(self):
        torch, vision, weights = self.weight_backend()
        model, result_weights = experiment.load_model(torch, vision, True)
        torch.hub.load_state_dict_from_url.assert_called_once_with(
            weights.url, map_location="cpu", progress=False, check_hash=True, weights_only=True)
        vision.models.resnet18.assert_called_once_with(weights=None)
        model.load_state_dict.assert_called_once()
        self.assertIs(result_weights, weights)

    def test_cached_weights_use_local_only(self):
        torch, vision, weights = self.weight_backend()
        path = self.root/"hub"/"checkpoints"/Path(weights.url).name
        path.parent.mkdir(parents=True)
        path.write_bytes(b"fixture weights")
        experiment.load_model(torch, vision, False)
        torch.load.assert_called_once()
        self.assertEqual(torch.load.call_args.kwargs, dict(map_location="cpu", weights_only=True))
        torch.hub.load_state_dict_from_url.assert_not_called()

    def test_corrupt_cached_weights_not_repaired(self):
        torch, vision, weights = self.weight_backend()
        path = self.root/"hub"/"checkpoints"/Path(weights.url).name
        path.parent.mkdir(parents=True)
        path.write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            experiment.load_model(torch, vision, True)
        torch.hub.load_state_dict_from_url.assert_not_called()

    def test_cuda_unavailable(self):
        torch = backend()[0]
        torch.cuda.is_available.return_value = False
        with self.assertRaisesRegex(ValueError, "CUDA unavailable"):
            experiment.select_device(torch, "cuda:0")

    def test_invalid_device_and_cpu_rejected(self):
        torch = backend()[0]
        for device in ("cpu", "cuda:-1", "cuda", "cuda:1"):
            with self.assertRaises(ValueError):
                experiment.select_device(torch, device)

    def test_success_schema_top3_and_single_model_load(self):
        result, torch, model, weights, load, extract = self.run_mocked()
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["video"]["sha256"], hashlib.sha256(self.video.read_bytes()).hexdigest())
        self.assertEqual(result["runtime"]["peak_allocated_gpu_memory_mib"], 2)
        self.assertEqual(result["runtime"]["gpu_name"], "Fixture GPU")
        self.assertEqual(len(result["frames"]), 5)
        self.assertEqual(result["frames"][0]["top3"],
                         [dict(category="three", confidence=.6), dict(category="one", confidence=.3),
                          dict(category="two", confidence=.1)])
        self.assertGreaterEqual(result["frames"][0]["inference_latency_ms"], 0)
        load.assert_called_once()
        model.to.assert_called_once_with("cuda:0")
        model.eval.assert_called_once()
        torch.inference_mode.assert_called_once()
        weights.transforms.assert_called_once()
        self.assertEqual(model.call_count, 5)
        self.assertEqual(extract.call_count, 5)
        for invocation in extract.call_args_list:
            self.assertFalse(invocation.args[-1].parent.exists())
        self.assertEqual(json.loads(self.output.read_text()), result)

    def test_existing_output_rejected_before_inference(self):
        self.output.parent.mkdir()
        self.output.write_text("original")
        with patch.object(experiment.importlib, "import_module") as load:
            with self.assertRaises(FileExistsError):
                experiment.run_experiment(self.video, self.output)
            load.assert_not_called()
        self.assertEqual(self.output.read_text(), "original")

    def test_explicit_overwrite_owned_artifact(self):
        result, *_ = self.run_mocked(frames=1)
        replacement = dict(result, frames=[])
        experiment.save_result(self.output, replacement, True)
        self.assertEqual(json.loads(self.output.read_text()), replacement)
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_unrelated_overwrite_rejected(self):
        self.output.parent.mkdir()
        self.output.write_text('{"schema_version":1}')
        with self.assertRaisesRegex(ValueError, "unrelated"):
            experiment.check_output(self.output, True)

    def test_no_repository_source_output(self):
        with self.assertRaisesRegex(ValueError, "ignored output"):
            experiment.check_output(experiment.ROOT/"new_source.json", False)

    def test_atomic_publish_failure_preserves_existing(self):
        old = dict(experiment=experiment.EXPERIMENT, schema_version=1, value="old")
        experiment.save_result(self.output, old)
        with patch.object(experiment.os, "replace", side_effect=OSError("publish failed")):
            with self.assertRaises(OSError):
                experiment.save_result(self.output, dict(old, value="new"), True)
        self.assertEqual(json.loads(self.output.read_text()), old)
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_racing_creation_not_clobbered(self):
        def raced_link(source, destination):
            destination.write_text("racer")
            raise FileExistsError("raced")
        with patch.object(experiment.os, "link", side_effect=raced_link):
            with self.assertRaises(FileExistsError):
                experiment.save_result(self.output, dict(schema_version=1))
        self.assertEqual(self.output.read_text(), "racer")
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_inference_failure_no_output_or_parent(self):
        with (patch.object(experiment.shutil, "which", return_value="tool"),
              patch.object(experiment, "probe_format_streams", return_value=metadata()),
              patch.object(experiment.importlib, "import_module", side_effect=ImportError("missing torch"))):
            with self.assertRaises(ImportError):
                experiment.run_experiment(self.video, self.output)
        self.assertFalse(self.output.parent.exists())

    def test_model_failure_leaves_existing_output(self):
        old = dict(schema_version=1, experiment=experiment.EXPERIMENT)
        experiment.save_result(self.output, old)
        torch, vision, images, _, _ = backend()
        with (patch.object(experiment.shutil, "which", return_value="tool"),
              patch.object(experiment, "probe_format_streams", return_value=metadata()),
              patch.object(experiment.importlib, "import_module", side_effect=[torch, vision, images]),
              patch.object(experiment, "load_model", side_effect=RuntimeError("model failed"))):
            with self.assertRaises(RuntimeError):
                experiment.run_experiment(self.video, self.output, overwrite=True)
        self.assertEqual(json.loads(self.output.read_text()), old)

    def test_invalid_prediction_rejected(self):
        probabilities = Mock()
        scores, indices = Mock(), Mock()
        scores.cpu.return_value.tolist.return_value = [float("nan"), .2, .1]
        indices.cpu.return_value.tolist.return_value = [0, 1, 2]
        probabilities.topk.return_value = (scores, indices)
        with self.assertRaises(ValueError):
            experiment.top_predictions(probabilities, ["a", "b", "c"])

    def test_cli_forwarding_and_error(self):
        with (patch.object(experiment, "run_experiment", return_value=dict(frames=[])) as run,
              contextlib.redirect_stdout(io.StringIO())):
            self.assertEqual(experiment.main(["--video", "v.mp4", "--allow-model-download", "--overwrite"]), 0)
        self.assertEqual(run.call_args.kwargs, dict(video=Path("v.mp4"), output=Path("output/vision_inference_v1.json"),
                         frames=5, device="cuda:0", allow_model_download=True, overwrite=True))
        with (patch.object(experiment, "run_experiment", side_effect=RuntimeError("failed")),
              contextlib.redirect_stdout(io.StringIO())):
            self.assertEqual(experiment.main(["--video", "v.mp4"]), 1)

    def test_later_frame_failure_discards_all_results(self):
        torch, vision, images, model, weights = backend()
        paths = []
        def extraction(video, timestamp, index, target):
            paths.append(target)
            if len(paths) == 2:
                raise RuntimeError("second frame failed")
            target.write_bytes(b"fixture")
        with (patch.object(experiment.shutil, "which", return_value="tool"),
              patch.object(experiment, "probe_format_streams", return_value=metadata()),
              patch.object(experiment.importlib, "import_module", side_effect=[torch, vision, images]),
              patch.object(experiment, "load_model", return_value=(model, weights)),
              patch.object(experiment, "extract_frame", side_effect=extraction)):
            with self.assertRaisesRegex(RuntimeError, "second frame"):
                experiment.run_experiment(self.video, self.output)
        self.assertFalse(self.output.parent.exists())
        self.assertTrue(all(not path.parent.exists() for path in paths))

    def test_changed_source_not_published(self):
        with patch.object(experiment, "file_identity", side_effect=[("a"*64, 10), ("b"*64, 10)]):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.run_mocked(frames=1)
        self.assertFalse(self.output.parent.exists())

    def test_import_no_ml_loading(self):
        with patch.object(experiment.importlib, "import_module", side_effect=AssertionError("ML import")):
            importlib.reload(experiment)


if __name__ == "__main__":
    unittest.main()
