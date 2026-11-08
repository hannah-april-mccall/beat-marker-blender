"""Beat storage and source-to-timeline mapping. No inference runs inside Blender."""
import json
import math
from pathlib import Path
import uuid
from collections import Counter

import bpy

DATA = "beat_marker_analysis_v1"
OWNER = "beat_marker_owner_v1"
REGISTRY = "beat_marker_registry_v1"
ENABLED = "beat_marker_enabled_v1"
BEAT_SELECTION = "beat_marker_selected_beats_v1"
MAX_BEATS = 32


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def strips(scene):
    return list(scene.sequence_editor.strips) if scene.sequence_editor else []


def fps(scene):
    value = scene.render.fps / scene.render.fps_base
    if not math.isfinite(value) or value <= 0:
        raise ValueError("The scene frame rate is invalid.")
    return value


def source_path(strip):
    if strip.type != 'SOUND' or not strip.sound:
        raise ValueError("Select a music sound strip in the Video Sequencer.")
    return str(Path(bpy.path.abspath(strip.sound.filepath, library=strip.sound.library)).resolve())


def stamp(path):
    stat = Path(path).stat()
    return {"path": str(Path(path).resolve()), "size": stat.st_size, "mtime": stat.st_mtime_ns}


def validate_strip(scene, strip):
    if strip not in strips(scene):
        raise ValueError("Use a music strip outside a meta strip for this version.")
    source_path(strip)
    if strip.sound.packed_file:
        raise ValueError("Unpack this music to a file before analysing it.")
    if len(strip.retiming_keys):
        raise ValueError("Use normal-speed music without retiming keys for this version.")
    if strip.right_handle <= strip.left_handle:
        raise ValueError("This music strip has no visible duration.")


def analysis(strip):
    raw = strip.get(DATA)
    if not raw:
        return None
    value = json.loads(raw)
    if value.get("schema") != 1 or not isinstance(value.get("beats"), list):
        raise ValueError("The saved beat map is unreadable. Analyse this music again.")
    return value


def beats_per_bar(data):
    """Use the recovered meter or the consensus of complete numbered bars."""
    recovered = (data.get('recovery') or {}).get('beatsPerBar')
    if isinstance(recovered, int) and 1 <= recovered <= MAX_BEATS:
        return recovered
    counts, bar = Counter(), []
    for row in data['beats']:
        beat = row.get('beat')
        if beat == 1:
            if bar and bar == list(range(1, len(bar) + 1)) and len(bar) <= MAX_BEATS:
                counts[len(bar)] += 1
            bar = [1]
        elif bar:
            bar.append(beat)
    if counts:
        return counts.most_common(1)[0][0]
    # A very short source may contain no complete bar.
    return max((r['beat'] for r in data['beats'] if isinstance(r.get('beat'), int)
                and 1 <= r['beat'] <= MAX_BEATS), default=0)


def available_beats(scene):
    songs = [s for s in strips(scene) if s.type == 'SOUND' and s.get(DATA)]
    selected = [s for s in songs if s.select]
    songs = selected or [s for s in songs if s.get(ENABLED, True)]
    meters = sorted({beats_per_bar(analysis(s)) for s in songs} - {0})
    return list(range(1, max(meters, default=0) + 1)), meters


def beat_filter(scene):
    if BEAT_SELECTION in scene:
        return sorted({int(n) for n in scene[BEAT_SELECTION] if 1 <= int(n) <= MAX_BEATS})
    # Existing projects keep their Every beat / Beat n selection.
    legacy = scene.beat_marker.beat_filter
    return 'ALL' if legacy == 'ALL' else [int(legacy)]


def beat_checks(settings):
    scene = settings.id_data
    selected = beat_filter(scene)
    if selected == 'ALL':
        selected = available_beats(scene)[0]
    return tuple(n in selected for n in range(1, MAX_BEATS + 1))


def set_beat_checks(settings, values):
    settings.id_data[BEAT_SELECTION] = [i + 1 for i, checked in enumerate(values) if checked]


def registry(scene):
    raw = scene.get(REGISTRY)
    return json.loads(raw) if raw else {}


