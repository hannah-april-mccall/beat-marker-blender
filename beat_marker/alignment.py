"""Frame-based edit planning and transactional native Blender strip edits."""
import bisect
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

import bpy
from . import core

EPS = 1e-5
_media = {}
_probe = None


def set_probe(ffmpeg):
    global _probe
    executable = Path(ffmpeg).expanduser()
    sibling = executable.parent / ('ffprobe.exe' if os.name == 'nt' else 'ffprobe')
    _probe = str(sibling) if sibling.is_file() else shutil.which('ffprobe')


def media_path(strip):
    if strip.type == 'MOVIE':
        return str(Path(bpy.path.abspath(strip.filepath)).resolve())
    if strip.type == 'SOUND':
        return core.source_path(strip)
    return ''


def media_info(strip):
    path = media_path(strip)
    stat = core.stamp(path)
    key = (path, stat['size'], stat['mtime'], strip.type)
    if key in _media:
        return _media[key]
    probe = _probe or shutil.which('ffprobe')
    if not probe:
        raise ValueError('FFprobe is missing. Check the local analysis engine installation.')
    selector = 'v:0' if strip.type == 'MOVIE' else 'a:0'
    result = subprocess.run([probe, '-v', 'error', '-select_streams', selector,
        '-show_entries', 'stream=duration,nb_frames,avg_frame_rate,r_frame_rate:format=duration',
        '-of', 'json', path], capture_output=True, text=True, timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise ValueError('Cannot read source media: ' + Path(path).name)
    metadata = json.loads(result.stdout)
    streams = metadata.get('streams', [])
    if not streams:
        raise ValueError('The source media has no usable ' + selector[0] + ' stream.')
    stream = streams[0]
    duration = float(stream.get('duration', metadata.get('format', {}).get('duration', 0)))
    if strip.type == 'MOVIE':
        rate = float(strip.fps)
        count = stream.get('nb_frames')
        count = int(count) if count and count != 'N/A' else round(duration * rate)
        duration = count / rate
    else:
        rate = None
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('The source duration is unavailable.')
    value = {'duration': duration, 'fps': rate, 'stamp': stat}
    _media[key] = value
    return value


def key_frames(strip):
    # This version leaves every existing retiming curve untouched.
    return len(strip.retiming_keys) if hasattr(strip, 'retiming_keys') else 0


def locked(scene, strip):
    channels = scene.sequence_editor.channels
    channel = next((c for c in channels if c.number == strip.channel), None)
    return bool(strip.lock or (channel and channel.lock))


def curve(scene, strip):
    if len(strip.retiming_keys):
        raise ValueError('Retimed clips are skipped in this version.')
    info = media_info(strip)
    units = info['fps'] if strip.type == 'MOVIE' else core.fps(scene)
    source_start = strip.content_trim_start / units
    source_end = info['duration'] - strip.content_trim_end / units
    audio_offset = float(strip.sound_offset) if strip.type == 'SOUND' else 0.0
    source_start -= audio_offset
    source_end -= audio_offset
    points = [[0.0, source_start], [float(strip.content_duration), source_end]]
    if points[-1][0] <= 0 or source_end <= source_start:
        raise ValueError('This clip has no usable source range.')
    return points, info


def at(points, frame):
    index = max(0, min(len(points) - 2, bisect.bisect_right([p[0] for p in points], frame) - 1))
    a, b = points[index:index + 2]
    return a[1] + (frame - a[0]) * (b[1] - a[1]) / (b[0] - a[0])


def read_strip(scene, strip):
    if strip.type not in {'MOVIE', 'SOUND'}:
        raise ValueError('Use movie clips with normal, forward playback.')
    if strip.type == 'MOVIE' and (strip.use_reverse_frames or strip.stream_index != 0):
        raise ValueError('Reversed clips and alternate video streams are not supported.')
    if strip.get(core.DATA):
        raise ValueError('The music reference stays fixed.')
    if locked(scene, strip):
        raise ValueError('The strip or its channel is locked.')
    points, info = curve(scene, strip)
    origin = float(strip.content_start)
    left, right = strip.left_handle - origin, strip.right_handle - origin
    if left < points[0][0] - EPS or right > points[-1][0] + EPS or right <= left:
        raise ValueError('The clip extends outside its source media.')
    middle = (left + right) / 2
    index = max(0, min(len(points) - 2, bisect.bisect_right([p[0] for p in points], middle) - 1))
    slopes = [(b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(points, points[1:])]
    slope = slopes[index]
    for i, (a, b) in enumerate(zip(points, points[1:])):
        if b[0] > left + EPS and a[0] < right - EPS and abs(slopes[i] - slope) > 1e-7:
            raise ValueError('Variable speed within the visible clip is not supported.')
    if slope <= 0:
        raise ValueError('Freeze frames and reverse playback are not supported.')
    lo, hi = index, index
    while lo and abs(slopes[lo - 1] - slope) < 1e-7:
        lo -= 1
    while hi < len(slopes) - 1 and abs(slopes[hi + 1] - slope) < 1e-7:
        hi += 1
    return {'name': strip.name, 'pointer': strip.as_pointer(), 'channel': strip.channel,
            'type': strip.type, 'start': strip.left_handle, 'end': strip.right_handle,
            'origin': origin, 'in': at(points, left), 'out': at(points, right),
            'speed': slope * core.fps(scene), 'slope': slope, 'points': points,
            'min_source': points[lo][1], 'max_source': points[hi + 1][1],
            'media': info, 'selected': strip.select}


def has_animation(scene, strip):
    animation = scene.animation_data
    if not animation:
        return False
    prefixes = [strip.path_from_id(), 'sequence_editor.strips_all[' + json.dumps(strip.name) + ']']
    paths = [driver.data_path for driver in animation.drivers]
    action = animation.action
    if action:
        # Blender 5.x actions use channel bags instead of action.fcurves.
        for layer in action.layers:
            for action_strip in layer.strips:
                for bag in getattr(action_strip, 'channelbags', []):
                    paths.extend(f.data_path for f in bag.fcurves)
    return any(any(path.startswith(prefix) for prefix in prefixes) for path in paths)


def settings(scene):
    s = scene.beat_marker
    return {'scope': s.align_scope, 'trim': s.align_length, 'anchor': s.align_anchor,
            'threshold': s.align_threshold, 'ripple': s.align_ripple, 'filter': core.beat_filter(scene)}


def signature(scene, options):
    strips = []
    for strip in core.strips(scene):
        path = media_path(strip)
        try:
            stamp = core.stamp(path) if path else None
        except OSError:
            stamp = None
        strips.append({'pointer': strip.as_pointer(), 'name': strip.name, 'type': strip.type,
            'start': strip.content_start, 'left': strip.left_handle, 'right': strip.right_handle,
            'channel': strip.channel, 'selected': strip.select, 'lock': locked(scene, strip),
            'keys': key_frames(strip), 'trim': [getattr(strip, 'content_trim_start', 0), getattr(strip, 'content_trim_end', 0)],
            'audio_offset': getattr(strip, 'sound_offset', 0), 'reverse': getattr(strip, 'use_reverse_frames', False),
            'connections': sorted(s.as_pointer() for s in strip.connections), 'path': path, 'stamp': stamp,
            'analysis': strip.get(core.DATA), 'enabled': strip.get(core.ENABLED), 
            'animation': has_animation(scene, strip),
            'inputs': [getattr(strip, k).as_pointer() for k in ('input_1', 'input_2') if getattr(strip, k, None)]})
    payload = [scene.as_pointer(), core.fps(scene), options, strips,
               [(m.name, m.frame, bool(m.camera)) for m in scene.timeline_markers], scene.get(core.REGISTRY)]
    return hashlib.sha256(core.dumps(payload).encode()).hexdigest()


def beat_frames(scene, options):
    frames = set()
    for strip in core.strips(scene):
        if strip.type == 'SOUND' and strip.get(core.DATA) and strip.get(core.ENABLED, True):
            frames.update(row['frame'] for row in core.rows_for_strip(scene, strip, core.analysis(strip), options['filter']))
    if len(frames) < 2:
        raise ValueError('Analyse music and enable at least two beat markers first.')
    core.owned_markers(scene, core.registry(scene))
    return sorted(frames)


def capture(scene, options):
    all_strips = core.strips(scene)
    dependencies = {getattr(s, k).as_pointer() for s in all_strips for k in ('input_1', 'input_2') if getattr(s, k, None)}
    videos = [s for s in all_strips if s.type == 'MOVIE']
    targets = {s.as_pointer() for s in videos if
               (options['scope'] == 'SELECTED' and s.select) or options['scope'] == 'CHANNEL_' + str(s.channel)}
    if not targets:
        raise ValueError('Select video clips or choose a channel containing movie clips.')
    rows = []
    for strip in all_strips:
        row = {'pointer': strip.as_pointer(), 'name': strip.name, 'type': strip.type,
               'channel': strip.channel, 'start': strip.left_handle, 'end': strip.right_handle,
               'target': strip.as_pointer() in targets, 'reason': None, 'linked': []}
        if strip.type == 'MOVIE':
            try:
                if strip.as_pointer() in dependencies:
                    raise ValueError('This clip has a transition or dependent effect.')
                if has_animation(scene, strip):
                    raise ValueError('Keyframed strips are not supported in this version.')
                row.update(read_strip(scene, strip))
                for connected in strip.connections:
                    if connected.type != 'SOUND' or connected not in all_strips:
                        raise ValueError('The clip has a connection to another video, effect or meta strip.')
                    if connected.as_pointer() in dependencies or has_animation(scene, connected):
                        raise ValueError('Connected audio has an effect or animation.')
                    if any(member != strip and member != connected for member in connected.connections):
                        raise ValueError('Connected audio is shared by another clip.')
                    member = read_strip(scene, connected)
                    if (member['start'] != row['start'] or member['end'] != row['end'] or
                        abs(member['in'] - row['in']) > .5 / core.fps(scene) or
                        abs(member['out'] - row['out']) > .5 / core.fps(scene) or
                        abs(member['speed'] - row['speed']) > 1e-5):
                        raise ValueError('Connected audio has different timing, trims or speed.')
                    row['linked'].append(member)
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                row['reason'] = str(exc)
        else:
            row['reason'] = 'This strip stays fixed.'
        rows.append(row)
    return rows


def candidates(clip, beats, ref_start, ref_end, options, fps, forced=None):
    threshold = options['threshold']
    starts = beats[bisect.bisect_left(beats, ref_start - threshold):bisect.bisect_right(beats, ref_start + threshold)]
    ends = beats[bisect.bisect_left(beats, ref_end - threshold):bisect.bisect_right(beats, ref_end + threshold)]
    old_duration = clip['end'] - clip['start']
    result = []
    for start in starts:
        if forced is not None and start != forced:
            continue
        for end in ends:
            duration = end - start
            if duration < 1 or start < -1048574 or end > 1048574:
                continue
            if options['trim'] == 'extend' and duration < old_duration:
                continue
            if options['trim'] == 'reduce' and duration > old_duration:
                continue
            delta = old_duration - duration
            head = 0 if options['anchor'] == 'start' else delta if options['anchor'] == 'end' else math.floor(delta / 2 + .5)
            source_in = clip['in'] + head * clip['slope']
            source_out = source_in + duration * clip['slope']
            speed = clip['speed']
            if not .01 - EPS <= speed <= 100 + EPS:
                continue
            if any(source_in < member['min_source'] - EPS or source_out > member['max_source'] + EPS
                   for member in [clip] + clip['linked']):
                continue
            left, right = abs(start - ref_start), abs(end - ref_end)
            if options['anchor'] == 'start':
                cost = left * 1000 + right
            elif options['anchor'] == 'end':
                cost = right * 1000 + left
            else:
                cost = abs(start + end - ref_start - ref_end) * 500 + abs(duration - old_duration)
            result.append({'start': start, 'end': end, 'in': source_in, 'out': source_out,
                           'speed': speed, 'aligned': True, 'cost': cost})
    return sorted(result, key=lambda r: (r['cost'], r['start'], r['end']))


def fallback(clip, shift=0):
    return {'start': clip['start'] + shift, 'end': clip['end'] + shift, 'in': clip.get('in'),
            'out': clip.get('out'), 'speed': clip.get('speed'), 'aligned': False, 'cost': 0}


def plan_channel(clips, beats, options, fps):
    if options['ripple']:
        path, offset, previous = [], 0, None
        for index, clip in enumerate(clips):
            start, end = clip['start'] + offset, clip['end'] + offset
            forced = previous['end'] if index and clips[index - 1]['end'] == clip['start'] else None
            choices = candidates(clip, beats, start, end, options, fps, forced) if clip['target'] and not clip['reason'] else []
            choices = [r for r in choices if previous is None or r['start'] >= previous['end']]
            row = choices[0] if choices else fallback(clip, offset)
            if previous and row['start'] < previous['end']:
                raise ValueError('Ripple would overlap an earlier clip. Resolve the existing overlap first.')
            if clip['reason'] and offset:
                raise ValueError('Ripple would move an unsupported or locked strip: ' + clip['name'])
            path.append(row)
            offset = row['end'] - clip['end']
            previous = row
        return path
    previous = [{'end': -math.inf, 'penalty': 0, 'cost': 0, 'path': []}]
    for clip in clips:
        choices = candidates(clip, beats, clip['start'], clip['end'], options, fps) if clip['target'] and not clip['reason'] else []
        choices.append(fallback(clip))
        next_rows = []
        for row in choices:
            viable = [p for p in previous if row['start'] >= p['end']]
            if not viable:
                continue
            best = min(viable, key=lambda p: (p['penalty'], p['cost']))
            next_rows.append({'end': row['end'], 'penalty': best['penalty'] + int(clip['target'] and not row['aligned']),
                              'cost': best['cost'] + row['cost'], 'path': best['path'] + [row]})
        if not next_rows:
            raise ValueError('This channel contains overlapping clips. Resolve those overlaps before alignment.')
        previous = next_rows
    return min(previous, key=lambda p: (p['penalty'], p['cost']))['path']


def make_plan(scene, options=None):
    options = options or settings(scene)
    beats = beat_frames(scene, options)
    rows = capture(scene, options)
    channels = sorted({row['channel'] for row in rows if row['target']})
    preview, changes, reserved = [], [], set()
    for channel in channels:
        clips = sorted((r for r in rows if r['channel'] == channel), key=lambda r: (r['start'], r['end']))
        path = plan_channel(clips, beats, options, core.fps(scene))
        for clip, after in zip(clips, path):
            changed = (clip['start'] != after['start'] or clip['end'] != after['end'] or
                       (clip.get('in') is not None and (abs(clip['in'] - after['in']) > EPS or abs(clip['out'] - after['out']) > EPS)))
            if clip['target'] or changed:
                preview.append({'name': clip['name'], 'pointer': clip['pointer'], 'channel': channel,
                    'before': {k: clip.get(k) for k in ('start', 'end', 'in', 'out', 'speed')}, 'after': after,
                    'target': clip['target'], 'changed': changed, 'reason': clip['reason'] or ('No compatible beat pair within the threshold and source handles.' if not after['aligned'] else '')})
            if changed:
                if clip['reason']:
                    raise ValueError('Cannot change ' + clip['name'] + ': ' + clip['reason'])
                for member in [clip] + clip['linked']:
                    if member['pointer'] in reserved:
                        raise ValueError('Two clip groups share the same connected strip.')
                    reserved.add(member['pointer'])
                    changes.append({'before': member, 'after': after})
    # Connected audio is checked against every obstacle on its own channel.
    final = {row['pointer']: (row['channel'], row['start'], row['end']) for row in rows}
    for change in changes:
        before, after = change['before'], change['after']
        final[before['pointer']] = (before['channel'], after['start'], after['end'])
    for change in changes:
        pointer = change['before']['pointer']
        channel, start, end = final[pointer]
        for other, (other_channel, left, right) in final.items():
            if other != pointer and channel == other_channel and start < right and end > left:
                raise ValueError('Alignment would overlap a strip on Channel ' + str(channel) + '.')
    return {'signature': signature(scene, options), 'scene': scene.as_pointer(), 'options': options,
            'beats': beats, 'preview': preview, 'changes': changes,
            'summary': {'targets': sum(r['target'] for r in preview),
                        'aligned': sum(r['target'] and r['after']['aligned'] for r in preview),
                        'changed': sum(r['target'] and r['changed'] for r in preview),
                        'skipped': sum(r['target'] and not r['after']['aligned'] for r in preview),
                        'ripple': sum(not r['target'] and r['changed'] for r in preview)}}


def native_snapshot(strip):
    return {'origin': strip.content_start, 'left': strip.left_handle, 'right': strip.right_handle,
            'channel': strip.channel, 'keys': key_frames(strip)}


def write_change(strip, before, after):
    source_delta_frames = (after['in'] - before['in']) / before['slope']
    shift = after['start'] - before['start'] - source_delta_frames
    if abs(shift - round(shift)) > EPS:
        raise ValueError('The planned source trim cannot be represented in whole timeline frames.')
    strip.content_start += round(shift)
    strip.left_handle = after['start']
    strip.right_handle = after['end']
    strip.invalidate_cache('RAW')


def restore_all(items):
    # Vacate final edit positions before restoring the original ranges. RNA handle
    # edits can otherwise trigger Blender's automatic overlap shuffling.
    for item in items:
        strip = item['strip']
        strip.content_start += item['stage'] - strip.left_handle
    for item in items:
        strip, before, stage = item['strip'], item['before'], item['stage']
        strip.content_start = stage - (before['left'] - before['origin'])
        strip.left_handle = stage
        strip.right_handle = stage + before['right'] - before['left']
        strip.content_start += before['left'] - stage
        strip.channel = before['channel']
        strip.invalidate_cache('RAW')
        if native_snapshot(strip) != before:
            raise RuntimeError('Could not fully restore ' + strip.name + '. Use Blender Undo.')


def apply_plan(scene, plan, fail_after=None):
    if scene.as_pointer() != plan['scene'] or signature(scene, settings(scene)) != plan['signature']:
        raise ValueError('The timeline or options changed. Preview the alignment again.')
    members = {strip.as_pointer(): strip for strip in core.strips(scene)}
    untouched = {pointer: native_snapshot(strip) for pointer, strip in members.items()
                 if pointer not in {change['before']['pointer'] for change in plan['changes']}}
    padding = 2 * plan['options']['threshold'] + 100
    cursor = max(strip.right_handle for strip in members.values()) + padding
    items = []
    for change in plan['changes']:
        strip = members[change['before']['pointer']]
        duration = max(strip.right_handle - strip.left_handle, change['after']['end'] - change['after']['start'])
        if cursor + duration + padding >= 1048574:
            raise ValueError('There is not enough empty timeline space to stage these edits safely.')
        items.append({'strip': strip, 'before': native_snapshot(strip), 'stage': cursor, 'change': change})
        cursor += duration + padding
    try:
        for item in items:
            item['strip'].content_start += item['stage'] - item['strip'].left_handle
        for index, item in enumerate(items):
            strip, change, stage = item['strip'], item['change'], item['stage']
            before = read_strip(scene, strip)
            after = dict(change['after'])
            after['end'] = stage + after['end'] - after['start']
            after['start'] = stage
            write_change(strip, before, after)
            strip.content_start += change['after']['start'] - strip.left_handle
            actual = read_strip(scene, strip)
            expected = change['after']
            if (actual['start'] != expected['start'] or actual['end'] != expected['end'] or
                actual['channel'] != change['before']['channel'] or
                abs(actual['in'] - expected['in']) > .001 / core.fps(scene) or
                abs(actual['out'] - expected['out']) > .001 / core.fps(scene) or
                abs(actual['speed'] - expected['speed']) > 1e-5):
                raise ValueError('Blender timing did not match the preview for ' + strip.name + '.')
            if fail_after is not None and index + 1 == fail_after:
                raise RuntimeError('Injected verification failure')
        if any(native_snapshot(members[pointer]) != before for pointer, before in untouched.items()):
            raise ValueError('Blender changed a strip outside the preview. The alignment was cancelled.')
        core.update_all(scene, plan['options']['filter'])
    except Exception:
        restore_all(items)
        raise
    return plan['summary']
