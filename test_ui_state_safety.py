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
    def test_designer_history_removed_but_space_undo_remains(self):
        for dead in ("state.history", "state.future", "recordHistory(",
                     "restoreHistory(", "updateHistoryButtons(",
                     "pendingNudgeHistory", "#undo-design", "#redo-design"):
            self.assertNotIn(dead, APP)
        model = (ROOT / "web" / "drawer-model.js").read_text(encoding="utf-8")
        self.assertIn("DL.undo", model)
        self.assertIn("DL.redo", model)

    def test_committed_change_only_clears_starter_for_real_change(self):
        source = function_source("noteCommittedDesignChange", APP)
        script = r"""
const state={design:{box:{x:16}},spaceStarterPreviewPending:true};
__SOURCE__
const same=noteCommittedDesignChange({box:{x:16}});
const stillPending=state.spaceStarterPreviewPending;
state.design.box.x=24;
const changed=noteCommittedDesignChange({box:{x:16}});
state.spaceStarterPreviewPending=true;
const known=noteCommittedDesignChange();
process.stdout.write(JSON.stringify({same,stillPending,changed,known,
 pending:state.spaceStarterPreviewPending}));
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {"same": False, "stillPending": True,
                                            "changed": True, "known": True, "pending": False})

    def test_surface_height_label_resets_without_reload(self):
        source = function_source("syncSurfaceControls", APP)
        script = r"""
const state={shown:true,design:{layout:{},box:{base_thickness:0.6}},
 activeSpace:{trim_size:'medium'}};
const nodes={};
const $=selector=>nodes[selector]??=( {hidden:false,textContent:'',value:'',checked:false} );
const isSurfaceBinDesign=()=>state.shown,surfaceTrimHeight=()=>7.5;
const surfaceStackingBlocked=()=>false,fmt=String;
const document={activeElement:null};
__SOURCE__
const labels=[];
for(const shown of [true,false,true]){
 state.shown=shown;syncSurfaceControls();labels.push($('#z-size-label').textContent);
}
process.stdout.write(JSON.stringify(labels));
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), ["Bin height", "Height", "Bin height"])

    def test_nudge_success_failure_and_stale_response_without_undo_snapshot(self):
        source = APP[APP.index("const commitNudge = debounce("):
                     APP.index("}, 200);", APP.index("const commitNudge = debounce(")) + len("}, 200);")]
        handler = function_source("handleLayoutArrowKeys", APP)
        self.assertIn("if (!pendingNudgeDraft)", handler)
        script = r"""
const clone=v=>JSON.parse(JSON.stringify(v)),debounce=fn=>fn;
const original={kind:'post',zone:[0,0,2,2]};
let pendingNudgeDraft=clone(original),resolveApi,rejectApi,changes=0;
const state={draftRequest:1,selected:0,draft:{kind:'post',zone:[1,0,3,2]},
 design:{layout:{features:[clone(original)]}},spaceStarterPreviewPending:true};
const api=()=>new Promise((resolve,reject)=>{resolveApi=resolve;rejectApi=reject});
const toast=()=>{},renderDraftFields=()=>{},refreshDraft=async()=>{},renderLayout2D=()=>{};
const renderPlaced=()=>{},updateSelectionButtons=()=>{};
const noteCommittedDesignChange=()=>{changes++;state.spaceStarterPreviewPending=false};
__SOURCE__
(async()=>{
 const success=commitNudge(1);
 resolveApi({design:{layout:{features:[clone(state.draft)]}},selected:0});
 await success;
 const afterSuccess={zone:state.draft.zone,pending:pendingNudgeDraft,
  starter:state.spaceStarterPreviewPending,changes};
 state.draftRequest=2;state.draft={kind:'post',zone:[2,0,4,2]};
 pendingNudgeDraft=clone(original);
 const failure=commitNudge(2);rejectApi(Error('rejected'));await failure;
 const afterFailure={zone:state.draft.zone,pending:pendingNudgeDraft,changes};
 state.draftRequest=3;state.draft={kind:'post',zone:[3,0,5,2]};
 pendingNudgeDraft=clone(original);
 const stale=commitNudge(3);
 state.draftRequest=4;state.draft={kind:'post',zone:[4,0,6,2]};
 resolveApi({design:{layout:{features:[{kind:'post',zone:[99,0,101,2]}]}},selected:0});
 await stale;
 process.stdout.write(JSON.stringify({afterSuccess,afterFailure,
  afterStale:{zone:state.draft.zone,pending:pendingNudgeDraft,changes}}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {
            "afterSuccess": {"zone": [1, 0, 3, 2], "pending": None,
                             "starter": False, "changes": 1},
            "afterFailure": {"zone": [0, 0, 2, 2], "pending": None, "changes": 1},
            "afterStale": {"zone": [4, 0, 6, 2], "pending": {"kind": "post", "zone": [0, 0, 2, 2]},
                           "changes": 1},
        })

    def test_reference_add_remove_readd_preserves_only_current_height_authority(self):
        source = "\n".join(function_source(name, APP) for name in (
            "referencePhysicalHeight", "referenceSeedForDraft", "referenceAddReady",
            "updateReferenceAddAvailability", "addReferenceToCurrentDraft",
            "removeReferenceFromCurrentDraft", "markDraftChanged", "commitReferenceEdit"))
        script = r"""
