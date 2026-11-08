"""Native Sequencer controls and a read-only alignment preview overlay."""
import json
import textwrap

import bpy
from bpy.types import Operator, Panel
from . import core, alignment

_previews = {}
_channel_items = {}
_handler = None


def scene_for(context):
    return context.sequencer_scene if context.area and context.area.type == 'SEQUENCE_EDITOR' else context.scene


def channels(self, context):
    # Enum callbacks also run from timers, where context.scene may be the 3D
    # scene rather than the scene displayed in the Sequencer.
    scene = self.id_data if isinstance(self.id_data, bpy.types.Scene) else scene_for(context)
    numbers = sorted({s.channel for s in core.strips(scene) if s.type == 'MOVIE'}) if scene else []
    key = tuple(numbers)
    if key not in _channel_items:
        _channel_items[key] = [('SELECTED', 'Selected video clips', 'Fit selected movie clips and their connected audio', 0)] + [
            ('CHANNEL_' + str(n), 'All clips on Channel ' + str(n), 'Fit every movie clip on this channel', n) for n in numbers]
    return _channel_items[key]


def setup_probe(context):
    from . import engine_directory
    from . import runtime
    _, paths = runtime.validate(engine_directory(context))
    alignment.set_probe(paths['ffmpeg'])


def refresh(scene):
    record = _previews.get(scene.as_pointer())
    if not record:
        return
    options = alignment.settings(scene)
    current = alignment.signature(scene, options)
    if current == record.get('signature'):
        return
    try:
        plan = alignment.make_plan(scene, options)
        _previews[scene.as_pointer()] = {'signature': current, 'plan': plan}
    except Exception as exc:
        _previews[scene.as_pointer()] = {'signature': current, 'error': str(exc)}


def tick():
    if not hasattr(bpy.types.Scene, 'beat_marker'):
        return None
    scenes = {scene.as_pointer(): scene for scene in bpy.data.scenes}
    for pointer in list(_previews):
        if pointer not in scenes:
            del _previews[pointer]
        else:
            try:
                refresh(scenes[pointer])
            except Exception as exc:
                _previews[pointer] = {'error': str(exc)}
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                area.tag_redraw()
    return .8


def clear():
    _previews.clear()


def busy():
    from . import _job
    return _job is not None


def message(context, text):
    context.window_manager.beat_marker_status = text


class BM_OT_preview_alignment(Operator):
    bl_idname = 'beat_marker.preview_alignment'
    bl_label = 'Preview alignment'
    bl_description = 'Preview beat-aligned clip edges without changing clips; updates automatically as the timeline changes'

    @classmethod
    def poll(cls, context):
        return scene_for(context) is not None and not busy()

    def execute(self, context):
        scene = scene_for(context)
        try:
            setup_probe(context)
            plan = alignment.make_plan(scene)
            _previews[scene.as_pointer()] = {'signature': plan['signature'], 'plan': plan}
            if context.area:
                context.area.tag_redraw()
            return {'FINISHED'}
        except Exception as exc:
            _previews[scene.as_pointer()] = {'error': str(exc)}
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def invoke(self, context, event):
        return self.execute(context)


class BM_OT_apply_alignment(Operator):
    bl_idname = 'beat_marker.apply_alignment'
    bl_label = 'Apply alignment'
    bl_description = 'Apply the preview, including connected audio and marker refresh, as one native Undo operation'
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        scene = scene_for(context)
        record = _previews.get(scene.as_pointer(), {}) if scene else {}
        return bool(record.get('plan', {}).get('changes')) and not busy()

    def execute(self, context):
        scene = scene_for(context)
        try:
            record = _previews.get(scene.as_pointer(), {})
            if not record.get('plan'):
                raise ValueError('Preview the alignment first.')
            result = alignment.apply_plan(scene, record['plan'])
            _previews.pop(scene.as_pointer(), None)
            text = str(result['changed']) + ' clips changed · ' + str(result['skipped']) + ' skipped'
            message(context, text)
            self.report({'INFO'}, text)
            return {'FINISHED'}
        except Exception as exc:
            message(context, str(exc))
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class BM_OT_clear_preview(Operator):
    bl_idname = 'beat_marker.clear_alignment_preview'
    bl_label = 'Hide preview'
    bl_description = 'Hide the proposed edit edges without changing the timeline'

    def execute(self, context):
        scene = scene_for(context)
        if scene:
            _previews.pop(scene.as_pointer(), None)
        return {'FINISHED'}


def label_wrapped(layout, text, width):
    for line in textwrap.wrap(text, max(20, int(width / 7.5))):
        layout.label(text=line)


