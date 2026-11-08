"""Full Blender -> bundled frozen worker -> markers, with no Adobe installation."""
import json
import os
from pathlib import Path
import sys
import bpy

ROOT = Path.cwd()
runtime_root = Path(os.environ.get('BEAT_MARKER_RUNTIME_ROOT') or (ROOT / '.build/current-runtime.txt').read_text())
sys.path.insert(0, str(runtime_root.parents[1]))
import beat_marker
from beat_marker import core, runtime

beat_marker.register()
scene = bpy.context.scene
scene.render.fps = 25
editor = scene.sequence_editor_create()
source = ROOT / '.build/integration/reference.wav'
music = editor.strips.new_sound('Generated music', str(source), channel=1, frame_start=137)
music.left_handle = 162
music.right_handle = 412
editor.active_strip = music
scene.timeline_markers.new('Manual marker stays', frame=170)
before_files = set(runtime_root.rglob('*'))
result = bpy.ops.beat_marker.analyse('EXEC_DEFAULT')
assert result == {'FINISHED'}, scene.name + ': ' + bpy.context.window_manager.beat_marker_status
assert music.get(core.DATA), 'Full-source beat map was not retained'
owned = core.registry(scene)[music[core.OWNER]]['markers']
assert len(owned) >= 4, 'No useful beats were returned to Blender'
assert all(music.left_handle <= row['frame'] < music.right_handle for row in owned)
assert scene.timeline_markers['Manual marker stays'].frame == 170
old = [row['frame'] for row in owned]
music.content_start += 75
bpy.ops.beat_marker.update_markers('EXEC_DEFAULT')
assert [row['frame'] for row in core.registry(scene)[music[core.OWNER]]['markers']] == [frame+75 for frame in old]
assert set(runtime_root.rglob('*')) == before_files, 'Analysis wrote into the installed runtime'
assert list((beat_marker.data_directory() / 'cache').glob('*.json'))
(ROOT / '.build/integration/engine-verification.json').write_text(json.dumps({'passed': True, 'blender': bpy.app.version_string, 'platform': runtime.platform_key(), 'markers': len(owned), 'source_offset_frames': 25, 'timeline_start': 137, 'marker_move_frames': 75, 'manual_markers_preserved': True}, indent=2))
print('BLENDER_BUNDLED_ENGINE_PASSED', len(owned), 'markers')