const clone=value=>JSON.parse(JSON.stringify(value));
const number=(value,fallback)=>Number.isFinite(Number(value))?Number(value):fallback;
const _nestMeasuredThickness=()=>null;
const button={hidden:true};
const fields={};
const $=selector=>selector==='#draft-fields'?fields:
 selector==='[data-action="add-reference"]'?(state.draft?.reference_object?null:button):
 {textContent:'',classList:{add(){}}};
const draftCommitIndex=()=>state.selected;
const updateGenerateAvailability=()=>{};
const renderDraftFields=()=>{};
const renderPlaced=()=>{};
const updateSelectionButtons=()=>{};
const refreshPreview=async()=>{};
const calls=[];
const noteCommittedDesignChange=()=>calls.push('change');
const api=async(path,payload)=>{
 calls.push(path);const design=clone(payload.design);
 design.layout.features[payload.index]=clone(payload.feature);
 return {design,selected:payload.index};
};
const toast=()=>{};
const commitReferenceEditSoon=()=>{};commitReferenceEditSoon.cancel=()=>{};
const state={draft:null,design:null,draftRequest:10,referenceResolutionRequest:10,
 draftResolvedOptions:{height:16,lip:1},draftIsNew:false,draftTouched:false,
 draftAutoCommit:true,referenceEditPending:false,selected:0,draftSourceIndex:0};
