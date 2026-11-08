import bpy,sys,json,math,traceback
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
import beat_marker
from beat_marker import core,alignment
beat_marker.register()
checks=[]
def check(name,value):
 assert value,name
 checks.append(name)
def rows(meter,count):
 return [{'time':i*.5,'beat':i%meter+1,'bar':i//meter+1} for i in range(count)]
def markers(scene,strip):
 return core.registry(scene)[strip[core.OWNER]]['markers']
try:
 s=bpy.context.scene;s.render.fps=25;s.render.fps_base=1
 ed=s.sequence_editor_create()
 path=str((ROOT/'.build/integration/reference.wav').resolve())
 a=ed.strips.new_sound('Four beats',path,channel=1,frame_start=137)
 core.import_analysis(s,a,{'schema':1,'beats':rows(4,64)},core.stamp(path),'detected','ALL')
 manual=s.timeline_markers.new('Keep manual',frame=155)
 check('four-beat music has four choices',core.available_beats(s)==([1,2,3,4],[4]))
 check('legacy every beat defaults to four checked boxes',list(s.beat_marker.beat_checks[:5])==[True]*4+[False])
 before=[(m.name,m.frame) for m in s.timeline_markers]
 s.beat_marker.beat_checks[1]=False;s.beat_marker.beat_checks[3]=False
 check('native checkboxes select beats one and three',core.beat_filter(s)==[1,3])
 check('choosing checkboxes does not edit markers until Update',before==[(m.name,m.frame) for m in s.timeline_markers])
 check('pending selection detected',core.is_stale(s,core.beat_filter(s)))
 bpy.ops.beat_marker.update_markers('EXEC_DEFAULT')
 expected=[137+math.floor(r['time']*25+.5) for r in rows(4,64) if r['beat'] in (1,3)]
 check('one and three produce exactly their source-aligned markers',[m['frame'] for m in markers(s,a)]==expected)
 check('no beats two or four labelled',all('♩ 1 ·' in m['name'] or '♩ 3 ·' in m['name'] for m in markers(s,a)))
 check('manual marker preserved',s.timeline_markers['Keep manual'].frame==155)
 check('selection applied without stale marker warning',not core.is_stale(s,core.beat_filter(s)))
 check('alignment follows the same one and three filter',alignment.beat_frames(s,alignment.settings(s))==expected)
 b=ed.strips.new_sound('Three beats',path,channel=2,frame_start=1101)
 core.import_analysis(s,b,{'schema':1,'beats':rows(3,60)},core.stamp(path),'detected',core.beat_filter(s))
 a.select=False;b.select=True
 check('selected three-beat song has only three choices',core.available_beats(s)==([1,2,3],[3]))
 check('one and three remain selected in a three-beat song',list(s.beat_marker.beat_checks[:3])==[True,False,True])
 check('three-beat music also filters one and three',len(markers(s,b))==40)
 a.select=False;b.select=False
 check('mixed songs without selection offer all recognised positions',core.available_beats(s)==([1,2,3,4],[3,4]))
 a.select=True
 a.left_handle=137;a.right_handle=155
 check('visible trim does not hide later beat numbers',core.available_beats(s)==([1,2,3,4],[4]))
 intro=rows(12,12)+[dict(r,time=r['time']+6,bar=r['bar']+1) for r in rows(4,40)]
 check('isolated missing downbeat does not create twelve checkboxes',core.beats_per_bar({'beats':intro})==4)
 check('recovered meter takes precedence',core.beats_per_bar({'beats':rows(3,60),'recovery':{'beatsPerBar':4}})==4)
 check('six-beat meter supported',core.beats_per_bar({'beats':rows(6,60)})==6)
 a.right_handle=937
 # Save/reload only the disposable test file, leaving the user's projects alone.
 file=ROOT/'.build/integration/persistence.blend'
 bpy.ops.wm.save_as_mainfile(filepath=str(file));bpy.ops.wm.open_mainfile(filepath=str(file))
 s=bpy.context.scene;ed=s.sequence_editor;a=ed.strips['Four beats'];b=ed.strips['Three beats']
 check('checkbox combination survives save and reload',core.beat_filter(s)==[1,3])
 s.beat_marker.beat_checks=tuple(False for i in range(core.MAX_BEATS))
 check('all unchecked is an empty selection',core.beat_filter(s)==[])
 core.update_all(s,core.beat_filter(s))
 check('empty selection removes only generated markers',[(m.name,m.frame) for m in s.timeline_markers]==[('Keep manual',155)])
 check('empty selection preserves analysis',bool(a.get(core.DATA)) and bool(b.get(core.DATA)))
 del s[core.BEAT_SELECTION];s.beat_marker.beat_filter='1'
 check('legacy bar-start setting migrates to beat one',core.beat_filter(s)==[1] and list(s.beat_marker.beat_checks[:4])==[True,False,False,False])
 empty=bpy.data.scenes.new('No analysis')
 check('no invented beat count before analysis',core.available_beats(empty)==([],[]))
 Path('.build/integration/markers-verification.json').write_text(json.dumps({'passed':True,'blender':bpy.app.version_string,'checks':checks},indent=2))
 print('BEAT_SELECTION_PASSED',len(checks))
except Exception:
 Path('.build/integration/markers-verification.json').write_text(json.dumps({'passed':False,'checks':checks,'error':traceback.format_exc()},indent=2));raise