class BM_PT_alignment(Panel):
    bl_label = 'Align edits to markers'
    bl_idname = 'BM_PT_alignment'
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Beat Marker'

    def draw(self, context):
        layout = self.layout
        scene = scene_for(context)
        if not scene:
            layout.label(text='Choose a Sequencer scene first', icon='INFO')
            return
        settings = scene.beat_marker
        layout.prop(settings, 'align_scope', text='')
        movies = [s for s in core.strips(scene) if s.type == 'MOVIE' and
            ((settings.align_scope == 'SELECTED' and s.select) or settings.align_scope == 'CHANNEL_' + str(s.channel))]
        layout.label(text=str(len(movies)) + (' clip' if len(movies) == 1 else ' clips'))
        layout.prop(settings, 'align_length', text='Clip length')
        row = layout.row(align=True)
        row.label(text='Source anchor')
        row.prop(settings, 'align_anchor', text='')
        layout.prop(settings, 'align_threshold', text='Threshold · frames')
        layout.prop(settings, 'align_ripple')
        row = layout.row(align=True)
        # Use the panel's scene context instead of rebinding the operator to a
        # different region in the split Sequencer/Preview editor.
        row.operator_context = 'EXEC_DEFAULT'
        row.operator('beat_marker.preview_alignment', icon='VIEWZOOM')
        row.operator('beat_marker.apply_alignment', icon='CHECKMARK')
        record = _previews.get(scene.as_pointer())
        if record:
            if record.get('error'):
                label_wrapped(layout, record['error'], context.region.width)
            else:
                plan = record['plan']
                summary = plan['summary']
                box = layout.box()
                if plan['changes']:
                    box.label(text='Preview · ' + str(summary['changed']) + ' clips will change', icon='VIEWZOOM')
                    box.label(text='Press Apply to change the clips')
                elif summary['aligned'] == summary['targets']:
                    box.label(text='All ' + str(summary['targets']) + ' clips are already aligned', icon='CHECKMARK')
                else:
                    box.label(text='No compatible edits found', icon='INFO')
                if summary['ripple']:
                    box.label(text=str(summary['ripple']) + ' following clips move with ripple')
                if summary['skipped']:
                    box.label(text=str(summary['skipped']) + ' skipped · expand Each clip for reasons', icon='INFO')
                box.prop(settings, 'align_details', text='Each clip', icon='TRIA_DOWN' if settings.align_details else 'TRIA_RIGHT', emboss=False)
                if settings.align_details:
                    for item in plan['preview']:
                        column = box.column(align=True)
                        column.label(text=item['name'])
                        before, after = item['before'], item['after']
                        if after['aligned']:
                            column.label(text=str(before['start']) + '–' + str(before['end']) + ' → ' + str(after['start']) + '–' + str(after['end']))
                            if abs(before['speed'] - after['speed']) > 1e-5:
                                column.label(text='Speed: ' + format(after['speed'] * 100, '.2f') + '%')
                            elif not item['changed']:
                                column.label(text='Already on beats')
                        elif item['changed']:
                            column.label(text='Moves with ripple')
                        else:
                            label_wrapped(column, item['reason'], context.region.width - 40)
                        box.separator(factor=.5)
                box.operator_context = 'EXEC_DEFAULT'
                box.operator('beat_marker.clear_alignment_preview', icon='HIDE_ON')
        row = layout.row()
        row.alignment = 'RIGHT'
        row.label(text='v0.3.0')


def draw_overlay():
    context = bpy.context
    if not context.area or context.area.type != 'SEQUENCE_EDITOR' or context.region.type != 'WINDOW':
        return
    if context.space_data.view_type == 'PREVIEW':
        return
    scene = context.sequencer_scene
    record = _previews.get(scene.as_pointer(), {}) if scene else {}
    plan = record.get('plan')
    if not plan:
        return
    import gpu
    import blf
    from gpu_extras.batch import batch_for_shader
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    view = context.region.view2d
    gpu.state.blend_set('ALPHA')
    try:
        for item in plan['preview']:
            if not item['changed'] and not item['after']['aligned']:
                continue
            # Font drawing changes the GPU blend state on some platforms.
            gpu.state.blend_set('ALPHA')
            after, channel = item['after'], item['channel']
            left, bottom = view.view_to_region(after['start'], channel + .12, clip=False)
            right, top = view.view_to_region(after['end'], channel + .88, clip=False)
            color = (.2, .82, .9, .12) if after['aligned'] else (.78, .4, .7, .16)
            shader.bind()
            shader.uniform_float('color', color)
            batch_for_shader(shader, 'TRIS', {'pos': [(left, bottom), (right, bottom), (right, top), (left, top)]}, indices=[(0, 1, 2), (0, 2, 3)]).draw(shader)
            shader.uniform_float('color', (.98, .35, .77, 1) if item['changed'] else (.25, .9, .98, 1))
            # Filled edge rectangles avoid platform-specific GPU line widths.
            for edge in (left, right):
                batch_for_shader(shader, 'TRIS', {'pos': [(edge - 2, bottom), (edge + 2, bottom), (edge + 2, top), (edge - 2, top)]}, indices=[(0, 1, 2), (0, 2, 3)]).draw(shader)
            batch_for_shader(shader, 'TRIS', {'pos': [(left, top - 4), (right, top - 4), (right, top), (left, top)]}, indices=[(0, 1, 2), (0, 2, 3)]).draw(shader)
            if 0 <= left < context.region.width and 0 <= top < context.region.height:
                label = 'Preview' if item['changed'] else 'On beat'
                font_size = 13 * context.preferences.system.ui_scale
                blf.size(0, font_size)
                width, height = blf.dimensions(0, label)
                shader.uniform_float('color', (.025, .04, .055, .9))
                batch_for_shader(shader, 'TRIS', {'pos': [(left + 4, top - height - 14), (left + width + 14, top - height - 14), (left + width + 14, top - 5), (left + 4, top - 5)]}, indices=[(0, 1, 2), (0, 2, 3)]).draw(shader)
                blf.color(0, .55, .93, .98, 1)
                blf.position(0, left + 9, top - height - 10, 0)
                blf.draw(0, label)
    finally:
        gpu.state.blend_set('NONE')


CLASSES = (BM_OT_preview_alignment, BM_OT_apply_alignment, BM_OT_clear_preview, BM_PT_alignment)


def register():
    global _handler
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    _handler = bpy.types.SpaceSequenceEditor.draw_handler_add(draw_overlay, (), 'WINDOW', 'POST_PIXEL')
    bpy.app.timers.register(tick, first_interval=.8, persistent=True)


def unregister():
    global _handler
    clear()
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    if _handler is not None:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(_handler, 'WINDOW')
        _handler = None
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