def validate_result(result):
    if result.get("schema") not in (1, 2) or not isinstance(result.get("beats"), list):
        raise ValueError("The analyser returned an invalid beat map.")
    last = -1.0
    for row in result["beats"]:
        t = row.get("time")
        if not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0 or t < last:
            raise ValueError("The analyser returned an invalid beat timestamp.")
        for key in ("beat", "bar"):
            if row.get(key) is not None and (not isinstance(row[key], int) or row[key] < 0):
                raise ValueError("The analyser returned an invalid beat number.")
        last = t


def mapping(scene, strip):
    """Blender sound skip = handle offset + content trim - sound offset * fps."""
    validate_strip(scene, strip)
    rate = fps(scene)
    # Sound datablock offset_time is not exposed by every Blender version.
    offset = float(strip.sound_offset) + float(getattr(strip.sound, "offset_time", 0.0))
    origin = float(strip.content_start) - float(strip.content_trim_start) + offset * rate
    return origin, float(strip.left_handle), float(strip.right_handle), rate


def rows_for_strip(scene, strip, data, beat_filter):
    origin, left, right, rate = mapping(scene, strip)
    if stamp(source_path(strip)) != data["source_stamp"]:
        raise ValueError("The music file changed. Analyse “" + strip.name + "” again.")
    rows = []
    allowed = None if beat_filter == 'ALL' else {int(n) for n in beat_filter} if isinstance(beat_filter, (list, tuple, set)) else {int(beat_filter)}
    for index, row in enumerate(data["beats"]):
        if allowed is not None and row.get("beat") not in allowed:
            continue
        position = origin + row["time"] * rate
        # Check source visibility before rounding; the out handle is exclusive.
        if position < left - 1e-6 or position >= right - 1e-6:
            continue
        frame = math.floor(position + 0.5)
        frame = max(int(left), min(int(right) - 1, frame))
        if frame < -1048574 or frame > 1048574:
            raise ValueError("A beat lies outside Blender’s supported marker frame range.")
        rows.append({"frame": frame, "beat": row.get("beat"), "bar": row.get("bar"), "index": index})
    return rows


def owner_plan(scene, saved):
    """Duplicating a strip copies properties; give its new instance its own owner."""
    groups = {}
    for strip in strips(scene):
        if strip.type == 'SOUND' and strip.get(DATA):
            groups.setdefault(strip.get(OWNER, ""), []).append(strip)
    result = []
    for owner, members in groups.items():
        old_name = saved.get(owner, {}).get("strip_name")
        members.sort(key=lambda strip: strip.name != old_name)
        for index, strip in enumerate(members):
            result.append((strip, owner if owner and index == 0 else uuid.uuid4().hex))
    return result


def owned_markers(scene, saved):
    names = {row["name"] for entry in saved.values() for row in entry["markers"]}
    found = {}
    for marker in scene.timeline_markers:
        if marker.name in names:
            if marker.name in found:
                raise ValueError("Two markers share a generated name. Rename the duplicate before updating.")
            if marker.camera:
                raise ValueError("A beat marker is bound to a camera. Unbind it before updating.")
            found[marker.name] = marker
    return found


def short_utf8(text, limit):
    return text.encode('utf-8')[:limit].decode('utf-8', errors='ignore')


def marker_label(strip, row):
    number = str(row["beat"]) if row["beat"] is not None else "?"
    bar = "bar " + str(row["bar"]) if row["bar"] is not None else "beat " + str(row["index"] + 1)
    return "♩ " + number + " · " + short_utf8(strip.name, 30) + " · " + bar