__SOURCE__
async function lifecycle(kind, options, resolvedOptions){
 state.draft={kind,zone:[-10,-8,10,8],options};state.design={layout:{features:[clone(state.draft)]}};
 state.draftRequest++;state.referenceResolutionRequest=state.draftRequest;
 state.draftResolvedOptions=resolvedOptions;state.draftTouched=false;state.referenceEditPending=false;
 const before=calls.length;
 addReferenceToCurrentDraft();await commitReferenceEdit();
 removeReferenceFromCurrentDraft();await commitReferenceEdit();
 const addVisible=referenceAddReady()&&!button.hidden;
 addReferenceToCurrentDraft();
 const seeded=state.draft.reference_object?.height;
 await commitReferenceEdit();
 return {kind,addVisible,seeded,count:state.design.layout.features.length,
   calls:calls.slice(before).filter(call=>call==='/api/feature/reference').length};
}
(async()=>{
 const cycles=[];
 cycles.push(await lifecycle('slot',{}, {height:16}));
 cycles.push(await lifecycle('steps',{}, {height:16,lip:1}));
 cycles.push(await lifecycle('post',{height:12},{}));
 state.draft={kind:'slot',zone:[-10,-8,10,8],options:{}};
 state.draftRequest=40;state.referenceResolutionRequest=40;state.draftResolvedOptions={height:16};
 state.draftIsNew=false;state.draftTouched=false;state.selected=0;state.draftSourceIndex=0;
 markDraftChanged(false);
 state.draftTouched=false; // holder edit saved; no fresh resolution has arrived
 const afterHolderEdit=referenceAddReady();
 markDraftChanged(true);
 state.draftTouched=false; // reference-only save cannot restore the stale owner
 const afterReferenceEdit=referenceAddReady();
 state.draftRequest++;state.referenceResolutionRequest=state.draftRequest;
 state.draftResolvedOptions={height:18};
 const afterFreshResolution=referenceAddReady();
 process.stdout.write(JSON.stringify({cycles,afterHolderEdit,afterReferenceEdit,afterFreshResolution,
   allCalls:calls.filter(call=>call==='/api/feature/reference').length}));
})();
""".replace("__SOURCE__", source)
        result = node_json(script)
        self.assertEqual(result["cycles"], [
            {"kind": "slot", "addVisible": True, "seeded": 16, "count": 1, "calls": 3},
            {"kind": "steps", "addVisible": True, "seeded": 17, "count": 1, "calls": 3},
            {"kind": "post", "addVisible": True, "seeded": 12, "count": 1, "calls": 3},
        ])
        self.assertFalse(result["afterHolderEdit"])
        self.assertFalse(result["afterReferenceEdit"])
        self.assertTrue(result["afterFreshResolution"])
        self.assertEqual(result["allCalls"], 9)

    def test_reopened_auto_height_reference_waits_for_accepted_draft_response(self):
        source = "\n".join(function_source(name, APP) for name in (
            "referencePhysicalHeight", "referenceSeedForDraft", "referenceAddReady",
            "updateReferenceAddAvailability", "addReferenceToCurrentDraft", "refreshDraft"))
        script = r"""
const number=(value,fallback)=>Number.isFinite(Number(value))?Number(value):fallback;
const _nestMeasuredThickness=()=>null;
const button={hidden:true};
const status={textContent:'',classList:{add(){},remove(){}}};
const $=selector=>selector==='[data-action="add-reference"]'?button:
 selector==='#draft-status'?status:selector==='#draft-fields'?{}:null;
const document={activeElement:null};
const draftCommitIndex=()=>0;
const applyBoreSizing=()=>holderCalls++;
const bumpBoreEpoch=()=>{};
const partInfo=()=>({kind:state.draft.kind,fields:[],flags:{qty:false}});
const autoCommitDraft=async()=>true;
const reconcileBoreBin=async()=>false;
const refreshPreview=async()=>{};
const renderDraftFields=()=>{};
const updateGenerateAvailability=()=>{};
const markDraftChanged=()=>{state.draftTouched=true;state.draftRequest++;updateReferenceAddAvailability()};
const commitReferenceEditSoon=()=>referenceCommits++;
const previewClientId='c2';
let holderCalls=0,referenceCommits=0,resolveDraft;
const api=()=>new Promise(resolve=>{resolveDraft=resolve});
const state={draft:null,draftRequest:4,referenceResolutionRequest:null,draftResolvedOptions:{},
 draftIsNew:false,draftTouched:false,draftAutoCommit:true,selected:0,
 design:{box:{z:40,base_thickness:4},layout:{features:[]}}};
