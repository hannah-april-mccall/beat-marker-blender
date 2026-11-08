import bpy,sys,json,math,traceback
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
import beat_marker
from beat_marker import core,alignment as edit
beat_marker.register();edit.set_probe(str(ROOT/'.build/native/bin'/('ffmpeg.exe' if sys.platform=='win32' else 'ffmpeg')))
PATH=str((ROOT/'.build/integration/source.avi').resolve())
MUSIC=str((ROOT/'.build/integration/reference.wav').resolve())
checks=[];matrix=[]
def check(name,condition):
 assert condition,name
 checks.append(name)
def snapshot(s):
 return [(x.name,edit.native_snapshot(x),[p.name for p in x.connections]) for x in core.strips(s) if x.type in {'MOVIE','SOUND'}],[(m.name,m.frame) for m in s.timeline_markers],s.get(core.REGISTRY)
def fixture(name='Fixture',durations=(46,44,59,61,37,43),gap=0):
 s=bpy.data.scenes.new(name);bpy.context.window.scene=s;bpy.context.workspace.sequencer_scene=s
 s.render.fps=25;s.render.fps_base=1
 ed=s.sequence_editor_create()
 music=ed.strips.new_sound('Music reference',MUSIC,channel=1,frame_start=1)
 rows=[{'time':i*.5,'beat':i%4+1,'bar':i//4+1} for i in range(64)]
 core.import_analysis(s,music,{'schema':1,'beats':rows},core.stamp(MUSIC),'detected','ALL')
 s.timeline_markers.new('Manual marker',frame=123)
 start=251
 for i,duration in enumerate(durations):
  for x in ed.strips:x.select=False
  v=ed.strips.new_movie('Shot '+str(i+1),PATH,channel=3,frame_start=start-100)
  a=ed.strips.new_sound('Camera '+str(i+1),PATH,channel=2,frame_start=start-100)
  v.left_handle=start;v.right_handle=start+duration
  a.left_handle=start;a.right_handle=start+duration
  ed.active_strip=v;bpy.ops.sequencer.connect()
  start+=duration+gap
 for x in ed.strips:x.select=x.type=='MOVIE'
 ed.active_strip=next(x for x in ed.strips if x.type=='MOVIE')
 s.beat_marker.align_threshold=30
 return s
try:
 for mode in ['both','extend','reduce']:
  for anchor in ['start','middle','end']:
   for ripple in [False,True]:
    s=fixture();s.beat_marker.align_length=mode;s.beat_marker.align_anchor=anchor;s.beat_marker.align_ripple=ripple
    before=snapshot(s)
    plan=edit.make_plan(s)
    check('preview read only '+str((mode,anchor,ripple)),before==snapshot(s))
    check('six targets '+str((mode,anchor,ripple)),plan['summary']['targets']==6)
    edit.apply_plan(s,plan)
    beats=set(plan['beats']);linked=0
    for x in core.strips(s):
     if x.type=='MOVIE':
      actual=edit.read_strip(s,x)
      row=next(r for r in plan['preview'] if r['pointer']==x.as_pointer())
      if row['after']['aligned']:
       check('beat edges '+str((mode,anchor,ripple,x.name)),x.left_handle in beats and x.right_handle in beats)
       if mode.startswith('rate-'):
        check('source window retained '+str((mode,anchor,ripple,x.name)),abs(actual['in']-row['before']['in'])<1e-6 and abs(actual['out']-row['before']['out'])<1e-6)
      check('speed preserved '+str((mode,anchor,ripple,x.name)),abs(actual['speed']-row['before']['speed'])<1e-7)
      if mode=='extend':check('extend direction '+str((anchor,ripple,x.name)),actual['end']-actual['start']>=row['before']['end']-row['before']['start'])
      if mode=='reduce':check('reduce direction '+str((anchor,ripple,x.name)),actual['end']-actual['start']<=row['before']['end']-row['before']['start'])
      if row['after']['aligned']:
       if anchor=='start':check('source start anchor '+str((mode,ripple,x.name)),abs(actual['in']-row['before']['in'])<1e-7)
       elif anchor=='end':check('source end anchor '+str((mode,ripple,x.name)),abs(actual['out']-row['before']['out'])<1e-7)
       else:check('source midpoint anchor '+str((mode,ripple,x.name)),abs(actual['in']+actual['out']-row['before']['in']-row['before']['out'])<=actual['slope']+1e-7)
      for a in x.connections:
       audio=edit.read_strip(s,a);linked+=1
       check('connected audio '+str((mode,anchor,ripple,x.name)),audio['start']==actual['start'] and audio['end']==actual['end'] and abs(audio['in']-actual['in'])<1e-6 and abs(audio['out']-actual['out'])<1e-6)
    check('all connections retained '+str((mode,anchor,ripple)),linked==6)
    check('music fixed '+str((mode,anchor,ripple)),s.sequence_editor.strips['Music reference'].content_start==1 and next(m for m in s.timeline_markers if m.name=='Manual marker').frame==123)
    matrix.append({'mode':mode,'anchor':anchor,'ripple':ripple,'aligned':plan['summary']['aligned'],'changed':plan['summary']['changed']})
 # Failure halfway through a group restores all timings and connections.
 s=fixture();before=snapshot(s);plan=edit.make_plan(s)
 try:edit.apply_plan(s,plan,fail_after=3);raise AssertionError('fault did not trigger')
 except RuntimeError as e:assert 'Injected' in str(e)
 check('partial edit rollback',before==snapshot(s))
 s=fixture();plan=edit.make_plan(s);next(x for x in core.strips(s) if x.type=='MOVIE').content_start+=1
 try:edit.apply_plan(s,plan);raise AssertionError('stale plan accepted')
 except ValueError as e:assert 'changed' in str(e)
 check('stale preview rejected',True)
 s=fixture();videos=[x for x in core.strips(s) if x.type=='MOVIE'];videos[0].lock=True
 plan=edit.make_plan(s)
 check('locked clip skipped',plan['summary']['skipped']>=1)
 # A pending music move is used by Preview and physically refreshed on Apply.
 s=fixture();music=s.sequence_editor.strips['Music reference'];music.content_start+=2
 manual=next(m for m in s.timeline_markers if m.name=='Manual marker');plan=edit.make_plan(s)
 check('preview uses current music position',plan['beats'][0]==3)
 edit.apply_plan(s,plan)
 check('apply refreshes owned music markers',not core.is_stale(s) and manual.frame==123)
 # Low threshold reports skips rather than claiming every clip changed.
 s=fixture();s.beat_marker.align_threshold=0;plan=edit.make_plan(s)
 check('threshold reports incompatible clips',plan['summary']['skipped']>0 and not plan['changes'])
 # Selected ripple moves unselected followers and preserves their relative gaps.
 s=fixture(gap=6);videos=[x for x in core.strips(s) if x.type=='MOVIE']
 for x in videos:x.select=False
 videos[0].select=True;s.beat_marker.align_ripple=True
 before={v.name:(v.left_handle,v.right_handle) for v in videos}
 p=edit.make_plan(s);check('selected ripple has one target',p['summary']['targets']==1)
 edit.apply_plan(s,p)
 shift=videos[1].left_handle-before[videos[1].name][0]
 check('unselected ripple followers keep spacing',all(v.left_handle-before[v.name][0]==shift and v.right_handle-before[v.name][1]==shift for v in videos[1:]))
 # Retimed and reversed video are left alone.
 s=fixture();videos=[x for x in core.strips(s) if x.type=='MOVIE']
 videos[0].use_reverse_frames=True;videos[1].retiming_keys.add(timeline_frame=videos[1].left_handle)
 p=edit.make_plan(s)
 check('unsupported retime and reverse skipped',p['summary']['skipped']>=2)
 # A clip used by a transition stays fixed.
 s=fixture();videos=[x for x in core.strips(s) if x.type=='MOVIE']
 s.sequence_editor.strips.new_effect('Transition',type='CROSS',channel=4,frame_start=videos[0].left_handle,length=10,input1=videos[0],input2=videos[1])
 p=edit.make_plan(s)
 check('transition inputs skipped',all(next(r for r in p['preview'] if r['pointer']==v.as_pointer())['reason'] for v in videos[:2]))
 # The source end and start are real bounds, not permission to hold a still frame.
 s=fixture(durations=(500,));v=next(x for x in core.strips(s) if x.type=='MOVIE');a=next(iter(v.connections))
 for x in [v,a]:x.content_start=101;x.left_handle=101;x.right_handle=601
 music=s.sequence_editor.strips['Music reference']
 rows=[{'time':i*.6,'beat':i%4+1,'bar':i//4+1} for i in range(54)]
 core.import_analysis(s,music,{'schema':1,'beats':rows},core.stamp(MUSIC),'detected','ALL')
 s.beat_marker.align_length='extend';p=edit.make_plan(s)
 check('no media invented beyond source handles',p['summary']['skipped']==1 and not p['changes'])
 # Timer callbacks may have a different 3D scene from the Sequencer scene.
 s.beat_marker.align_scope='CHANNEL_3'
 bpy.context.window.scene=bpy.data.scenes.new('Different main scene')
 check('channel scope belongs to sequencer scene',edit.settings(s)['scope']=='CHANNEL_3')
 check('different main scene keeps six-clip scene settings',edit.make_plan(s)['summary']['targets']==1)
 Path('.build/integration/alignment-verification.json').write_text(json.dumps({'passed':True,'blender':bpy.app.version_string,'checks':checks,'matrix':matrix},indent=2))
 print('ALIGNMENT_TESTS_PASSED',len(checks),'checks',len(matrix),'matrix cases')
except Exception:
 traceback.print_exc()
 Path('.build/integration/alignment-verification.json').write_text(json.dumps({'passed':False,'checks':checks,'matrix':matrix,'traceback':traceback.format_exc()},indent=2))
 raise
