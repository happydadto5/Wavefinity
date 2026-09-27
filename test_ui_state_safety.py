"""Focused, non-browser checks for Fix 071B state and preview transport."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from test_space_preferences import function_source
from test_wavefinity_web import _fix21_photo_design
from wavefinity_web import default_design, default_feature_payload, duplicate_feature_payload, preview_payload


ROOT = Path(__file__).resolve().parent
APP = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
PANEL = (ROOT / "web" / "drawer-panel.js").read_text(encoding="utf-8")


def node_json(source: str):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is required")
    result = subprocess.run([node, "-e", source], capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class BrowserStateLogicTests(unittest.TestCase):
    def test_same_selected_preview_pick_rechecks_generation_before_2d(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("selectedFeature", "selectFromPreview"))
        script = r"""
const design={layout:{features:[{kind:'post'}]}},space={id:'S'},events=[];
const state={design,activeSpace:space,designInventoryId:'B1',previewRequest:4,selected:0};
const DP={mode:'design'},$=()=>({textContent:'',classList:{add(){},remove(){}}});
const activatePreviewView=v=>events.push(v),renderLayout2D=()=>events.push('layout');
const localStorage={getItem:()=>null};
__SOURCE__
(async()=>{
  const rejected=await selectedFeature(0,false,()=>false);
  Promise.resolve().then(()=>state.previewRequest++);
  await selectFromPreview({type:'saved',index:0},
    {design,space,source:'B1',preview:4});
  process.stdout.write(JSON.stringify({rejected,events,selected:state.selected}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {"rejected": False, "events": [], "selected": 0})


    def test_space_edit_real_async_chain_never_overwrites_newer_navigation(self):
        app_source = "\n".join(function_source(name, APP) for name in
                               ("installLoadedDesignSource", "designerEditInventoryRow",
                                "designerInstallInventorySpec"))
        script = r"""
const fs=require('fs'),vm=require('vm'),events=[],resolvers={};
const original={marker:'original',layout:{features:[]}},space={id:'S'};
const state={folderMode:'space',activeSpace:space,activeSpaceId:'S',output:'folder',
  design:original,designInventoryId:'B1'};
const DL={active:true,loaded:true,pegboardRefreshError:false,selectedRow:'B1',
  layout:{design_specs:{B2:{marker:'B2'},B3:{marker:'B3'}}},
  bin:id=>({id,kind:'bin'}),selectRow:id=>{DL.selectedRow=id;events.push('select:'+id)},
  spaceContext:()=>({spaceId:state.activeSpaceId,output:state.output}),
  spaceContextCurrent:c=>c.spaceId===state.activeSpaceId&&c.output===state.output};
const ctx={Map,Set,Promise,JSON,Number,String,Object,Date,Math,state,DL,
  localStorage:{getItem:()=>null},$:()=>null,$$:()=>[],
  SP:{offerSpacePlanning(){}},toast:()=>{},clone:v=>JSON.parse(JSON.stringify(v)),
  isStructuralDesign:()=>false,typedSpaceOrdinaryBin:()=>true,
  flushSpaceDesignAutosave:async()=>true,beginDesignMutation:()=>true,finishDesignMutation:()=>{},
  api:(_path,arg)=>new Promise(resolve=>resolvers[arg.design.marker]=resolve),
  resetNestPhotoSession:()=>{},bindLidMemoryForDesign:()=>{},syncForm:()=>{},
  clearDraftSelection:()=>{},refreshPreview:()=>Promise.resolve(),
  activatePreviewView:v=>events.push('view:'+v)};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8')+';this.DP=DP',ctx);
vm.runInContext(__APP_SOURCE__,ctx);
const DP=ctx.DP;DP.mode='space';DP.showPendingMode=()=>{};
DP.setMode=mode=>{DP.mode=mode;events.push('mode:'+mode)};
DP.update=()=>{};DP.ensureInventoryLoaded=async()=>true;
const tick=()=>new Promise(setImmediate);
(async()=>{
  const old=DP.openInventoryRow('B2');await tick();
  await DP.selectMode('space');
  resolvers.B2({design:{marker:'B2',layout:{features:[]}}});await old;
  const afterNavigation=[state.design.marker,DL.selectedRow,DP.mode];
  const first=DP.openInventoryRow('B2');await tick();
  const second=DP.openInventoryRow('B3');await tick();
  resolvers.B3({design:{marker:'B3',layout:{features:[]}}});await second;
  resolvers.B2({design:{marker:'B2',layout:{features:[]}}});await first;
  process.stdout.write(JSON.stringify({afterNavigation,afterCompeting:[state.design.marker,DL.selectedRow,DP.mode]}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__APP_SOURCE__", json.dumps(app_source))
        out = node_json(script.replace("process.argv[1]", json.dumps(str(ROOT / "web" / "drawer-panel.js"))))
        self.assertEqual(out["afterNavigation"], ["original", "B1", "space"])
        self.assertEqual(out["afterCompeting"], ["B3", "B3", "design"])



    def test_compact_mesh_pick_is_frontmost_and_respects_base_lid_visibility(self):
        names = ["pointInPolygon", "pickTriangleDepth", "previewPickDepth", "clickedPreviewMesh"]
        source = "\n".join(function_source(name, APP) for name in names)
        script = r"""
const tri=z=>[0,0,z,10,0,z,0,10,z];
const divider={positions:tri(1),normals:[0,0,1],owner:'base'};
const cover={positions:tri(2),normals:[0,0,1],owner:'base'};
const state={preview:{meshes:[divider],pick_meshes:[{mesh_index:0,pick:{type:'saved',index:0}}]},
  previewPickMeshContext:{camera:{},project:p=>[p[0],p[1]],visibleGroups:new Set(['base'])}};
const cameraVector=()=>[0,0,1],iso=p=>p,dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
__SOURCE__
const picked=clickedPreviewMesh([2,2])?.pick;
state.preview.meshes.push(cover);
const occluded=clickedPreviewMesh([2,2])?.pick;
state.previewPickMeshContext.visibleGroups=new Set(['lid']);
const hidden=clickedPreviewMesh([2,2]);
process.stdout.write(JSON.stringify({picked,occluded,hidden}));
""".replace("__SOURCE__", source)
        out = node_json(script)
        self.assertEqual(out, {"picked": {"type": "saved", "index": 0}, "occluded": None, "hidden": None})


    def test_delayed_preview_pick_rejects_new_preview_generation(self):
        source = function_source("selectedFeature", APP)
        script = r"""
const design={layout:{features:[{kind:'post',zone:[0,0,8,8]}]}}, space={id:'S'};
const state={design,activeSpace:space,designInventoryId:'B1',previewRequest:7,
  selected:null,draft:{kind:'post'},partZoneLocks:{}};
let release; const deferredDraftSwitch=()=>new Promise(resolve=>release=resolve);
const $=()=>({hidden:false}),$$=()=>[];
const clone=v=>JSON.parse(JSON.stringify(v));
const resetNestPhotoSession=()=>{},commitEdgeMountFormBeforeSwitch=()=>true;
const cancelPendingDraftWork=()=>{},updateNudgeUI=()=>{},AUTO_FOOTPRINT_KINDS=new Set();
const updateInteriorModeVisibility=()=>{},partInfo=()=>({}),syncDraftEditorIdentity=()=>{};
const renderDraftFields=()=>{},renderPlaced=()=>{},updateSelectionButtons=()=>{};
const refreshDraft=()=>{},renderLayout2D=()=>{};
__SOURCE__
(async()=>{
  const oldGeneration=state.previewRequest;
  const pending=selectedFeature(0,false,()=>state.previewRequest===oldGeneration);
  state.previewRequest++;
  release({proceed:true,committed:false,finish:()=>{}});
  const accepted=await pending;
  process.stdout.write(JSON.stringify({accepted,selected:state.selected}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {"accepted": False, "selected": None})

    def test_inventory_edit_pending_and_rollback(self):
        script = r"""
const fs=require('fs'),vm=require('vm');
const ctx={Map,Set,Promise,JSON,Number,String,Object,Date,
  state:{folderMode:'space',activeSpaceId:'S',output:'folder'},
  DL:{active:true,spaceContext:()=>({spaceId:'S'}),spaceContextCurrent:c=>c.spaceId==='S',
    selectRow:id=>events.push('select:'+id)},
  activatePreviewView:v=>events.push('view:'+v),
  localStorage:{getItem:()=>null},$:()=>null,$$:()=>[]};
const events=[]; let release;
ctx.designerEditInventoryRow=()=>new Promise(resolve=>release=resolve);
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8')+';this.DP=DP',ctx);
const DP=ctx.DP;DP.mode='space';
DP.showPendingMode=mode=>events.push('pending:'+mode);
DP.setMode=mode=>{DP.mode=mode;events.push('mode:'+mode)};
(async()=>{
  const failed=DP.openInventoryRow('B2');
  const before=[DP.mode,events.slice()];release(false);await failed;
  const afterFailure=[DP.mode,events.slice()];events.length=0;
  const accepted=DP.openInventoryRow('B2');release(true);await accepted;
  process.stdout.write(JSON.stringify({before,afterFailure,afterSuccess:[DP.mode,events]}));
})().catch(e=>{console.error(e);process.exit(1)});
"""
        out = node_json(script.replace("process.argv[1]", json.dumps(str(ROOT / "web" / "drawer-panel.js"))))
        self.assertEqual(out["before"], ["space", ["pending:design"]])
        self.assertEqual(out["afterFailure"], ["space", ["pending:design", "pending:null"]])
        self.assertEqual(out["afterSuccess"], ["design", ["pending:design", "select:B2", "mode:design", "view:3d", "pending:null"]])






    def test_side_opening_pair_mapping_clamp_and_round_trip(self):
        names = ["sideOpeningVerticalFits", "sideOpeningPairFromControls",
                 "sideOpeningRangeLegal", "normalizeSideOpeningPair", "readSideOpeningForm",
                 "syncSideOpeningRange"]
        source = "\n".join(function_source(name, APP) for name in names)
        script = r"""
const els={}, make=()=>({value:'',hidden:false,style:{},getAttribute:()=>null,setAttribute(){}});
const $=s=>els[s] ||= make(), number=(v,f=0)=>Number.isFinite(Number(v))?Number(v):f;
const fmt=v=>String(Math.round(v*10)/10);
const state={catalog:{side_openings:{sizes:[{value:'medium',width_mm:10}],top_bridge_mm:4}}};
const SIDE_OPENING_DEFAULTS={enabled:false,shape:'curved',size:'medium',sides:[],from_bottom_percent:0,from_top_percent:0};
const SIDE_OPENING_SIDE_IDS=['front','back','left','right'];
let lid=false;
const sideOpeningLidStackForced=()=>lid;
const sideOpeningMinFromTop=()=>20;
const sideOpeningState=d=>({...SIDE_OPENING_DEFAULTS,...(d.box.side_openings||{})});
const sideOpeningAllowedSizes=()=>['medium'];
const b4bEnabled=()=>false, baseTrimEnabled=()=>false;
__FUNCTIONS__
const design={box:{z:40,base_thickness:0.6}};
$('#side-opening-front').getAttribute=()=> 'true';
$('#side-opening-shape').value='curved'; $('#side-opening-size').value='medium';
function read(lower,upper){$('#side-opening-lower').value=String(lower);$('#side-opening-upper').value=String(upper);
 readSideOpeningForm(design); return {...design.box.side_openings};}
const zero=read(0,100), ten=read(10,90);
syncSideOpeningRange(ten);
const handles=[$('#side-opening-lower').value,$('#side-opening-upper').value];
const crossing=normalizeSideOpeningPair(design,{lower:95,upper:90},'lower');
lid=true;
const bridged=normalizeSideOpeningPair(design,{lower:10,upper:100},'upper');
process.stdout.write(JSON.stringify({zero,ten,handles,crossing,bridged}));
""".replace("__FUNCTIONS__", source)
        out = node_json(script)
        self.assertEqual((out["zero"]["from_bottom_percent"], out["zero"]["from_top_percent"]), (0, 0))
        self.assertEqual((out["ten"]["from_bottom_percent"], out["ten"]["from_top_percent"]), (10, 10))
        self.assertEqual(out["handles"], ["10", "90"])
        self.assertLess(out["crossing"]["lower"], out["crossing"]["upper"])
        self.assertLessEqual(out["bridged"]["upper"], 80)

    def test_ai_help_envelope_composition_session_and_space_rules(self):
        source = "\n".join(function_source(name, APP) for name in (
            "aiParseEnvelope", "aiCompositionEmpty", "aiCheckSession", "aiSpaceViolation"))
        error_class = APP[APP.index("class AiHelpError"):APP.index("\n}\n", APP.index("class AiHelpError")) + 3]
        schema = re.search(r'const AI_SCHEMA = "([^"]+)"', APP).group(1)
        script = r"""
__ERROR__
const AI_SCHEMA='__SCHEMA__',number=(v,f=0)=>{const n=Number(v);return Number.isFinite(n)?n:f},fmt=v=>String(v);
let draft=false,key='K1',space={kind:'drawer',x:80,y:80,z:50};
const state={folderMode:'space',get activeSpace(){return space},catalog:{base_unit:8}};
const draftNeedsSaving=()=>draft,edgeMountActive=d=>Boolean(d.box.edge_mount);
const isStructuralDesign=d=>Boolean(d.box.b4b?.enabled),drawerSpaceCapacity=mm=>Math.floor(mm/8);
const aiContextKey=()=>key;
__FUNCTIONS__
const ok={schema:AI_SCHEMA,request_id:'R',context_fingerprint:'F',assumptions:[],design:{box:{x:16}}};
const text=v=>JSON.stringify(v);
const fail=fn=>{try{fn();return null}catch(e){return e.stale?'stale':e.message}};
const parsed=[
  aiParseEnvelope(text(ok)).request_id,
  aiParseEnvelope('```json\n'+text(ok)+'\n```').request_id,
  fail(()=>aiParseEnvelope('Here you go: '+text(ok))),
  fail(()=>aiParseEnvelope(text(ok)+text(ok))),
  fail(()=>aiParseEnvelope('```json\n```json\n'+text(ok)+'\n```\n```')),
  fail(()=>aiParseEnvelope(text({...ok,schema:'v2'}))),
  fail(()=>aiParseEnvelope(text({...ok,assumptions:undefined}))),
  fail(()=>aiParseEnvelope(text({...ok,design:[]}))),
];
const blank={box:{x:16,y:32,z:40,wall:1.2,pegboard:{enabled:true}},label:'',scoop:false,layout:{features:[]}};
const withBox=extra=>({...blank,box:{...blank.box,...extra}});
const composed={
  blank:aiCompositionEmpty(blank),
  feature:aiCompositionEmpty({...blank,layout:{features:[{kind:'text'}]}}),
  label:aiCompositionEmpty({...blank,label:'Tools'}),
  scoop:aiCompositionEmpty({...blank,scoop:true}),
  lid:aiCompositionEmpty(withBox({lid:{enabled:true}})),
  stack:aiCompositionEmpty(withBox({stack:{mode:'direct'}})),
  grip:aiCompositionEmpty(withBox({lift_grabbers:{enabled:true}})),
  sides:aiCompositionEmpty(withBox({side_openings:{enabled:true}})),
  edge:aiCompositionEmpty(withBox({edge_mount:{side:'front'}})),
};
draft=true;composed.draft=aiCompositionEmpty(blank);draft=false;
const session={request_id:'R',context_fingerprint:'F',contextKey:'K1'};
const sessions=[fail(()=>aiCheckSession(ok,session)),fail(()=>aiCheckSession(ok,null)),
  fail(()=>aiCheckSession({...ok,request_id:'OLD'},session)),
  fail(()=>{key='K2';aiCheckSession(ok,session)})];
const base={box:{x:32,y:32,z:40,pegboard:{enabled:true,standard:'standard',cleat_x:'auto'}}};
space={kind:'drawer',x:80,y:80,z:50};const plain={box:{x:32,y:32,z:40}};
const rules=[aiSpaceViolation({box:{x:72,y:72,z:50}},plain),aiSpaceViolation({box:{x:88,y:72,z:50}},plain),
  aiSpaceViolation({box:{x:72,y:72,z:60}},plain),
  aiSpaceViolation({box:{x:16,y:16,z:40,b4b:{enabled:true}}},plain)];
space={kind:'pegboard',x:200,y:200,z:100,pegboard_standard:'standard'};
rules.push(aiSpaceViolation({box:{x:32,y:32,z:60,pegboard:base.box.pegboard}},base),
  aiSpaceViolation({box:{x:32,y:32,z:60}},base),
  aiSpaceViolation({box:{x:32,y:32,z:60,pegboard:{...base.box.pegboard,cleat_x:'3'}}},base));
process.stdout.write(JSON.stringify({parsed,composed,sessions,rules}));
""".replace("__ERROR__", error_class).replace("__SCHEMA__", schema).replace("__FUNCTIONS__", source)
        out = node_json(script)
        self.assertEqual(out["parsed"][:2], ["R", "R"])
        self.assertTrue(all(out["parsed"][2:]))
        self.assertEqual(out["composed"], {
            "blank": True, "feature": False, "label": False, "scoop": False, "lid": False,
            "stack": False, "grip": False, "sides": False, "edge": False, "draft": False})
        self.assertEqual(out["sessions"][0], None)
        self.assertEqual(out["sessions"][1:], ["stale", "stale", "stale"])
        self.assertIsNone(out["rules"][0])
        self.assertTrue(all(out["rules"][1:4]))
        self.assertIsNone(out["rules"][4])
        self.assertTrue(all(out["rules"][5:]))

    def test_ai_help_install_reuses_or_creates_identity_and_adopts_without_rebuild(self):
        source = "\n".join(function_source(name, APP) for name in (
            "aiIdentityKey", "aiSpaceContext", "aiInstallCandidate", "aiProveCandidate", "aiCheckSession"))
        error_class = APP[APP.index("class AiHelpError"):APP.index("\n}\n", APP.index("class AiHelpError")) + 3]
        script = r"""
__ERROR__
const clone=v=>JSON.parse(JSON.stringify(v)),events=[],previewClientId='C';
const old={box:{x:16},marker:'old',layout:{features:[]}},proven={marker:'ai',box:{x:32},layout:{features:[]}};
const state={folderMode:'space',activeSpace:{kind:'drawer',x:80,y:80,z:50},activeSpaceId:'S',
  designInventoryId:'B1',design:old,cleanDesign:old,previewRequest:0,history:[1]};
const aiHelp={generation:0};let fullPreviewStarts=0,unsaved=false,confirmed=true,next={problems:[]};
const aiContextKey=()=>'K',aiSetStatus=()=>{},typedSpaceOrdinaryBin=()=>true;
const withDeferredDraftSwitch=action=>action({}),beginDesignMutation=()=>true,finishDesignMutation=()=>{};
const resetNestPhotoSession=()=>{},bindLidMemoryForDesign=()=>{},syncForm=()=>{},clearDraftSelection=()=>{};
const DP={setMode:()=>{}},activatePreviewView=()=>{},freshDesignForCurrentFolder=()=>clone(old);
const flushSpaceDesignAutosave=async()=>{events.push('flush');return true};
const designHasChanges=()=>unsaved,appConfirmAction=async()=>confirmed;
const invalidatePendingPreview=()=>{state.previewRequest+=1;events.push('invalidate')};
const adoptPreviewResult=r=>{state.preview=r;state.design=r.design;events.push('adopt')};
const persistSpaceDesignSource=async(_c,force)=>{events.push('persist:'+force)};
const refreshPreview=()=>events.push('REBUILD');
const aiSpaceViolation=()=>null;
const api=async path=>{events.push('api:'+path);return next};
__FUNCTIONS__
const candidate=()=>({design:clone(proven),preview:{design:clone(proven),fits:true}});
const session=reuse=>({request_id:'R',context_fingerprint:'F',reuse,baseline:old,
  contextKey:JSON.stringify({identity:aiIdentityKey()})});
(async()=>{
  const run=async reuse=>{
    events.length=0;state.design=clone(old);state.designInventoryId='B1';
    const ok=await aiInstallCandidate(candidate(),session(reuse));
    return {ok,marker:state.design.marker,id:state.designInventoryId,events:[...events],
      previews:fullPreviewStarts,history:state.history.length};
  };
  const reuse=await run(true), fresh=await run(false);
  unsaved=true;confirmed=false;state.activeSpace=state.activeSpace;
  const noSpace=(state.folderMode='design',state.activeSpace=null,state.activeSpaceId=null,
    await (async()=>{events.length=0;state.design=clone(old);const ok=await aiInstallCandidate(candidate(),
      {request_id:'R',context_fingerprint:'F',reuse:false,baseline:old,contextKey:JSON.stringify({identity:aiIdentityKey()})});
      return {ok,marker:state.design.marker,events:[...events]}})());
  state.folderMode='space';state.activeSpace={kind:'drawer',x:80,y:80,z:50};state.activeSpaceId='S';
  state.design=clone(old);events.length=0;next={problems:['post: does not fit'],design:proven};
  let refusal=null;
  try{await aiProveCandidate({design:{},request_id:'R',context_fingerprint:'F'},{...session(true),contextKey:'K'})}
  catch(e){refusal=e.message}
  const stale=await(async()=>{state.design=clone(old);const bound=session(true);state.activeSpaceId='OTHER';
    try{await aiInstallCandidate(candidate(),bound);return null}catch(e){return e.stale}})();
  process.stdout.write(JSON.stringify({reuse,fresh,noSpace,refusal,marker:state.design.marker,stale}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__ERROR__", error_class).replace("__FUNCTIONS__", source)
        out = node_json(script)
        self.assertEqual((out["reuse"]["previews"], out["fresh"]["previews"]), (1, 2))  # one owner claim each
        # Blank bin: rewritten in place, keeps its row, saved as an edit, preview adopted not rebuilt.
        self.assertEqual((out["reuse"]["ok"], out["reuse"]["marker"], out["reuse"]["id"]), (True, "ai", "B1"))
        self.assertEqual(out["reuse"]["events"], ["invalidate", "adopt", "persist:true"])
        # Meaningful bin: saved first, then the AI result is a brand-new bin.
        self.assertEqual((out["fresh"]["ok"], out["fresh"]["marker"], out["fresh"]["id"]), (True, "ai", None))
        self.assertEqual(out["fresh"]["events"], ["flush", "invalidate", "adopt", "persist:true"])
        for one in (out["reuse"], out["fresh"]):
            self.assertNotIn("REBUILD", one["events"])
            self.assertEqual(one["history"], 0)
        # Declining the Design-folder discard prompt changes nothing.
        self.assertEqual(out["noSpace"], {"ok": False, "marker": "old", "events": []})
        # A candidate with problems is refused before any state or preview owner is touched.
        self.assertIn("could not build", out["refusal"])
        self.assertEqual(out["marker"], "old")
        # A different Space at install time is stale, never applied.
        self.assertTrue(out["stale"])

    def test_ai_help_ui_is_wired_without_a_provider_and_dictation_is_optional(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        actions = html[html.index('id="bin-actions"'):html.index('id="stack-note"')]
        self.assertLess(actions.index('id="designer-duplicate"'), actions.index('id="ai-help-open"'))
        self.assertRegex(html, r'<button[^>]*id="ai-help-dictate"[^>]*\shidden')
        section = APP[APP.index("// ------------------------------------------------------------ AI Help (Fix 073)"):
                      APP.index("// New Bin (B1)")]
        self.assertNotIn("fetch(", section)
        self.assertEqual(sorted(set(re.findall(r'api\("(/[^"]+)"', section))),
                         ["/api/ai/candidate", "/api/ai/prompt", "/api/ai/repair-prompt"])
        script = "\n".join([function_source("aiSpeechRecognitionClass", APP), r"""
const none=aiSpeechRecognitionClass({}),moz=aiSpeechRecognitionClass({SpeechRecognition:'A'}),
  webkit=aiSpeechRecognitionClass({webkitSpeechRecognition:'B'});
process.stdout.write(JSON.stringify({none,moz,webkit}));"""])
        self.assertEqual(node_json(script), {"none": None, "moz": "A", "webkit": "B"})



if __name__ == "__main__":
    unittest.main()