__SOURCE__
(async()=>{
 const results=[];
 for(const kind of ['slot','steps']){
  state.draft={kind,zone:[-10,-8,10,8],options:{}};
  state.design.layout.features=[state.draft];state.draftTouched=false;
  state.referenceResolutionRequest=null;state.draftResolvedOptions={};
  const pending=refreshDraft();
  const before={hidden:button.hidden,ready:referenceAddReady()};
  addReferenceToCurrentDraft();
  resolveDraft({resolved_options:{height:16,lip:1},feature:{}});
  await pending;
  const after={hidden:button.hidden,ready:referenceAddReady()};
  const sizingBeforeAdd=holderCalls;
  addReferenceToCurrentDraft();
  results.push({kind,before,after,height:state.draft.reference_object?.height,
   zone:state.draft.zone,referenceCommits,extraSizing:holderCalls-sizingBeforeAdd});
 }
 process.stdout.write(JSON.stringify(results));
})();
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), [
            {"kind": "slot", "before": {"hidden": True, "ready": False},
             "after": {"hidden": False, "ready": True}, "height": 16,
             "zone": [-10, -8, 10, 8], "referenceCommits": 1, "extraSizing": 0},
            {"kind": "steps", "before": {"hidden": True, "ready": False},
             "after": {"hidden": False, "ready": True}, "height": 17,
             "zone": [-10, -8, 10, 8], "referenceCommits": 2, "extraSizing": 0},
        ])

    def test_reference_seed_waits_for_resolved_slot_and_steps_height(self):
        source = "\n".join(function_source(name, APP) for name in (
            "referencePhysicalHeight", "referenceSeedForDraft", "referenceAddReady",
            "updateReferenceAddAvailability", "addReferenceToCurrentDraft"))
        script = r"""
const number=(value,fallback)=>Number.isFinite(Number(value))?Number(value):fallback;
const _nestMeasuredThickness=()=>null;
const button={hidden:true};
const $=selector=>selector==='[data-action="add-reference"]'?button:{};
const draftCommitIndex=()=>0;
let referenceCommits=0;
const renderDraftFields=()=>{};
const commitReferenceEditSoon=()=>referenceCommits++;
const state={draft:null,draftRequest:5,referenceResolutionRequest:null,draftResolvedOptions:{},
 draftIsNew:false,draftTouched:false,design:{box:{z:40,base_thickness:4},layout:{features:[]}}};
const markDraftChanged=()=>{state.draftTouched=true;state.draftRequest++;updateReferenceAddAvailability()};
__SOURCE__
const results=[];
for(const kind of ['slot','steps']){
 state.draft={kind,zone:[-10,-8,10,8],options:{}};
 state.draftTouched=false;state.draftRequest=5;state.referenceResolutionRequest=null;
 state.draftResolvedOptions={};state.design.layout.features=[state.draft];
 updateReferenceAddAvailability();
 addReferenceToCurrentDraft();
 let unresolvedRejected=false;
 try{referenceSeedForDraft(state.draft,null,state.design)}catch{unresolvedRejected=true}
 const before={hidden:button.hidden,reference:state.draft.reference_object??null,
  commits:referenceCommits,unresolvedRejected};
 state.draftResolvedOptions={height:16,lip:1};state.referenceResolutionRequest=5;
 updateReferenceAddAvailability();
 const shown=!button.hidden;
 addReferenceToCurrentDraft();
 results.push({kind,before,shown,height:state.draft.reference_object?.height,
   zone:state.draft.zone,commits:referenceCommits});
}
const explicit=[];
for(const kind of ['pocket','post','slot']){
 state.draft={kind,zone:[-10,-8,10,8],options:{height:12}};
 state.draftTouched=false;state.referenceResolutionRequest=null;state.draftResolvedOptions={};
 explicit.push({kind,ready:referenceAddReady(),height:referenceSeedForDraft(state.draft,null,state.design).height});
}
state.draft={kind:'steps',zone:[-10,-8,10,8],options:{height:16,lip:-2}};
const clamped=referenceSeedForDraft(state.draft,null,state.design).height;
process.stdout.write(JSON.stringify({results,explicit,clamped}));
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {
            "results": [
                {"kind": "slot", "before": {"hidden": True, "reference": None, "commits": 0,
                                              "unresolvedRejected": True},
                 "shown": True, "height": 16, "zone": [-10, -8, 10, 8], "commits": 1},
                {"kind": "steps", "before": {"hidden": True, "reference": None, "commits": 1,
                                               "unresolvedRejected": True},
                 "shown": True, "height": 17, "zone": [-10, -8, 10, 8], "commits": 2},
            ],
            "explicit": [{"kind": kind, "ready": True, "height": 12}
                         for kind in ("pocket", "post", "slot")],
            "clamped": 16,
        })

    def test_bore_ceiling_warning_stays_at_design_level_and_clears(self):
        source = function_source("updateBoreCeilingWarning", APP)
        script = r"""
