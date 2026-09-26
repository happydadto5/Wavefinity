"""Focused, non-browser checks for Fix 071B state and preview transport."""

from __future__ import annotations

import json
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


class PreviewPickTransportTests(unittest.TestCase):
    def test_storage_box_divider_has_compact_mesh_pick_identity(self):
        design = default_design()
        design["box"].update(x=64, y=48, z=40, b4b={"enabled": True})
        feature = default_feature_payload({"design": design, "kind": "divider"})["feature"]
        design["layout"]["features"] = [feature]
        preview = json.loads(json.dumps(preview_payload({"design": design})))
        self.assertEqual(len(preview["pick_meshes"]), 1)
        pick = preview["pick_meshes"][0]
        self.assertEqual(pick["pick"], {"type": "saved", "index": 0})
        mesh = preview["meshes"][pick["mesh_index"]]
        self.assertEqual((mesh["kind"], mesh["owner"]), ("feature_divider", "base"))
        self.assertTrue(mesh["positions"])
        draft = preview_payload({"design": design, "draft": feature, "selected": 0})
        self.assertEqual(draft["pick_meshes"][0]["pick"], {"type": "draft"})

    def test_same_kind_and_draft_ids_survive_json_boundary(self):
        design = default_design()
        design["box"].update(x=64, y=64)
        feature = default_feature_payload({"design": design, "kind": "post"})["feature"]
        design["layout"]["features"] = [
            {**feature, "zone": [-24, -8, -8, 8]},
            {**feature, "zone": [8, -8, 24, 8]},
        ]
        preview = json.loads(json.dumps(preview_payload({"design": design})))
        ids = {tuple(face["pick"].items()) for face in preview["geometry"] if face["pick"]}
        self.assertIn((("type", "saved"), ("index", 0)), ids)
        self.assertIn((("type", "saved"), ("index", 1)), ids)
        self.assertTrue(all(face["owner"] is None for face in preview["geometry"] if face["pick"]))

        draft = {**feature, "zone": [-8, 10, 8, 26]}
        preview = json.loads(json.dumps(preview_payload({"design": design, "draft": draft})))
        self.assertTrue(any(face["pick"] == {"type": "draft"} for face in preview["geometry"]))

    def test_shared_recessed_nests_have_separate_nonprinting_proxies(self):
        design = _fix21_photo_design()["design"]
        design = duplicate_feature_payload({"design": design, "index": 0})["design"]
        preview = json.loads(json.dumps(preview_payload({"design": design})))
        self.assertEqual([proxy["pick"]["index"] for proxy in preview["pick_proxies"]], [0, 1])
        self.assertTrue(all(len(proxy["points"]) >= 3 for proxy in preview["pick_proxies"]))
        self.assertFalse(any(face["pick"] for face in preview["geometry"]
                             if face["kind"] == "feature_nest"))


