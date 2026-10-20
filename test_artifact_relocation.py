"""Relocation audit: synthetic artifacts, real planning/hash/cache validation."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import export_shorts as shorts
import export_longform as longform
from shared_analysis import create_analysis, save_analysis
from windows import build_candidate_windows
from verify import snapshot


class RelocationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root/'original'
        self.repo.mkdir()
        self.video = self.repo/'game.mp4'
        self.video.write_bytes(b'synthetic source')
        self.analysis = self.repo/'analysis.json'
        self.output = self.repo/'output'
        self.probe = patch('transcription.probe_format_streams', return_value={
            'format': {'duration': '120'}, 'streams': [
                {'codec_type': 'audio'}, {'codec_type': 'video', 'width': 160,
                 'height': 90, 'avg_frame_rate': '30/1'}]})
        self.probe.start()
        self.addCleanup(self.probe.stop)
        data = create_analysis(dict(path='game.mp4', duration_seconds=120,
                                    sha256=shorts.media_sha256(self.video)))
        data['candidate_windows'] = dict(status='analyzed', provenance=dict(
            detector='Audio-only', variant='fixed', k=5, artifact='output/research.json'),
            data=build_candidate_windows([dict(second=t, score=t) for t in (15,35,55,75,95)],120))
        save_analysis(data,self.analysis)
        self.manifests = []
        for mode, planner in (('shorts',shorts.plan_export),('longform',longform.prepare_plan)):
            _, directory, manifest = planner(self.video,self.analysis,output_root=self.output)
            directory.mkdir(parents=True)
            if mode == 'shorts':
                for row in manifest['clips']:
                    target = directory/row['output_filename']
                    target.write_bytes(b'synthetic clip')
                    row.update(status='exported',output_sha256=shorts.media_sha256(target))
            else:
                target = Path(manifest['assembly']['output_path'])
                target.write_bytes(b'synthetic assembly')
                self.long_duration = manifest['planning']['estimated_duration_seconds']
                manifest['assembly'].update(status='complete',assembled_segment_count=len(manifest['segments']),
                    actual_duration_seconds=self.long_duration,output_sha256=shorts.media_sha256(target))
                for row in manifest['segments']: row['status']='assembled'
            path = directory/(mode+'_manifest.json')
            path.write_text(json.dumps(manifest),encoding='utf-8')
            self.manifests.append(path)

    def check_both(self, video=None, analysis=None, output=None, error=None):
        before = snapshot([p for p in self.root.rglob('*') if p.is_file()])
        def probe(path):
            return dict(duration_seconds=self.long_duration if Path(path).name=='longform_v1.mp4' else 15,
                        streams=[dict(codec_type='audio'),dict(codec_type='video')])
        with patch.object(shorts,'probe_clip',side_effect=probe), \
             patch('subprocess.run',side_effect=AssertionError('No external processing')), \
             patch.object(Path,'mkdir',side_effect=AssertionError('No directory creation')), \
             patch('tempfile.NamedTemporaryFile',side_effect=AssertionError('No output writes')):
            for exporter in (shorts.export_shorts,longform.export_longform):
                if error:
                    with self.assertRaisesRegex((ValueError,OSError),error):
                        exporter(video or self.video,analysis or self.analysis,
                                 output_root=output or self.output,cache_only=True)
                else:
                    _, result = exporter(video or self.video,analysis or self.analysis,
                                         output_root=output or self.output,cache_only=True)
                    if 'clips' in result:
                        self.assertTrue(all(r['status']=='reused' for r in result['clips']))
                    else: self.assertEqual(result['assembly']['status'],'reused')
        after = snapshot([p for p in self.root.rglob('*') if p.is_file()])
        self.assertEqual(before,after)

    def test_original_paths(self):
        self.check_both()

    def test_repository_copy_fails_on_source_path(self):
        destination=self.root/'copied'
        shutil.copytree(self.repo,destination)
        self.check_both(destination/'game.mp4',destination/'analysis.json',destination/'output',
                        'Cache-only stale manifest: source')

    def test_source_move_identical_bytes_planning_passes_cache_fails(self):
        destination=self.root/'moved'
        destination.mkdir()
        moved=self.video.rename(destination/'game.mp4')
        shorts.plan_export(moved,self.analysis,output_root=self.output)
        longform.prepare_plan(moved,self.analysis,output_root=self.output)
        self.check_both(video=moved,error='Cache-only stale manifest: source')

    def test_changed_source_same_path(self):
        self.video.write_bytes(b'changed source')
        self.check_both(error='Source identity mismatch')

    def test_missing_source(self):
        self.video.unlink()
        self.check_both(error='Media file not found:')

    def test_analysis_file_relocated_without_edits(self):
        moved=self.analysis.rename(self.root/'relocated_analysis.json')
        self.check_both(analysis=moved)

    def test_outputs_relocated_source_unchanged(self):
        moved=self.root/'relocated_output'
        shutil.copytree(self.output,moved)
        self.check_both(output=moved)

    def test_analysis_locator_edit_invalidates_raw_hash(self):
        data=json.loads(self.analysis.read_text())
        data['source_video']['path']='new/location/game.mp4'
        self.analysis.write_text(json.dumps(data))
        self.check_both(error='Cache-only stale shared analysis')

    def test_manifest_source_hash_mismatch(self):
        for path in self.manifests:
            data=json.loads(path.read_text())
            data['source']['sha256']='0'*64
            path.write_text(json.dumps(data))
        # Shorts checks full source first; Long-form checks ownership first.
        self.check_both(error='Cache-only stale manifest: source|Existing manifest is unrelated or invalid; refusing replacement')

    def test_manifest_analysis_hash_mismatch(self):
        for path in self.manifests:
            data=json.loads(path.read_text())
            data['shared_analysis']['sha256']='0'*64
            path.write_text(json.dumps(data))
        self.check_both(error='Cache-only stale shared analysis')


if __name__=='__main__':
    unittest.main()