const element={hidden:true,textContent:''};
const $=selector=>selector==='#bore-ceiling-warning' ? element : null;
__SOURCE__
updateBoreCeilingWarning({top_mm:72,cap_mm:64,space_kind:'drawer'});
const whileEditingAnotherBore={hidden:element.hidden,text:element.textContent};
updateBoreCeilingWarning(null);
process.stdout.write(JSON.stringify({whileEditingAnotherBore,afterCorrection:{hidden:element.hidden,text:element.textContent}}));
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {
            "whileEditingAnotherBore": {"hidden": False,
                "text": "Object reaches 72 mm; this Drawer is 64 mm high. The object may not fit when closed."},
            "afterCorrection": {"hidden": True, "text": ""},
        })
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index('id="bore-ceiling-warning"'), html.index('class="canvas-wrap'))
        self.assertNotIn("data-bore-ceiling-warning", APP)

    def test_new_part_reference_action_waits_for_initial_add(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("referencePhysicalHeight", "referenceAddReady", "addReferenceToCurrentDraft"))
        script = r"""
const state={draftIsNew:true,selected:null,draftSourceIndex:null,draft:{kind:'post',zone:[-10,-8,10,8]},
 design:{layout:{features:[]}},draftRequest:0,referenceResolutionRequest:0,
 draftResolvedOptions:{height:30},referenceEditPending:false,draftTouched:false};
const draftCommitIndex=()=>state.selected!==null ? state.selected : state.draftIsNew ? null : state.draftSourceIndex;
const markDraftChanged=()=>{},renderDraftFields=()=>{};
const referenceSeedForDraft=()=>({width:20,depth:16,height:30});
let referenceCommits=0;
const commitReferenceEditSoon=()=>{referenceCommits++;state.design.layout.features[0].reference_object=state.draft.reference_object};
__SOURCE__
const initial=referenceAddReady();
const initialApply=new Promise(resolve=>globalThis.acceptInitial=resolve);
addReferenceToCurrentDraft();
const clickedWhilePending=referenceCommits;
acceptInitial({kind:'post',zone:[-10,-8,10,8]});
initialApply.then(feature=>{
 state.design.layout.features.push(feature);state.selected=0;state.draftSourceIndex=0;state.draftIsNew=false;state.draft=feature;
 const after=referenceAddReady();
 addReferenceToCurrentDraft();
 process.stdout.write(JSON.stringify({initial,clickedWhilePending,after,referenceCommits,features:state.design.layout.features}));
});
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {"initial": False, "clickedWhilePending": 0,
            "after": True, "referenceCommits": 1, "features": [{"kind": "post", "zone": [-10, -8, 10, 8],
                                         "reference_object": {"width": 20, "depth": 16, "height": 30}}]})

    def test_reference_commit_uses_reference_route_without_resizing(self):
        source = function_source("commitReferenceEdit", APP)
        script = r"""
const clone=v=>JSON.parse(JSON.stringify(v));
const original={kind:'post',zone:[-10,-8,10,8]};
const state={design:{layout:{features:[original]}},draft:{...clone(original),
 reference_object:{width:22,depth:16,height:16}},draftRequest:3,referenceEditPending:true,
 selected:0,draftIsNew:false};
