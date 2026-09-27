"""Focused, non-browser checks for Fix 071B state and preview transport."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from dataclasses import replace
from organizer_engine import BoxSpec, SideOpeningSpec, StackSpec, SIDE_OPENING_WIDTHS
from organizer_side_openings import (
    SIDE_OPENING_CORNER_MARGIN_MM, side_opening_allowed_sizes, validate_side_openings,
)
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
    def test_space_canvas_switch_remembers_design_view_and_uses_space_renderer(self):
        source = function_source("activatePreviewView", APP) + "\n" + function_source("preferredDesignView", APP)
        script = r"""
const events=[],state={folderMode:'space',runtime:{hosted:false},lastDesignView:'3d'};
const make=()=>({active:false,classList:{toggle(_name,on){this.active=on},
  remove(){},add(){}},setAttribute(){},tabIndex:0,offsetWidth:1});
const tabs={'2d':make(),'3d':make()},wraps={'2d':make(),'3d':make(),drawer:make()};
const $=s=>s.startsWith('.view-tab')?tabs[s.match(/data-view="([^"]+)/)[1]]:
  s.startsWith('.canvas-wrap')?wraps[s.match(/data-canvas="([^"]+)/)[1]]:null;
const $$=s=>s==='.view-tab'?Object.values(tabs):Object.values(wraps);
const updatePreviewHelp=()=>{},updateDividerEditBreadcrumb=()=>{},updateNudgeUI=()=>{};
const requestAnimationFrame=fn=>fn(),renderPreview3D=()=>events.push('3d'),
  renderLayout2D=()=>events.push('2d'),DV={render:()=>events.push('space')};
__SOURCE__
activatePreviewView('2d');activatePreviewView('drawer');
const inSpace={remembered:preferredDesignView(),canvases:Object.fromEntries(Object.entries(wraps).map(([k,v])=>[k,v.classList.active]))};
activatePreviewView(preferredDesignView());
process.stdout.write(JSON.stringify({inSpace,after:Object.fromEntries(Object.entries(wraps).map(([k,v])=>[k,v.classList.active])),events}));
""".replace("__SOURCE__", source)
        out = node_json(script)
        self.assertEqual(out["inSpace"], {"remembered": "2d", "canvases": {"2d": False, "3d": False, "drawer": True}})
        self.assertEqual(out["after"], {"2d": True, "3d": False, "drawer": False})
        self.assertEqual(out["events"], ["2d", "space", "2d"])

    def test_invalid_overlay_is_latest_preview_owned_for_hard_and_structured_errors(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("setDesignInvalidOverlay", "refreshPreview"))
        script = r"""
const overlays={"#design-invalid-overlay-3d":{hidden:true,message:{textContent:''}},
  "#design-invalid-overlay-2d":{hidden:true,message:{textContent:''}}};
const status={textContent:'',classList:{remove(){},add(){}}};
const $=(s,within)=>s==='.design-invalid-message'?within.message:
  s==='#preview-state'?status:overlays[s];
const state={design:{layout:{features:[]}},previewRequest:0,lidThicknessEpoch:0};
let fullPreviewStarts=0,plainErrors=0;
const previewClientId='C',SP={renderSpaceInfo(){}},beginPreviewWait=()=>{},endPreviewWait=()=>{},
  updateGenerateAvailability=()=>{},clearLidThicknessReport=()=>{},updateAutoExpandButton=()=>{};
