"""Beat Marker: local beat analysis and refreshable music markers for Blender."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, BoolVectorProperty, EnumProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup

from . import core, alignment, alignment_ui, runtime

_job = None


def redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                area.tag_redraw()


def status(text):
    bpy.context.window_manager.beat_marker_status = text
    redraw()


def scene_for(context):
    if context.area and context.area.type == 'SEQUENCE_EDITOR':
        return context.sequencer_scene
    return context.scene


def data_directory():
    try:
        return Path(bpy.utils.extension_path_user(__package__, path='analysis', create=True))
    except (RuntimeError, ValueError):
        # Also supports running the source checkout in Blender's test runner.
        return Path(bpy.utils.user_resource('CONFIG', path='beat_marker/analysis', create=True))


def engine_directory(context=None):
    return runtime.prepare(data_directory())[0]


def command(context, source, output, timing):
    root, paths = runtime.prepare(data_directory())
    return [str(paths['engine']), '--resources', str(root), '--data-dir', str(data_directory()),
            '--source', source, '--output', str(output), '--timing', timing]


def selected_music(context):
    found = [strip for strip in core.strips(scene_for(context)) if strip.type == 'SOUND' and strip.select]
    if len(found) != 1:
        raise ValueError("Select one music sound strip in the Video Sequencer.")
    core.validate_strip(scene_for(context), found[0])
    return found[0]


class BMPreferences(AddonPreferences):
    bl_idname = __package__
    def draw(self, context):
        self.layout.label(text='Beat Marker ' + runtime.VERSION)
        self.layout.label(text='Analysis engine included · audio stays on this computer')
        try:
            runtime.validate(Path(__file__).resolve().parent / 'runtime')
            self.layout.label(text='Bundled engine: ' + runtime.platform_key(), icon='CHECKMARK')
        except ValueError as exc:
            self.layout.label(text=str(exc), icon='ERROR')


class BMSettings(PropertyGroup):
    timing: EnumProperty(name="Timing", items=[
        ('auto', 'Auto · recover a consistent pulse', 'Recover sparse intros when later beats support a consistent pulse'),
        ('detected', 'Original model detections', 'Use the original model predictions without recovery'),
        ('steady', 'Use a steady beat grid', 'Extend a reference pulse; use only for music with a steady tempo')], default='auto')
    beat_filter: EnumProperty(name="Beats to mark", items=[
        ('ALL', 'Every beat', 'Create a marker for each detected or recovered beat'),
        ('1', 'Bar starts', 'Mark beat one of each estimated bar'),
        *[(str(n), 'Beat ' + str(n), 'Mark estimated beat ' + str(n) + ' in each bar') for n in range(2, 9)]], default='ALL', options={'HIDDEN'})
    beat_checks: BoolVectorProperty(name='Beats to mark', size=core.MAX_BEATS,
        description='Include this beat when adding or updating markers; click Update marker times to apply',
        get=core.beat_checks, set=core.set_beat_checks)
    align_scope: EnumProperty(name='Clips', items=alignment_ui.channels)
    align_length: EnumProperty(name='Clip length', items=[
        ('both', 'Extend / reduce', 'Change source trims while keeping playback speed'),
        ('extend', 'Extend only', 'Allow a longer duration or movement at the same duration'),
        ('reduce', 'Reduce only', 'Allow a shorter duration or movement at the same duration')], default='both')
    align_anchor: EnumProperty(name='Source anchor', items=[
        ('start', 'Use start', 'Keep the source start when trimming and favour the nearest start beat'),
        ('middle', 'Use midpoint', 'Trim around the source centre and favour the nearest beat-pair centre'),
        ('end', 'Use end', 'Keep the source end when trimming and favour the nearest end beat')], default='start')
    align_threshold: IntProperty(name='Threshold · frames', description='Maximum distance each edge may move to reach a beat; measured after earlier ripple shifts', default=30, min=0, max=10000)
    align_ripple: BoolProperty(name='Ripple following clips', description='Carry changes through later clips on the chosen video channels, preserving gaps and moving their connected audio')
    align_details: BoolProperty(name='Each clip', default=False)


class BM_OT_commit(Operator):
    bl_idname = 'beat_marker.commit_analysis'
    bl_label = 'Analyse music and add beat markers'
    bl_options = {'INTERNAL'}
    payload: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        try:
            job = json.loads(self.payload)
            if scene_for(context).as_pointer() != job['scene_pointer']:
                raise ValueError("The scene changed during analysis. Return to the music scene and analyse again.")
            strip = next((s for s in core.strips(scene_for(context)) if s.as_pointer() == job['strip_pointer']), None)
            if not strip:
                raise ValueError("The analysed music strip was removed. No markers were added.")
            result = json.loads(Path(job['output']).read_text())
            count = core.import_analysis(scene_for(context), strip, result, job['source_stamp'], job['timing'], core.beat_filter(scene_for(context)))
            status(str(count) + ' beat markers added. Ctrl/Cmd+Z undoes this change.')
            self.report({'INFO'}, str(count) + ' beat markers added')
            return {'FINISHED'}
        except Exception as exc:
            status(str(exc))
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


def start_job(context):
    global _job
    if _job:
        raise ValueError("Analysis is already running.")
    strip = selected_music(context)
    source = core.source_path(strip)
    source_stamp = core.stamp(source)
    folder = Path(tempfile.mkdtemp(prefix='beat-marker-blender-'))
    output = folder / 'result.json'
    log = folder / 'progress.txt'
    try:
        args = command(context, source, output, scene_for(context).beat_marker.timing)
        handle = log.open('w', encoding='utf-8')
        try:
            process = subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                env=runtime.process_environment(),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        finally:
            handle.close()
    except Exception:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        raise
    _job = {'process': process, 'folder': folder, 'log': log, 'started': time.monotonic(),
            'output': str(output), 'scene_pointer': scene_for(context).as_pointer(),
            'strip_pointer': strip.as_pointer(), 'source_stamp': source_stamp,
            'timing': scene_for(context).beat_marker.timing, 'name': strip.name}
    status('Analysing “' + strip.name + '”…')
    return _job


def finish_job(context):
    job = _job
    if job['process'].returncode != 0:
        log = job['log'].read_text(errors='replace')
        lines = [line.strip() for line in log.splitlines() if line.strip()]
        raise ValueError('Analysis failed: ' + (lines[-1][-300:] if lines else 'the local analyser stopped.'))
    payload = {key: job[key] for key in ('output', 'scene_pointer', 'strip_pointer', 'source_stamp', 'timing')}
    return bpy.ops.beat_marker.commit_analysis('EXEC_DEFAULT', payload=core.dumps(payload))


def cleanup_job():
    global _job
    if _job:
        import shutil
        process = _job['process']
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        shutil.rmtree(_job['folder'], ignore_errors=True)
    _job = None


class BM_OT_analyse(Operator):
    bl_idname = 'beat_marker.analyse'
    bl_label = 'Analyse selected music'
    bl_description = 'Find beats locally and create markers for one selected music strip; no audio is uploaded'
    bl_options = {'REGISTER', 'UNDO'}
    _timer = None

    @classmethod
    def poll(cls, context):
        return scene_for(context) is not None and _job is None

    def execute(self, context):
        if not bpy.app.background:
            return self.invoke(context, None)
        try:
            job = start_job(context)
            job['process'].wait(timeout=600)
            return finish_job(context)
        except Exception as exc:
            status(str(exc))
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        finally:
            cleanup_job()

    def invoke(self, context, event):
        try:
            start_job(context)
            self._timer = context.window_manager.event_timer_add(0.4, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        except Exception as exc:
            cleanup_job()
            status(str(exc))
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def modal(self, context, event):
        if _job is None:
            self.stop(context)
            return {'CANCELLED'}
        if event.type == 'ESC':
            self.stop(context)
            status('Analysis cancelled. No markers changed.')
            return {'CANCELLED'}
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        if time.monotonic() - _job['started'] > 600:
            self.stop(context)
            status('Analysis timed out. Try a shorter source file.')
            return {'CANCELLED'}
        if _job['process'].poll() is None:
            try:
                lines = _job['log'].read_text(errors='replace').splitlines()
                if lines:
                    status(lines[-1][-160:])
            except OSError:
                pass
            return {'PASS_THROUGH'}
        try:
            result = finish_job(context)
        except Exception as exc:
            status(str(exc))
            self.report({'ERROR'}, str(exc))
            result = {'CANCELLED'}
        self.stop(context)
        return result

    def stop(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        cleanup_job()

    def cancel(self, context):
        self.stop(context)


class BM_OT_update(Operator):
    bl_idname = 'beat_marker.update_markers'
    bl_label = 'Update marker times'
    bl_description = 'Refresh all analysed music in this scene after moves, trims or frame-rate changes, without analysing again'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _job is None and scene_for(context) is not None

    def execute(self, context):
        try:
            count = core.update_all(scene_for(context), core.beat_filter(scene_for(context)))
            status(str(count) + ' beat markers updated.')
            self.report({'INFO'}, str(count) + ' beat markers updated')
            return {'FINISHED'}
        except Exception as exc:
            status(str(exc))
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class BM_OT_remove(Operator):
    bl_idname = 'beat_marker.remove_markers'
    bl_label = 'Remove from Selected'
    bl_description = 'Remove only this tool’s beat markers belonging to selected music strips'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _job is None and scene_for(context) is not None

    def execute(self, context):
        try:
            count = core.remove_selected(scene_for(context))
            status(str(count) + ' beat markers removed.')
            self.report({'INFO'}, str(count) + ' beat markers removed')
            return {'FINISHED'}
        except Exception as exc:
            status(str(exc))
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class BM_PT_music(Panel):
    bl_label = 'Music clip'
    bl_idname = 'BM_PT_music'
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Beat Marker'

    def draw(self, context):
        layout = self.layout
        if scene_for(context) is None:
            layout.label(text='Choose a scene in the Sequencer header', icon='INFO')
            return
        settings = scene_for(context).beat_marker
        sounds = [s for s in core.strips(scene_for(context)) if s.type == 'SOUND' and s.select]
        if len(sounds) == 1:
            strip = sounds[0]
            layout.label(text=strip.name, icon='SOUND')
            rate = core.fps(scene_for(context))
            layout.label(text='Timeline start: ' + bpy.utils.smpte_from_frame(strip.left_handle, fps=rate, fps_base=1.0))
            try:
                origin, left, right, rate = core.mapping(scene_for(context), strip)
                layout.label(text='Source start: ' + format(max(0, (left - origin) / rate), '.3f') + ' s')
            except ValueError as exc:
                layout.label(text=str(exc), icon='INFO')
        else:
            layout.label(text='Select one music strip', icon='SOUND')
        layout.prop(settings, 'timing', text='')
        row = layout.row()
        row.operator_context = 'INVOKE_DEFAULT'
        row.enabled = len(sounds) == 1 and _job is None
        row.operator('beat_marker.analyse', icon='PLAY_SOUND')
        if _job:
            layout.label(text='Analysing locally · Esc to cancel', icon='TIME')


class BM_PT_markers(Panel):
    bl_label = 'Markers'
    bl_idname = 'BM_PT_markers'
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Beat Marker'

    def draw(self, context):
        layout = self.layout
        if scene_for(context) is None:
            layout.label(text='Choose a scene in the Sequencer header', icon='INFO')
            return
        scene = scene_for(context)
        settings = scene.beat_marker
        beats, meters = core.available_beats(scene)
        if beats:
            layout.label(text='Beats to mark · ' + ' / '.join(str(n) for n in meters) + ' per bar')
            grid = layout.grid_flow(columns=min(4, len(beats)), row_major=True, even_columns=True, even_rows=True, align=True)
            for number in beats:
                grid.prop(settings, 'beat_checks', index=number - 1, text='Beat ' + str(number))
            if not any(settings.beat_checks[n - 1] for n in beats):
                layout.label(text='No beats selected', icon='INFO')
        else:
            layout.label(text='Analyse music to choose beats', icon='INFO')
        column = layout.column(align=True)
        column.operator_context = 'EXEC_DEFAULT'
        column.scale_y = 1.25
        column.operator('beat_marker.update_markers', icon='FILE_REFRESH')
        column.operator('beat_marker.remove_markers', icon='TRASH')
        try:
            if core.is_stale(scene, core.beat_filter(scene)):
                layout.label(text='Changes pending · update marker times', icon='INFO')
        except Exception:
            pass
        message = context.window_manager.beat_marker_status
        if message:
            import textwrap
            for line in textwrap.wrap(message, max(22, int(context.region.width / 7.5))):
                layout.label(text=line)


@persistent
def before_load(_):
    cleanup_job()
    alignment_ui.clear()


CLASSES = (BMPreferences, BMSettings, BM_OT_commit, BM_OT_analyse, BM_OT_update, BM_OT_remove, BM_PT_music, BM_PT_markers)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.beat_marker = PointerProperty(type=BMSettings)
    bpy.types.WindowManager.beat_marker_status = StringProperty(options={'SKIP_SAVE'})
    bpy.app.handlers.load_pre.append(before_load)
    alignment_ui.register()


def unregister():
    cleanup_job()
    alignment_ui.unregister()
    if before_load in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(before_load)
    del bpy.types.Scene.beat_marker
    del bpy.types.WindowManager.beat_marker_status
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
