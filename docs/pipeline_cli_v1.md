# Unified Pipeline CLI V1

Run from the repository root:

    python pipeline.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json --mode both

Use --mode shorts or --mode longform for one exporter; both is the default.
Add --dry-run to preview without encoding or --force to explicitly refresh
owned generated outputs under the existing exporters' safety rules.

This thin wrapper delegates to the existing exporter CLIs. Their validation,
cache integrity checks, output layout, and overwrite protections are unchanged.
Repeated valid exports are reused; missing/incompatible analysis fails clearly.
No analysis, transcription, or models are run, and shared analysis is unchanged.

The current artifact contains five preselected Audio-only anchors, not a complete
candidate pool or fresh Audio+Scene ranking. Shorts retains its default Top-5
contract and fixed [-10,+5] windows. Long-form expands anchors by 15 seconds
on either side and merges gaps up to 5 seconds. This is a baseline assembly
policy, not a validated narrative editor. Use the individual exporter CLIs for
their additional configuration options.

Outputs remain under output/<source-stem>/shorts/ and
output/<source-stem>/longform/, including their existing manifests.
Both mode attempts each exporter independently, reports separate outcomes,
and returns a nonzero exit code if either fails (including partial failures).
Successful outputs are retained when the other exporter fails.