const setError=()=>{plainErrors++};
const pending=[];
const api=()=>new Promise((resolve,reject)=>pending.push({resolve,reject}));
const adoptPreviewResult=r=>setDesignInvalidOverlay(r.fits?'':r.message);
__SOURCE__
const shown=()=>Object.values(overlays).map(o=>[o.hidden,o.message.textContent]);
(async()=>{
 const old=refreshPreview(),latest=refreshPreview();
 pending[1].resolve({fits:true});await latest;
 pending[0].resolve({fits:false,message:'old problem'});await old;
 const stale=shown();
 const hard=refreshPreview(),cleared=shown();
 pending[2].reject(new Error('current failure'));await hard;
 const failed=shown();
 const next=refreshPreview(),newRequestCleared=shown();
 pending[3].resolve({fits:false,message:'current invalid'});await next;
 process.stdout.write(JSON.stringify({stale,cleared,failed,newRequestCleared,structured:shown(),plainErrors}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        out = node_json(script)
        self.assertTrue(all(hidden for hidden, _ in out["stale"]))
        self.assertTrue(all(hidden for hidden, _ in out["cleared"]))
        self.assertEqual(out["failed"], [[False, "current failure"], [False, "current failure"]])
        self.assertTrue(all(hidden for hidden, _ in out["newRequestCleared"]))
        self.assertEqual(out["structured"], [[False, "current invalid"], [False, "current invalid"]])
        self.assertEqual(out["plainErrors"], 4)  # request-start clearing only; no hard-error footer echo
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        drawer = html[html.index('data-canvas="drawer"'):html.index('data-canvas="2d"')]
        self.assertNotIn("design-invalid-overlay", drawer)
        self.assertIn('font-size: 24px', (ROOT / "web" / "styles.css").read_text(encoding="utf-8"))

    def test_ai_candidate_name_keeps_free_suffix_and_renumbers_collisions(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("aiTypedSpaceActive", "aiResolveCandidateName"))
        script = r"""
const state={folderMode:'space',designInventoryId:'B1'};
const DL={active:true,layout:{},bins:[{id:'B1',name:'Lipstick'},{id:'B2',name:'Other'}]};
__SOURCE__
const resolve=(name,excludeCurrent)=>aiResolveCandidateName(name,{excludeCurrent});
const freeSuffix=resolve(' Lipstick (2) ',false);
const firstCollision=resolve('lipstick',false);
DL.bins.push({id:'B3',name:'LIPSTICK (2)'});
const suffixCollision=resolve('Lipstick (2)',false);
const modifyingOwn=resolve('Lipstick',true);
const newAgainstOwn=resolve('Lipstick',false);
process.stdout.write(JSON.stringify({freeSuffix,firstCollision,suffixCollision,modifyingOwn,newAgainstOwn}));
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {
            "freeSuffix": "Lipstick (2)", "firstCollision": "lipstick (2)",
            "suffixCollision": "Lipstick (3)", "modifyingOwn": "Lipstick",
            "newAgainstOwn": "Lipstick (3)",
        })

    def test_ai_recent_descriptions_save_only_per_space_and_failure_is_nonblocking(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("aiTypedSpaceActive", "aiRecordRecentDescription"))
        script = r"""
const warnings=[],state={folderMode:'space'};
const DL={active:true,layout:{settings:{ai_design_recent_descriptions:[]}},
  change:fn=>{fn();return true},save:async()=>DL.saveOk};
const aiRenderRecentDescriptions=()=>{},toast=m=>warnings.push(m);
__SOURCE__
(async()=>{
  DL.saveOk=true;
  for(let i=0;i<11;i++)await aiRecordRecentDescription(' Object '+i+' ');
  await aiRecordRecentDescription('object 5');
  const recent=[...DL.layout.settings.ai_design_recent_descriptions];
  DL.saveOk=false;await aiRecordRecentDescription('unsaved description');
  state.folderMode='design';await aiRecordRecentDescription('outside Space');
  process.stdout.write(JSON.stringify({recent,current:DL.layout.settings.ai_design_recent_descriptions,
    warnings}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        out = node_json(script)
        self.assertEqual(len(out["recent"]), 10)
        self.assertEqual(out["recent"][0], "object 5")
        self.assertNotIn("Object 0", out["recent"])
        self.assertEqual(out["current"][0], "unsaved description")
        self.assertNotIn("outside Space", out["current"])
        self.assertEqual(len(out["warnings"]), 1)

    def test_bore_angle_proves_growth_before_mutating_and_cancel_keeps_draft(self):
        source = function_source("commitBoreAngleChange", APP)
        script = r"""
const clone=v=>JSON.parse(JSON.stringify(v)),events=[];
const state={design:{box:{x:32,y:32},layout:{features:[{kind:'bore'}]}},
  draft:{kind:'bore',zone:[-8,-8,8,8],options:{angle:0}},boreEpoch:0};
const input={dataset:{draft:'option:angle'},value:'80'};
let targetX=40,accepted=false,spaceError=null;
const number=(v,f=0)=>Number.isFinite(Number(v))?Number(v):f,fmt=v=>String(v);
const draftCommitIndex=()=>0,boreXyMode=()=> 'manual',
  boreDefaultAngleDirection=()=> 'back';
const sizeBoreToGrid=(candidate,{syncFields})=>{
  events.push('size-candidate:'+syncFields);
  candidate.zone=[-12,-8,12,8];
};
const api=async(_path,body)=>{events.push('probe:'+body.design.layout.features[0].options.angle);
  events.push('zone:'+body.design.layout.features[0].zone.join(','));
  return{design:{...body.design,box:{...body.design.box,x:targetX}},box:{x:targetX,y:32}}};
const aiSpaceViolation=()=>spaceError;
const appConfirmAction=async()=>{events.push('confirm');return accepted};
const updateDraftFromFields=()=>{events.push('mutate');state.draft.options.angle=10;state.boreEpoch++};
const refreshDraftSoon={cancel:()=>events.push('cancel-refresh')};
const autoExpandBin=async()=>{events.push('grow');return 'done'};
const renderDraftFields=()=>{},renderPlaced=()=>{},refreshPreview=async()=>{},
  toast=message=>events.push('toast:'+message);
__SOURCE__
const run=async()=>{events.length=0;state.draft.options.angle=0;state.boreEpoch=0;input.value='80';
 await commitBoreAngleChange({currentTarget:input});
 return{angle:state.draft.options.angle,value:input.value,events:[...events]}};
(async()=>{
 const cancel=await run();accepted=true;
 const grow=await run();targetX=32;
 const fit=await run();targetX=40;spaceError='too large';
 const impossible=await run();
 process.stdout.write(JSON.stringify({cancel,grow,fit,impossible}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        out = node_json(script)
        self.assertEqual((out["cancel"]["angle"], out["cancel"]["value"]), (0, "90"))
        lead = ["size-candidate:false", "probe:10", "zone:-12,-8,12,8"]
        self.assertEqual(out["cancel"]["events"], lead + ["confirm"])
        self.assertEqual(out["grow"]["events"], lead + ["confirm", "mutate", "cancel-refresh", "grow"])
        self.assertEqual(out["fit"]["events"], lead + ["mutate"])
        self.assertEqual(out["impossible"]["angle"], 0)
        self.assertNotIn("confirm", out["impossible"]["events"])

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
  preferredDesignView:()=> '2d',
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
ctx.preferredDesignView=()=> '2d';
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
        self.assertEqual(out["afterSuccess"], ["design", ["pending:design", "select:B2", "mode:design", "view:2d", "pending:null"]])






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

    def test_side_opening_browser_size_filter_matches_python_validator(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("sideOpeningSideSpan", "sideOpeningVerticalFits", "sideOpeningAllowedSizes"))
        cases = [
            ("curved", 0.0, 0.0, False, 32.0),
            ("square", 35.0, 0.0, False, 32.0),
            ("curved", 10.0, 25.0, True, 32.0),
            ("square", 35.0, 25.0, True, 32.0),
            ("curved", 40.0, 35.0, True, 20.0),
        ]
        designs = []
        for shape, bottom, top, bridged, height in cases:
            designs.append({"box": {
                "x": 48.0, "y": 40.0, "z": height, "base_thickness": 0.6,
                "stack": {"enabled": bridged},
                "side_openings": {"enabled": True, "sides": ["front", "right"],
                                  "shape": shape, "size": "small",
                                  "from_bottom_percent": bottom, "from_top_percent": top},
            }})
        catalog = {"side_openings": {"corner_margin_mm": SIDE_OPENING_CORNER_MARGIN_MM,
                                      "sizes": [{"value": key, "width_mm": value}
                                                for key, value in SIDE_OPENING_WIDTHS.items()]}}
        script = r"""
const designs=__DESIGNS__,state={catalog:__CATALOG__};
const number=(v,f=0)=>Number.isFinite(Number(v))?Number(v):f;
const sideOpeningState=d=>d.box.side_openings;
__SOURCE__
process.stdout.write(JSON.stringify(designs.map(d=>sideOpeningAllowedSizes(d))));
""".replace("__DESIGNS__", json.dumps(designs)).replace("__CATALOG__", json.dumps(catalog)).replace("__SOURCE__", source)
        offered = node_json(script)
        for design, js_allowed in zip(designs, offered):
            data = design["box"]
            so = data["side_openings"]
            box = BoxSpec(data["x"], data["y"], data["z"],
                          stack=StackSpec(mode="direct" if data["stack"]["enabled"] else "none"))
            spec = SideOpeningSpec(enabled=True, sides=tuple(so["sides"]),
                                   shape=so["shape"], size="small",
                                   from_bottom_percent=so["from_bottom_percent"],
                                   from_top_percent=so["from_top_percent"])
            expected = side_opening_allowed_sizes(box, spec)
            self.assertEqual(js_allowed, list(expected), so)
            for size in SIDE_OPENING_WIDTHS:
                candidate = replace(box, side_openings=replace(spec, size=size))
                if size in expected:
                    validate_side_openings(candidate)
                else:
                    with self.assertRaises(ValueError, msg=(so, size)):
                        validate_side_openings(candidate)

    def test_ai_help_envelope_session_and_space_rules(self):
        source = "\n".join(function_source(name, APP) for name in (
            "aiParseEnvelope", "aiCheckSession", "aiSpaceViolation",
            "pegboardProductMinimums"))
        error_class = APP[APP.index("class AiHelpError"):APP.index("\n}\n", APP.index("class AiHelpError")) + 3]
        schema = re.search(r'const AI_SCHEMA = "([^"]+)"', APP).group(1)
        script = r"""
__ERROR__
const AI_SCHEMA='__SCHEMA__',number=(v,f=0)=>{const n=Number(v);return Number.isFinite(n)?n:f},fmt=v=>String(v);
let draft=false,key='K1',space={kind:'drawer',x:80,y:80,z:50};
const state={folderMode:'space',get activeSpace(){return space},catalog:{base_unit:8}};
const draftNeedsSaving=()=>draft,edgeMountActive=d=>Boolean(d.box.edge_mount?.active);
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
  aiSpaceViolation({box:{x:32,y:32,z:60,pegboard:{...base.box.pegboard,cleat_x:'3'}}},base),
  aiSpaceViolation({box:{x:32,y:32,z:40,pegboard:base.box.pegboard}},base));
space={kind:'pegboard',x:200,y:200,z:100,pegboard_standard:'skadis'};
const sk={box:{pegboard:{enabled:true,standard:'skadis'}}};
rules.push(aiSpaceViolation({box:{x:64,y:32,z:60,pegboard:sk.box.pegboard}},sk),
  aiSpaceViolation({box:{x:48,y:32,z:60,pegboard:sk.box.pegboard}},sk));
process.stdout.write(JSON.stringify({parsed,sessions,rules}));
""".replace("__ERROR__", error_class).replace("__SCHEMA__", schema).replace("__FUNCTIONS__", source)
        out = node_json(script)
        self.assertEqual(out["parsed"][:2], ["R", "R"])
        self.assertTrue(all(out["parsed"][2:]))
        self.assertEqual(out["sessions"][0], None)
        self.assertEqual(out["sessions"][1:], ["stale", "stale", "stale"])
        self.assertIsNone(out["rules"][0])
        self.assertTrue(all(out["rules"][1:4]))
        self.assertIsNone(out["rules"][4])
        self.assertTrue(all(out["rules"][5:8]))  # missing mount, changed cleat, Standard below 48 mm tall
        self.assertIsNone(out["rules"][8])
        self.assertTrue(out["rules"][9])  # SKÅDIS below 56 mm wide

    def test_ai_help_explicit_adoption_preserves_or_creates_identity_without_rebuild(self):
        source = "\n".join(function_source(name, APP) for name in (
            "aiIdentityKey", "aiSpaceContext", "aiTypedSpaceActive", "aiResolveCandidateName",
            "aiInstallCandidate", "aiProveCandidate", "aiCheckSession"))
        error_class = APP[APP.index("class AiHelpError"):APP.index("\n}\n", APP.index("class AiHelpError")) + 3]
        script = r"""
__ERROR__
const clone=v=>JSON.parse(JSON.stringify(v)),events=[],previewClientId='C';
const old={part_name:'Lipstick',box:{x:16},marker:'old',layout:{features:[]}},
  proven={part_name:'Lipstick',marker:'ai',box:{x:32},layout:{features:[]}};
const state={folderMode:'space',activeSpace:{kind:'drawer',x:80,y:80,z:50},activeSpaceId:'S',
  designInventoryId:'B1',design:old,cleanDesign:old,previewRequest:0,history:[1]};
const DL={active:true,layout:{},bins:[{id:'B1',name:'Lipstick'},{id:'B2',name:'Lipstick (2)'}]};
const aiHelp={generation:0};let fullPreviewStarts=0,unsaved=false,confirmed=true,next={problems:[]};
const aiContextKey=()=>'K',aiSetStatus=()=>{},typedSpaceOrdinaryBin=()=>true;
const withDeferredDraftSwitch=action=>action({}),beginDesignMutation=()=>true,finishDesignMutation=()=>{};
const resetNestPhotoSession=()=>{},bindLidMemoryForDesign=()=>{},syncForm=()=>{},clearDraftSelection=()=>{};
const DP={setMode:()=>{}},activatePreviewView=()=>{},freshDesignForCurrentFolder=()=>({marker:'starter'});
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
const session=()=>({request_id:'R',context_fingerprint:'F',baseline:old,
  contextKey:JSON.stringify({identity:aiIdentityKey()})});
(async()=>{
  const run=async mode=>{
    events.length=0;state.design=clone(old);state.designInventoryId='B1';
    const ok=await aiInstallCandidate(candidate(),session(),mode);
    return {ok,marker:state.design.marker,id:state.designInventoryId,name:state.design.part_name,events:[...events],
      previews:fullPreviewStarts,history:state.history.length,clean:state.cleanDesign.marker};
  };
  const reuse=await run('modify'), fresh=await run('new');
  unsaved=true;confirmed=false;state.activeSpace=state.activeSpace;
  const noSpace=(state.folderMode='design',state.activeSpace=null,state.activeSpaceId=null,
    await (async()=>{events.length=0;state.design=clone(old);const ok=await aiInstallCandidate(candidate(),
      {request_id:'R',context_fingerprint:'F',baseline:old,contextKey:JSON.stringify({identity:aiIdentityKey()})},'new');
      return {ok,marker:state.design.marker,events:[...events]}})());
  state.folderMode='space';state.activeSpace={kind:'drawer',x:80,y:80,z:50};state.activeSpaceId='S';
  state.design=clone(old);events.length=0;next={problems:['post: does not fit'],design:proven};
  let refusal=null;
  try{await aiProveCandidate({design:{},request_id:'R',context_fingerprint:'F'},{...session(),contextKey:'K'})}
  catch(e){refusal=e.message}
  const stale=await(async()=>{state.design=clone(old);const bound=session();state.activeSpaceId='OTHER';
    try{await aiInstallCandidate(candidate(),bound,'modify');return null}catch(e){return e.stale}})();
  process.stdout.write(JSON.stringify({reuse,fresh,noSpace,refusal,marker:state.design.marker,stale}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__ERROR__", error_class).replace("__FUNCTIONS__", source)
        out = node_json(script)
        self.assertEqual((out["reuse"]["previews"], out["fresh"]["previews"]), (1, 2))  # one owner claim each
        # Modify keeps its row and nonblank name; New uses the first free suffix.
        self.assertEqual((out["reuse"]["ok"], out["reuse"]["marker"], out["reuse"]["id"]), (True, "ai", "B1"))
        self.assertEqual(out["reuse"]["name"], "Lipstick")
        self.assertEqual(out["reuse"]["events"], ["invalidate", "adopt", "persist:true"])
        # Remembered Space defaults follow ordinary edit rules: a reused bin keeps its own
        # clean baseline; a new AI bin starts from the unedited starter, never the candidate.
        self.assertEqual((out["reuse"]["clean"], out["fresh"]["clean"]), ("old", "starter"))
        # Meaningful bin: saved first, then the AI result is a brand-new bin.
        self.assertEqual((out["fresh"]["ok"], out["fresh"]["marker"], out["fresh"]["id"]), (True, "ai", None))
        self.assertEqual(out["fresh"]["name"], "Lipstick (3)")
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

    def test_ai_help_prompt_covers_committed_draft_and_only_answer_defects_are_repairable(self):
        error_class = APP[APP.index("class AiHelpError"):APP.index("\n}\n", APP.index("class AiHelpError")) + 3]
        source = "\n".join(function_source(name, APP) for name in (
            "aiGeneratePrompt", "aiProcessResponse", "aiProveCandidate", "aiParseEnvelope", "aiCheckSession"))
        schema = re.search(r'const AI_SCHEMA = "([^"]+)"', APP).group(1)
        script = r"""
__ERROR__
const AI_SCHEMA='__SCHEMA__',clone=v=>JSON.parse(JSON.stringify(v)),previewClientId='C';
const statuses=[],sent=[],events=[];let refuse=false,answer='',mode='';
const state={design:{part_name:'',layout:{features:[]}}};
const aiHelp={session:null,busy:false,generation:0,failure:null,generatedFor:null};
const $=selector=>({value:selector==='#ai-help-description'?'A tray':answer,close:()=>events.push('close')});
const aiSetBusy=b=>{aiHelp.busy=b},aiUpdateGenerateAvailability=()=>{},
  aiSetStatus=(m,o={})=>statuses.push({m,repair:Boolean(o.repair)});
const aiShowPrompt=()=>{},toast=()=>{},isStructuralDesign=()=>false,aiCompositionEmpty=d=>!d.layout.features.length;
const aiSpaceContext=()=>null,aiExistingBinNames=()=>['Existing'],aiRecordRecentDescription=()=>{},
  aiContextKey=()=>'K',visibleDesignSnapshot=()=>clone(state.design);
const withDeferredDraftSwitch=async(action,refused)=>{
  events.push('guard');if(refuse)return refused;
  state.design.layout.features.push({kind:'post'});events.push('committed');return action({});};
const api=async(path,body)=>{
  if(path==='/api/ai/prompt'){sent.push(clone(body));return{request_id:'R',context_fingerprint:'F',prompt:'P'};}
  if(mode==='400')throw Object.assign(new Error('bad design'),{status:400});
  if(mode==='500')throw Object.assign(new Error('boom'),{status:500});
  if(mode==='network')throw new TypeError('Failed to fetch');
  return{problems:[],design:{},preview:{}};};
const aiSpaceViolation=()=>null;
let installError=null,installResult=true;
const aiInstallCandidate=async()=>{if(installError)throw installError;return installResult;};
__FUNCTIONS__
const envelope=JSON.stringify({schema:AI_SCHEMA,request_id:'R',context_fingerprint:'F',assumptions:[],design:{box:{}}});
(async()=>{
  await aiGeneratePrompt();
  const prompt={features:sent[0].design.layout.features.length,order:[...events],session:Boolean(aiHelp.session),
    names:sent[0].design.part_name,existing:sent[0].existing_names,generatedFor:aiHelp.generatedFor};
  events.length=0;refuse=true;aiHelp.session=null;await aiGeneratePrompt();
  const refused={session:aiHelp.session,last:statuses.at(-1).m};refuse=false;
  await aiGeneratePrompt();
  const run=async(label,setup)=>{mode='';await aiGeneratePrompt();events.length=0;statuses.length=0;
    aiHelp.failure=null;installError=null;installResult=true;
    answer=envelope;setup();await aiProcessResponse('modify');
    const last=statuses.at(-1);return{label,repair:last.repair,failure:Boolean(aiHelp.failure),
      session:Boolean(aiHelp.session),generatedFor:aiHelp.generatedFor,closed:events.includes('close')};};
  const out=[];
  out.push(await run('junk',()=>{answer='not json';}));
  out.push(await run('ok',()=>{}));
  out.push(await run('rejected',()=>{mode='400';}));
  out.push(await run('service',()=>{mode='500';}));
  out.push(await run('network',()=>{mode='network';}));
  out.push(await run('applyFailed',()=>{installError=new AiHelpError('x',{operational:true,applied:true});}));
  out.push(await run('unexpected',()=>{installError=new Error('kaboom');}));
  out.push(await run('stale',()=>{installError=new AiHelpError('old',{stale:true});}));
  process.stdout.write(JSON.stringify({prompt,refused,out}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__ERROR__", error_class).replace("__SCHEMA__", schema).replace("__FUNCTIONS__", source)
        out = node_json(script)
        # The prompt is written from the design AFTER a meaningful draft was committed.
        self.assertEqual(out["prompt"], {"features": 1, "order": ["guard", "committed"],
                                          "session": True, "names": "", "existing": ["Existing"],
                                          "generatedFor": "A tray"})
        self.assertEqual(out["refused"]["session"], None)
        self.assertIn("Finish or discard", out["refused"]["last"])
        by = {one["label"]: one for one in out["out"]}
        # Only a defect in the answer itself is handed back to the AI.
        for label in ("junk", "rejected"):
            self.assertEqual((by[label]["repair"], by[label]["failure"]), (True, True), label)
        for label in ("service", "network", "applyFailed", "unexpected", "stale"):
            self.assertEqual((by[label]["repair"], by[label]["failure"]), (False, False), label)
        self.assertFalse(by["applyFailed"]["session"])  # applied: the old prompt is spent
        self.assertIsNone(by["stale"]["generatedFor"])  # same description can regenerate
        self.assertTrue(by["ok"]["closed"])

    def test_ai_help_context_key_covers_bin_name_and_draft(self):
        source = "\n".join(function_source(name, APP) for name in ("aiContextKey", "aiIdentityKey", "aiSpaceContext"))
        script = r"""
const state={folderMode:'space',activeSpaceId:'S',designInventoryId:'B1',activeSpace:{kind:'drawer',x:80,y:80,z:50}};
let design={part_name:'Tray',box:{x:16}},draft=null;
const visibleDesignSnapshot=()=>JSON.parse(JSON.stringify(design)),isStructuralDesign=()=>false;
const draftNeedsSaving=()=>Boolean(draft);state.draft=null;
const pegboardProductMinimums=()=>({x:0,z:48});
__FUNCTIONS__
const keys=[aiContextKey()];
design={part_name:'Renamed',box:{x:16}};keys.push(aiContextKey());
design={part_name:'Tray',box:{x:24}};keys.push(aiContextKey());
design={part_name:'Tray',box:{x:16}};draft=true;state.draft={kind:'post'};keys.push(aiContextKey());
draft=null;state.draft=null;state.designInventoryId='B2';keys.push(aiContextKey());
process.stdout.write(JSON.stringify({distinct:new Set(keys).size}));
""".replace("__FUNCTIONS__", source)
        out = node_json(script)
        self.assertEqual(out["distinct"], 5)  # name, size, open draft and bin identity each change the key

    def test_ai_help_ui_is_wired_without_a_provider_and_dictation_is_optional(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        actions = html[html.index('id="bin-actions"'):html.index('id="stack-note"')]
        self.assertIn('id="designer-duplicate"', actions)
        options = html[html.index('data-section="parts-options"'):html.index('id="ai-help-open"') + 50]
        self.assertIn('id="ai-help-open"', options)
        self.assertRegex(html, r'<button[^>]*id="ai-help-dictate"[^>]*\shidden')
        # Product name is "AI Design"; internal ai-help-* IDs are implementation detail only.
        dialog = html[html.index('id="ai-help-dialog"'):html.index('</dialog>', html.index('id="ai-help-dialog"'))]
        self.assertIn("AI Design", html[html.index('id="ai-help-open"'):html.index("</button>", html.index('id="ai-help-open"'))])
        self.assertIn(">AI Design<", dialog)
        self.assertNotIn("AI Help", dialog)
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