def replace_markers(scene, plans, *, replace_owners=None, disable=()):
    """Preflight every strip, then replace only registered marker names atomically."""
    saved = registry(scene)
    found = owned_markers(scene, saved)
    replace_owners = set(saved) if replace_owners is None else set(replace_owners)
    removing = {row["name"] for owner, entry in saved.items() if owner in replace_owners for row in entry["markers"]}
    used = {marker.name for marker in scene.timeline_markers if marker.name not in removing}
    updated = {key: value for key, value in saved.items() if key not in replace_owners}
    count = 0
    for strip, owner, rows, data, beat_filter in plans:
        markers = []
        for row in rows:
            base = short_utf8(marker_label(strip, row), 57)
            name, suffix = base, 2
            while name in used:
                name = short_utf8(base, 55) + " · " + str(suffix)
                suffix += 1
            used.add(name)
            markers.append({"name": name, "frame": row["frame"]})
        updated[owner] = {"strip_name": strip.name, "markers": markers, "filter": beat_filter}
        count += len(markers)
    before_markers = [{"name": marker.name, "frame": marker.frame, "select": marker.select}
                      for name, marker in found.items() if name in removing]
    touched = [strip for strip, *_ in plans] + list(disable)
    before_props = [(strip, {key: strip.get(key) for key in (OWNER, DATA, ENABLED)}) for strip in touched]
    new_markers = []
    try:
        for name in removing:
            if name in found:
                scene.timeline_markers.remove(found[name])
        for strip, owner, rows, data, beat_filter in plans:
            strip[OWNER] = owner
            strip[DATA] = dumps(data)
            strip[ENABLED] = True
            for row in updated[owner]["markers"]:
                marker = scene.timeline_markers.new(row["name"], frame=row["frame"])
                marker.select = False
                new_markers.append(marker)
        for strip in disable:
            strip[ENABLED] = False
        scene[REGISTRY] = dumps(updated)
    except Exception:
        for marker in new_markers:
            scene.timeline_markers.remove(marker)
        for row in before_markers:
            marker = scene.timeline_markers.new(row["name"], frame=row["frame"])
            marker.select = row["select"]
        for strip, values in before_props:
            for key, value in values.items():
                if value is None:
                    if key in strip:
                        del strip[key]
                else:
                    strip[key] = value
        scene[REGISTRY] = dumps(saved)
        raise
    return count


def import_analysis(scene, strip, result, source_stamp, timing, beat_filter):
    validate_result(result)
    validate_strip(scene, strip)
    if stamp(source_path(strip)) != source_stamp:
        raise ValueError("The source changed during analysis. Select it and analyse again.")
    saved = registry(scene)
    assignments = {strip.as_pointer(): owner for strip, owner in owner_plan(scene, saved)}
    owner = assignments.get(strip.as_pointer(), uuid.uuid4().hex)
    data = {"schema": 1, "beats": result["beats"], "source_stamp": source_stamp,
            "timing": timing, "median_bpm": result.get("medianBpm"),
            "recovery": result.get("recovery"), "engine": result.get("engine")}
    rows = rows_for_strip(scene, strip, data, beat_filter)
    return replace_markers(scene, [(strip, owner, rows, data, beat_filter)], replace_owners={owner})


def update_all(scene, beat_filter):
    saved = registry(scene)
    plans = []
    for strip, owner in owner_plan(scene, saved):
        if not strip.get(ENABLED, True):
            continue
        data = analysis(strip)
        plans.append((strip, owner, rows_for_strip(scene, strip, data, beat_filter), data, beat_filter))
    if not plans and not saved:
        raise ValueError("Analyse a music strip first.")
    return replace_markers(scene, plans)


def remove_selected(scene):
    saved = registry(scene)
    selected = [(strip, owner) for strip, owner in owner_plan(scene, saved) if strip.select]
    owners = {owner for strip, owner in selected}
    removed = sum(len(value["markers"]) for key, value in saved.items() if key in owners)
    if not removed:
        raise ValueError("Select a music strip with Beat Marker markers to remove.")
    replace_markers(scene, [], replace_owners=owners, disable=[strip for strip, owner in selected])
    return removed


def is_stale(scene, desired_filter=None):
    saved = registry(scene)
    assignments = [(strip, owner) for strip, owner in owner_plan(scene, saved) if strip.get(ENABLED, True)]
    if len(assignments) != len(saved):
        return bool(assignments or saved)
    for strip, owner in assignments:
        old = saved.get(owner)
        if not old:
            return True
        try:
            rows = rows_for_strip(scene, strip, analysis(strip), old["filter"] if desired_filter is None else desired_filter)
        except Exception:
            return True
        if [row["frame"] for row in rows] != [row["frame"] for row in old["markers"]]:
            return True
    return False
