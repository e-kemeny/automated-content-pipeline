"""Desktop adapter tests: mocked orchestration plus real input/protocol validation."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import processing
import worker

class ProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.video=self.root/'source Ã§Â©Âº Ã¦Â Â¼.mp4';self.video.write_bytes(b'fixture')
        st=self.video.stat()
        self.config=dict(video=str(self.video),workspace=str(self.root/'job space'),mode='both',size_bytes=st.st_size,modified_ms=st.st_mtime_ns//1_000_000)
        self.request=dict(protocol_version=1,request_id='job-1',job_id='job-1',command='process_video',config=self.config)
    def test_valid_request_unicode_and_spaces(self):
        self.assertEqual(worker.parse_request(json.dumps(self.request))[0],self.request)
        self.assertEqual(processing.validate_config(self.config)[0],self.video)
    def test_missing_source_and_changed_source(self):
        self.video.unlink()
        with self.assertRaises(ValueError):processing.validate_config(self.config)
        self.video.write_bytes(b'changed content')
        with self.assertRaises(ValueError):processing.validate_config(self.config)
    def test_invalid_config_and_existing_workspace(self):
        for edit in ({'mode':'shell'},{'video':'relative.mp4'},{'size_bytes':True},{'extra':1}):
            with self.assertRaises(ValueError):processing.validate_config(dict(self.config,**edit))
        Path(self.config['workspace']).mkdir()
        with self.assertRaises(ValueError):processing.validate_config(self.config)
    def test_missing_dependencies_before_workspace_creation(self):
        with patch('processing.shutil.which',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'ffmpeg'):processing.run(self.config,lambda _:None)
        self.assertFalse(Path(self.config['workspace']).exists())
    def test_protocol_failure_is_not_completion(self):
        events=[]
        with patch('processing.run',side_effect=RuntimeError('export failed')),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(processing.dispatch(self.request,events.append),1)
        self.assertEqual(events[0]['event'],'failed');self.assertEqual(events[0]['artifacts'],[])
    def test_stdout_redirected_and_real_stage_order(self):
        events=[]
        def run(config,report):
            print('pipeline log')
            for stage in processing.STAGES: report(stage)
            return [{'kind':'review'}]
        with patch('processing.run',side_effect=run),contextlib.redirect_stderr(io.StringIO()) as err,contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(processing.dispatch(self.request,events.append),0)
        self.assertIn('pipeline log',err.getvalue());self.assertEqual(out.getvalue(),'')
        self.assertEqual([e['sequence'] for e in events],list(range(1,7)))
        self.assertTrue(all(e['total']==0 for e in events));self.assertEqual(events[-1]['event'],'completed')
    def test_pipeline_delegation_and_artifact_verification(self):
        paths={k:self.root/k for k in ('analysis','review','exports')}
        shorts=Mock();longs=Mock();dev=Mock()
        dev.paths_for.return_value=paths
        rows=[dict(status='exported',output_filename=f'{i}.mp4') for i in range(5)]
        shorts.export_shorts.return_value=(self.root,dict(clips=rows))
        shorts.probe_clip.return_value=dict(duration_seconds=15)
        shorts.plan_export.return_value=(self.video,self.root,dict(clips=rows))
        longs.export_longform.return_value=(self.root,dict(assembly=dict(status='complete',actual_duration_seconds=80)))
        with patch('processing.dependencies',return_value=(dev,shorts,longs)),patch('transcription.probe_media',return_value=dict(width=320,duration_seconds=80)),patch('processing.artifact',side_effect=lambda p,k,d=None:dict(path=str(p),kind=k,duration_seconds=d)),patch('tempfile.tempdir',str(self.root)):
            stages=[];result=processing.run(self.config,stages.append)
        self.assertEqual(stages,list(processing.STAGES));self.assertEqual(len(result),8)
        dev.obtain_analysis.assert_called_once();dev.publish_review.assert_called_once()
        self.assertTrue(shorts.export_shorts.call_args.kwargs['cache_only'])
        self.assertTrue(longs.export_longform.call_args.kwargs['cache_only'])
    def test_fewer_candidates_propagates_without_padding(self):
        dev=Mock(); shorts=Mock(); longs=Mock()
        dev.obtain_analysis.side_effect=ValueError('Need five valid separated candidates; found 3. No padding is permitted')
        with patch('processing.dependencies',return_value=(dev,shorts,longs)),patch('transcription.probe_media',return_value=dict(width=320,duration_seconds=10)),patch('tempfile.tempdir',str(self.root)):
            with self.assertRaisesRegex(ValueError,'five'):processing.run(self.config,lambda _:None)
        shorts.export_shorts.assert_not_called();longs.export_longform.assert_not_called()

    def test_export_failure_never_returns_artifacts(self):
        dev=Mock();shorts=Mock();dev.paths_for.return_value=dict(analysis=self.root/'analysis',exports=self.root/'exports')
        shorts.export_shorts.return_value=(self.root,dict(clips=[dict(status='failed')]))
        with patch('processing.dependencies',return_value=(dev,shorts,Mock())),patch('transcription.probe_media',return_value=dict(width=320,duration_seconds=80)),patch('tempfile.tempdir',str(self.root)):
            with self.assertRaisesRegex(RuntimeError,'Shorts export failed'):processing.run(self.config,lambda _:None)
    def test_real_worker_progress_remains_on_stdout(self):
        import subprocess, sys
        bad = dict(self.request, config={})
        result = subprocess.run([sys.executable, '-I', '-B', str(Path(worker.__file__))], input=json.dumps(bad), text=True, capture_output=True)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([e['event'] for e in events], ['started', 'failed'])
        self.assertEqual([e['sequence'] for e in events], [1, 2])
        self.assertNotEqual(result.returncode, 0)

    def test_request_id_version_and_fields_rejected(self):
        for edit in ({'protocol_version':2},{'job_id':'other'},{'unexpected':True}):
            self.assertIsNotNone(worker.parse_request(json.dumps(dict(self.request,**edit)))[1])

if __name__=='__main__':unittest.main()