class BrowserStateLogicTests(unittest.TestCase):
    def test_primary_and_legacy_preview_proxy_paths_execute_with_visibility(self):
        names = ["drawOverlay2D", "drawGeometryLegacy2D", "addPreviewPickFace", "addPreviewPickProxies"]
        source = "\n".join(function_source(name, APP) for name in names)
        script = r"""
const camera={yaw:0,elevation:40,zoom:1};
const state={previewSupportPolygons:[],previewPickMeshContext:null,
  preview:{pick_proxies:[{points:[[0,0,1],[1,0,1],[0,1,1]],pick:{type:'saved',index:0}}]},
  design:{box:{x:8,y:8,z:8}},b4bView:'base',binVisible:true,interiorVisible:false,xrayOn:false};
const ctx={beginPath(){},moveTo(){},lineTo(){},closePath(){},fill(){},stroke(){},fillText(){}};
const b4bEnabled=()=>true,baseTrimEnabled=()=>false,number=v=>Number(v)||0;
const canvasSize=()=>({context:ctx,width:100,height:100}),paintBackdrop=()=>{};
const cameraVector=()=>[0,0,1],currentPreviewClassify=()=>face=>face.owner==='lid'?'lid':'base';
const isFacingBinWall=()=>false,isBinFace=()=>false,iso=p=>p,dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const shadedColor=()=>'#aaa',drawContactShadow=()=>{},drawUsableFloor=()=>{},drawBoreAxes=()=>{};
const draw3DDimensions=()=>{},drawDimensionGhost3D=()=>{},drawFrontMarker=()=>{};
const b4bShadowBox=()=>null,b4bAssembledEnvelope=()=>null,dimensionDragBoxOverride=()=>null;
const dimensionDisplayOverride=()=>null;
__SOURCE__
const face={kind:'feature_divider',normal:[0,0,1],owner:'base',layer:0,
  points:[[0,0,1],[1,0,1],[0,1,1]]};
drawOverlay2D(ctx,100,100,[],[],camera,{midX:0,midY:0,scale:1},()=> 'base',new Set(['base']));
const primary=state.previewSupportPolygons.length;
drawGeometryLegacy2D({},[face],camera);
const legacy=state.previewSupportPolygons.length;
state.b4bView='lid';drawGeometryLegacy2D({},[face],camera);
const hidden=state.previewSupportPolygons.length;
process.stdout.write(JSON.stringify({primary,legacy,hidden}));
""".replace("__SOURCE__", source)
        out = node_json(script)
        self.assertEqual(out, {"primary": 1, "legacy": 1, "hidden": 0})

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

    def test_storage_box_mesh_pick_opens_exact_divider_in_2d(self):
        names = ["pointInPolygon", "pickTriangleDepth", "previewPickDepth", "clickedPreviewSupport",
                 "clickedPreviewMesh", "selectFromPreview"]
        source = "\n".join(function_source(name, APP) for name in names)
        script = r"""
const design={},space={id:'S'},events=[],state={design,activeSpace:space,
  designInventoryId:'B1',previewRequest:3,selected:null,
  previewSupportPolygons:[],preview:{meshes:[{owner:'base',positions:[0,0,1,10,0,1,0,10,1],
  normals:[0,0,1]}],pick_meshes:[{mesh_index:0,pick:{type:'saved',index:0}}]},
  previewPickMeshContext:{camera:{},project:p=>[p[0],p[1]],visibleGroups:new Set(['base'])}};
const DP={mode:'design'},cameraVector=()=>[0,0,1],iso=p=>p,
  dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const selectedFeature=async i=>{state.selected=i;events.push('select:'+i);return true};
const $=()=>({textContent:'',classList:{add(){},remove(){}}});
const activatePreviewView=v=>events.push(v),renderLayout2D=()=>{};
const localStorage={getItem:()=> '1'};
__SOURCE__
(async()=>{
  const pick=clickedPreviewSupport({getBoundingClientRect:()=>({left:0,top:0})},
    {clientX:2,clientY:2});
  await selectFromPreview(pick,{design,space,source:'B1',preview:3});
  process.stdout.write(JSON.stringify({pick,events,selected:state.selected}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        out = node_json(script)
        self.assertEqual(out, {"pick": {"type": "saved", "index": 0},
                               "events": ["select:0", "2d"], "selected": 0})

    def test_delayed_preview_pick_rejects_new_preview_generation(self):
        source = function_source("selectedFeature", APP)
        script = r"""
const design={layout:{features:[{kind:'post',zone:[0,0,8,8]}]}}, space={id:'S'};
const state={design,activeSpace:space,designInventoryId:'B1',previewRequest:7,
  selected:null,draft:{kind:'post'},partZoneLocks:{}};