const draftCommitIndex=()=>0;
const calls=[];
const api=async(path,payload)=>{calls.push(path);return {design:{layout:{features:[clone(payload.feature)]}},selected:0}};
const noteCommittedDesignChange=()=>calls.push('change'),renderPlaced=()=>{},updateSelectionButtons=()=>{};
const updateReferenceAddAvailability=()=>{};
const refreshPreview=async()=>calls.push('preview');
const $=()=>({textContent:'',classList:{add(){}}});
__SOURCE__
commitReferenceEdit().then(()=>process.stdout.write(JSON.stringify({calls,
 zone:state.design.layout.features[0].zone,pending:state.referenceEditPending})));
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {"calls": ["/api/feature/reference", "change", "preview"],
                                            "zone": [-10, -8, 10, 8], "pending": False})

    def test_reference_editor_seed_and_positive_edit_leave_holder_size_alone(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("referencePhysicalHeight", "referenceSeedForDraft", "updateReferenceAxis"))
        script = r"""
const number=(v,f)=>Number.isFinite(Number(v))?Number(v):f;
const _nestMeasuredThickness=o=>o?.tool_thickness || null;
__SOURCE__
const draft={kind:'post',zone:[-10,-8,10,8],options:{}};
const before=JSON.stringify(draft.zone);
draft.reference_object=referenceSeedForDraft(draft,{height:16},{box:{z:40,base_thickness:.6}});
const rejected=updateReferenceAxis(draft,'width','0');
const accepted=updateReferenceAxis(draft,'width','22');
process.stdout.write(JSON.stringify({ref:draft.reference_object,before,after:JSON.stringify(draft.zone),rejected,accepted}));
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {"ref": {"width": 22, "depth": 16, "height": 16},
                                            "before": "[-10,-8,10,8]", "after": "[-10,-8,10,8]",
                                            "rejected": False, "accepted": True})

    def test_reference_preview_group_follows_interior_visibility_and_framing(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("classifyOrdinaryFace", "previewAabbWithoutReference", "currentPreviewPasses"))
        script = r"""
const state={binVisible:true,interiorVisible:true,xrayOn:false};
const b4bEnabled=()=>false,baseTrimEnabled=()=>false;
const buffers={allAabb:{min:[-5,-5,0],max:[5,5,100]},groups:{
 bin:{aabb:{min:[-5,-5,0],max:[5,5,30]}},
 interior:{aabb:{min:[-3,-3,1],max:[3,3,25]}},
 reference:{aabb:{min:[-2,-2,1],max:[2,2,100]}}}};
