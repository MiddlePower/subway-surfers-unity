// Run: node tools/test_hoverboard_input.cjs
// Hoverboard fallback only freezes timer for Space/double-tap DURING a run.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function boot(runMode='no-coin') {
  const windowEvents=new Map(), hostEvents=new Map(), nodes=new Map();
  let state='ready', now=0, actions=[];
  const on=(table,type,fn)=>table.set(type,[...(table.get(type)||[]),fn]);
  const trigger=(table,type,event)=>{for(const fn of table.get(type)||[])fn(event);};
  const host={ addEventListener:(type,fn)=>on(hostEvents,type,fn) };
  const stage={};
  nodes.set('challenge-game',host);
  nodes.set('challenge-stage',stage);
  const document={
    body:{dataset:{runMode}},getElementById:id=>nodes.get(id)||null,
  };
  class CustomEvent {constructor(type,{detail}){this.type=type;this.detail=detail;}}
  const window={
    addEventListener:(type,fn)=>on(windowEvents,type,fn),
    dispatchEvent:event=>actions.push(event.detail.kind),
    RunnerRunTimer:{snapshot:()=>({state})},
  };
  vm.runInNewContext(fs.readFileSync(__dirname+'/hoverboard-input.js','utf8'),{
    window,document,CustomEvent,performance:{now:()=>now},Math,console,
  });
  const key=(code='Space', extras={})=>{
    trigger(windowEvents,'keydown',{
      code,key:code==='Space'?' ':code,repeat:false,ctrlKey:false,
      altKey:false,metaKey:false,target:{closest(){return null;}},...extras,
    });
  };
  const pointer=(type,x,y,time)=>{
    now=time;
    trigger(hostEvents,'pointerdown',{pointerType:type,clientX:x,clientY:y});
  };
  return {
    key,pointer,actions,change:value=>state=value,
    dblclick:()=>trigger(hostEvents,'dblclick',{}),
  };
}

const ui=boot();
ui.key();
ui.dblclick();
assert.deepEqual(ui.actions,[],'no timer stop before run starts');
ui.change('running');
ui.key();
assert.deepEqual(ui.actions,['hoverboard']);
ui.key('Space',{repeat:true});
ui.key('Space',{ctrlKey:true});
ui.key('Space',{target:{closest(){return {tagName:'INPUT'};}}});
assert.equal(ui.actions.length,1);
ui.pointer('touch',10,10,1000);
ui.pointer('touch',12,11,1190);
assert.equal(ui.actions.length,2,'double-tap activates fallback');
ui.change('finished');
ui.key();
ui.dblclick();
assert.equal(ui.actions.length,2,'finished timer remains frozen');
const normal=boot('standard');
normal.change('running');
normal.key();
assert.equal(normal.actions.length,0,'normal game is unaffected');
console.log('PASS: hoverboard fallback detects Space + touch double-tap during challenge only');