let release; const guardDraftSwitch=()=>new Promise(resolve=>release=resolve);
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
  release(true);
  const accepted=await pending;
  process.stdout.write(JSON.stringify({accepted,selected:state.selected}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {"accepted": False, "selected": None})

    def test_inventory_edit_pending_and_rollback(self):
        script = r"""
const fs=require('fs'),vm=require('vm');
const ctx={Map,Set,Promise,JSON,Number,String,Object,Date,
  state:{activeSpaceId:'S',output:'folder'},DL:{selectRow:id=>events.push('select:'+id)},
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
        self.assertEqual(out["afterSuccess"], ["design", ["pending:design", "select:B2", "mode:design", "pending:null"]])

    def test_bore_derived_display_and_manual_minimum_are_separate(self):
        helpers = "\n".join((APP[APP.index("const roundUpHalfMm ="):APP.index("\n", APP.index("const roundUpHalfMm ="))],
                             APP[APP.index("const roundNearestHalfMm ="):APP.index("\n", APP.index("const roundNearestHalfMm ="))],
                             APP[APP.index("const boreDerivedDimension ="):APP.index("\nfunction roundFitZoneUpHalfMm", APP.index("const boreDerivedDimension ="))]))
        script = "const number=(v,f)=>Number.isFinite(Number(v))?Number(v):f;" + helpers + "\n" + \
                 "const exact=57.695;process.stdout.write(JSON.stringify({auto:exact,shown:boreDerivedDimension('height',exact),manual:roundUpHalfMm(exact),angle:boreDerivedDimension('angle',17)}));"
        self.assertEqual(node_json(script), {"auto": 57.695, "shown": 57.5, "manual": 58, "angle": 17})
        self.assertIn("boreDerivedDimension(key, value)", APP[APP.index("const optionField ="):APP.index("const gridField =")])
        self.assertIn("one.options.height = roundUpHalfMm(resolvedHeight)", APP)

    def test_3d_pick_switches_after_selection_invalidates_old_preview_and_remembers_help(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("wireSupportLayoutDialog", "selectFromPreview"))
        script = r"""
const design={}, space={id:'S1'}, state={design,activeSpace:space,designInventoryId:'B1',
  previewRequest:4,selected:null,draft:null};
const DP={mode:'design'}, events=[], saved={};
const dialog={open:false,showModal(){this.open=true;events.push('help')},close(){this.open=false;
  this.handlers.close()},addEventListener(name,fn){this.handlers[name]=fn},handlers:{}};
const els={'#support-layout-dialog':dialog,'#support-layout-dialog-open':{addEventListener(){}},
  '#support-layout-remember':{checked:true},'#preview-state':{textContent:'',classList:{add(){},remove(){}}}};
const $=s=>els[s], localStorage={getItem:k=>saved[k],setItem:(k,v)=>saved[k]=v};
const selectedFeature=async index=>{state.selected=index;state.previewRequest++;events.push('selected');return true};
const activatePreviewView=v=>events.push(v),renderLayout2D=()=>events.push('layout');
__SOURCE__
(async()=>{
  wireSupportLayoutDialog();
  const context=()=>({design,space,source:'B1',preview:state.previewRequest});
  await selectFromPreview({type:'saved',index:0},context());
  const first=events.slice();dialog.close();
  await selectFromPreview({type:'saved',index:0},context());
  const suppressed=events.slice();
  saved['wavefinity-3d-pick-help-dismissed']='0';
  await selectFromPreview({type:'saved',index:0},context());
  process.stdout.write(JSON.stringify({first,suppressed,all:events,saved}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        out = node_json(script)
        self.assertEqual(out["first"], ["selected", "2d", "layout", "help"])
        self.assertEqual(out["suppressed"].count("help"), 1)
        self.assertEqual(out["all"].count("help"), 2)
        self.assertEqual(out["saved"]["wavefinity-3d-pick-help-dismissed"], "0")

    def test_auto_fit_rounds_required_manual_dimensions_up(self):
        source = function_source("roundFitZoneUpHalfMm", APP)
        out = node_json("const number=(v,f)=>Number.isFinite(Number(v))?Number(v):f; "
                        + APP[APP.index("const roundUpHalfMm ="):APP.index("\n", APP.index("const roundUpHalfMm ="))]
                        + source + "process.stdout.write(JSON.stringify(roundFitZoneUpHalfMm([0,0,57.695,16])));")
        self.assertAlmostEqual(out[2] - out[0], 58)
        self.assertAlmostEqual(out[3] - out[1], 16)
        self.assertAlmostEqual((out[0] + out[2]) / 2, 57.695 / 2)

    def test_selection_actions_appear_before_preview_and_failed_guard_keeps_old_target(self):
        source = function_source("selectedFeature", APP)
        script = r"""
const events=[];
const design={layout:{features:[{kind:'post',zone:[0,0,8,8]}]}};
const space={id:'A'};
const state={design,activeSpace:space,designInventoryId:'B1',selected:null,draft:null,
  partZoneLocks:{},paletteBrowsing:true};
const clone=v=>JSON.parse(JSON.stringify(v));
let accept;
const guardDraftSwitch=()=>new Promise(resolve=>{accept=resolve});
const $=()=>({hidden:false}), $$=()=>[];
const resetNestPhotoSession=()=>{}, commitEdgeMountFormBeforeSwitch=()=>true;
const cancelPendingDraftWork=()=>{}, updateNudgeUI=()=>{};
const AUTO_FOOTPRINT_KINDS=new Set();
const updateInteriorModeVisibility=()=>{}, partInfo=()=>({});
const syncDraftEditorIdentity=()=>{}, renderDraftFields=()=>{}, renderPlaced=()=>{};
const updateSelectionButtons=()=>events.push('actions');
const refreshDraft=()=>events.push('preview');
const renderLayout2D=()=>events.push('layout');
__SOURCE__
(async()=>{
  const first=selectedFeature(0);
  const pending=[state.selected,events.slice()];
  accept(false); const refused=await first;
  const afterFailure=[state.selected,events.slice()];
  const second=selectedFeature(0);
  accept(true); const accepted=await second;
  const afterSuccess=[state.selected,events.slice()];
  state.selected=null; events.length=0;
  const stale=selectedFeature(0);
  state.activeSpace={id:'B'}; accept(true);
  const staleAccepted=await stale;
  process.stdout.write(JSON.stringify({pending,refused,afterFailure,accepted,afterSuccess,staleAccepted,
    staleSelection:state.selected,staleEvents:events}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        out = node_json(script)
        self.assertEqual(out["pending"], [None, []])
        self.assertFalse(out["refused"])
        self.assertEqual(out["afterFailure"], [None, []])
        self.assertTrue(out["accepted"])
        self.assertEqual(out["afterSuccess"], [0, ["actions", "preview", "layout"]])
        self.assertFalse(out["staleAccepted"])
        self.assertIsNone(out["staleSelection"])
        self.assertEqual(out["staleEvents"], [])

    def test_filter_is_session_space_scoped_and_failed_mode_guard_rolls_back(self):
        script = r"""
const fs = require('fs'), vm = require('vm');
const els = {}, calls = [], make = () => ({ hidden:false, classList:{toggle(){},add(){},remove(){}},
  setAttribute(){}, addEventListener(){}, dataset:{} });
const ctx = { Map, Set, Promise, JSON, Number, String, Object, Date,
  $: s => els[s] ||= make(), $$: () => [],
  state: { folderMode:'space', activeSpace:{name:'Same'}, activeSpaceId:'A' },
  DL: { active:true, loaded:true, pegboardRefreshError:false, on(){}, bin:id => ({id}),
    ensureLoaded:async()=>{}, spaceContext:()=>({}), spaceContextCurrent:()=>true },
  DV: {wire(){}}, SP:{renderSpaceInfo(){},offerSpacePlanning(){}},
  document:{body:{classList:{toggle(){}}}}, window:{addEventListener(){}},
  localStorage:{getItem:()=>'{"show":"printed","sort":"name"}',setItem(){}},
  activatePreviewView:v=>calls.push(v), toast(){},
  flushVisibleDesignEditsBeforeModeSwitch:async()=>false, flushSpaceDesignAutosave:async()=>true,
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8')+';this.DP=DP;',ctx);
const DP=ctx.DP;
DP.update=()=>{};
DP.syncFilterSpace();
const fresh=[DP.filter.show,DP.filter.sort];
DP.filter.show='saved'; DP.filtersBySpace.set('A','saved');
ctx.state.activeSpace={name:'Same'}; ctx.state.activeSpaceId='B'; DP.syncFilterSpace();
const other=DP.filter.show;
ctx.state.activeSpace={name:'Renamed'}; ctx.state.activeSpaceId='A'; DP.syncFilterSpace();
const back=DP.filter.show;
(async()=>{
  DP.mode='design';
  const refused=await DP.selectMode('space');
  const unchanged=DP.mode;
  ctx.flushVisibleDesignEditsBeforeModeSwitch=async()=>true;
  const accepted=await DP.selectMode('space');
  process.stdout.write(JSON.stringify({fresh,other,back,refused,unchanged,accepted,mode:DP.mode,calls}));
})().catch(e=>{console.error(e);process.exit(1)});
"""
        out = node_json(script.replace("process.argv[1]", json.dumps(str(ROOT / "web" / "drawer-panel.js"))))
        self.assertEqual(out["fresh"], ["all", "name"])
        self.assertEqual(out["other"], "all")
        self.assertEqual(out["back"], "saved")
        self.assertFalse(out["refused"])
        self.assertEqual(out["unchanged"], "design")
        self.assertTrue(out["accepted"])
        self.assertEqual(out["calls"], ["drawer"])

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

    def test_frontmost_pick_does_not_select_occluded_feature(self):
        names = ["pointInPolygon", "pickTriangleDepth", "previewPickDepth", "clickedPreviewSupport", "clickedPreviewMesh"]
        source = "\n".join(function_source(name, APP) for name in names)
        script = r"""
const state={previewSupportPolygons:[]};
__FUNCTIONS__
const polygon=[[0,0],[10,0],[10,10],[0,10]];
const put=(depth,pick)=>state.previewSupportPolygons.push({polygon,depths:[depth,depth,depth,depth],pick,proxy:false});
put(2,{type:'saved',index:0}); put(5,{type:'saved',index:1});
const canvas={getBoundingClientRect:()=>({left:0,top:0})};
const front=clickedPreviewSupport(canvas,{clientX:5,clientY:5});
put(7,null);
const hidden=clickedPreviewSupport(canvas,{clientX:5,clientY:5});
process.stdout.write(JSON.stringify({front,hidden}));
""".replace("__FUNCTIONS__", source)
        out = node_json(script)
        self.assertEqual(out["front"], {"type": "saved", "index": 1})
        self.assertIsNone(out["hidden"])


if __name__ == "__main__":
    unittest.main()