__SOURCE__
const shown=currentPreviewPasses(buffers);
state.interiorVisible=false;
const hidden=currentPreviewPasses(buffers);
process.stdout.write(JSON.stringify({group:classifyOrdinaryFace({kind:'reference_object'}),
 shown:shown.passes,shownZ:shown.aabb.max[2],hidden:hidden.passes,hiddenZ:hidden.aabb.max[2]}));
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {
            "group": "reference",
            "shown": [{"group": "bin", "alpha": 1}, {"group": "interior", "alpha": 1},
                      {"group": "reference", "alpha": .3}], "shownZ": 100,
            "hidden": [{"group": "bin", "alpha": 1}], "hiddenZ": 30,
        })

    def test_modifier_immediate_save_flushes_edge_grip_and_opening(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("flushModifierForm", "saveModifierPart"))
        script = r"""
const clone=v=>JSON.parse(JSON.stringify(v));
const cases=[['edge_mount','label_text','Last label'],
 ['inside_grip','size','large'],['side_openings','shape','square']];
const seen=[];
let state,pendingDesignHistory,visible,debounced,changes,fail;
const beginDesignMutation=()=>true,finishDesignMutation=()=>{};
const cancelChangedDesignDebounce=()=>{debounced=false};
const applyLiveFormWithModifierConflictGuard=()=>{
 state.design.box[state.modifierEditing][visible.key]=visible.value;return true;
};
const noteCommittedDesignChange=before=>{if(JSON.stringify(before)!==JSON.stringify(state.design))changes++};
const api=async()=>{if(fail)throw Error('validation failed');return {design:clone(state.design)}};
const clearDraftSelection=()=>{state.modifierEditing=null},renderPlaced=()=>{},refreshPreview=async()=>{};
const toast=()=>{};
__SOURCE__
(async()=>{
 for(const [kind,key,value] of cases){
  state={modifierEditing:kind,design:{box:{[kind]:{[key]:'old',label_enabled:true}}},canGenerate:true};
  pendingDesignHistory=clone(state.design);visible={key,value};debounced=true;changes=0;fail=false;
  await saveModifierPart();
  seen.push({kind,value:state.design.box[kind][key],debounced,changes,closed:state.modifierEditing===null});
 }
 state={modifierEditing:'inside_grip',design:{box:{inside_grip:{size:'old'}}},canGenerate:true};
 pendingDesignHistory=clone(state.design);visible={key:'size',value:'medium'};debounced=true;changes=0;fail=true;
 await saveModifierPart();
 seen.push({kind:'failed',value:state.design.box.inside_grip.size,closed:state.modifierEditing===null});
 process.stdout.write(JSON.stringify(seen));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        result = node_json(script)
        for actual, expected in zip(result[:3], ("Last label", "large", "square")):
            self.assertEqual(actual["value"], expected)
            self.assertFalse(actual["debounced"])
            self.assertEqual(actual["changes"], 1)
            self.assertTrue(actual["closed"])
        self.assertEqual(result[3], {"kind": "failed", "value": "medium", "closed": False})

    def test_modifier_save_claims_live_baseline_before_awaited_validation(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("beginDesignMutation", "flushModifierForm", "saveModifierPart"))
        script = r"""
const clone=v=>JSON.parse(JSON.stringify(v));
const old={box:{inside_grip:{size:'small'}}};
const state={design:clone(old),modifierEditing:'inside_grip',canGenerate:true,
 spaceStarterPreviewPending:true,designMutationBusy:false};
let pendingDesignHistory=clone(old),debounced=true,resolveApi,changes=0;
const cancelChangedDesignDebounce=()=>{debounced=false};
const applyLiveFormWithModifierConflictGuard=()=>{
 state.design.box.inside_grip.size='large';return true;
};
const cancelPendingDraftWork=()=>{},setMutationSurfacesInert=()=>{};
const mutationControls=()=>[],updateSelectionButtons=()=>{},updateGenerateAvailability=()=>{};
const finishDesignMutation=()=>{state.designMutationBusy=false};
const noteCommittedDesignChange=before=>{
 if(JSON.stringify(before)!==JSON.stringify(state.design)){
  changes++;state.spaceStarterPreviewPending=false;
 }
};
const api=()=>new Promise(resolve=>{resolveApi=resolve});
const clearDraftSelection=()=>{state.modifierEditing=null};
const renderPlaced=()=>{},refreshPreview=async()=>{},toast=()=>{};
__SOURCE__
(async()=>{
 const saving=saveModifierPart();
 const held={value:state.design.box.inside_grip.size,baseline:pendingDesignHistory,
  debounced,busy:state.designMutationBusy,changes};
 resolveApi({design:clone(state.design)});
 await saving;
 process.stdout.write(JSON.stringify({held,final:{value:state.design.box.inside_grip.size,
  closed:state.modifierEditing===null,starter:state.spaceStarterPreviewPending,
  busy:state.designMutationBusy,changes}}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {
            "held": {"value": "large", "baseline": None, "debounced": False,
                     "busy": True, "changes": 1},
            "final": {"value": "large", "closed": True, "starter": False,
                      "busy": False, "changes": 1},
        })

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
const resetNestPhotoSession=()=>{},flushModifierForm=()=>true;
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
  designInventoryId:'B1',design:old,cleanDesign:old,previewRequest:0};
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
      previews:fullPreviewStarts,clean:state.cleanDesign.marker};
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
