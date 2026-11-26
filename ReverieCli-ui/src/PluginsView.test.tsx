// @vitest-environment jsdom
import {useState} from 'react';
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {PluginsView} from './PluginsView';
import {usePlugins} from './plugin-state';
import type {PluginCandidate} from './generated/core-types';
import type {PluginRecord,PluginsState} from './types';

afterEach(cleanup);
const first:PluginCandidate={sha256:'a'.repeat(64),name:'Native fixture',version:'1.0',source:{kind:'directory',location:'fixture'},bytes:1234,signing_key:null,verification:'candidate_approval_required',approval_profile_sha256:'b'.repeat(64),approval_required:true,components:[{kind:'command',name:'fixture-command',path:'commands/one.md',description:'Registered fixture',policy:{permissions:['files.read']},requires_platform:false},{kind:'hook',name:'PreToolUse:0',path:'hooks/hooks.json',description:'PreToolUse',policy:{event:'PreToolUse',matcher:'Write',entries:[{type:'command',command:'node fixture-hook.mjs',permissions:['files.read'],env_keys:['TOKEN_NAME']}]},requires_platform:false}],license:'MIT',license_files:['LICENSE'],approval:{permissions:['files.read'],components:[{kind:'hook',event:'PreToolUse',command:'node fixture-hook.mjs'}]}};
const second:PluginCandidate={...first,sha256:'c'.repeat(64),version:'2.0',approval_profile_sha256:'d'.repeat(64),approval:{permissions:['files.read','files.write'],components:first.approval}};
const base:PluginRecord={id:'plugin-1',name:'Native fixture',family:'extension',version:'1.0',status:'trust_required',status_label:'trust_required',enabled:false,trusted:false,protocol_status:'compatible',protocol_label:'compatible',tool_count:0,command_count:1,skill_count:0,entry_path:'',install_dir:'fixture/package',active_sha256:first.sha256,approval_profile_sha256:first.approval_profile_sha256,hooks_enabled:false,auto_update:false,previous_sha256:'',source:first.source,candidates:[first,second]};
function setup(options:{trusted?:boolean;held?:boolean;activeOnly?:boolean}={}) {
  let state:PluginsState={revision:1,summary:{},records:[{...base,candidates:options.activeOnly?[]:base.candidates,trusted:Boolean(options.trusted),status:options.trusted?'disabled':'trust_required'}]};
  let rejectPrepare:((error:Error)=>void)|undefined;
  const request=vi.fn(async(action:string,payload:Record<string,unknown>)=>{
    if(action==='listPlugins'||action==='refreshPlugins')return {type:'plugins',plugins:structuredClone(state)};
    if(action==='inspectPlugin')return {type:'plugin.inspect',plugin_id:'plugin-1',record:structuredClone(state.records[0]),active:structuredClone(state.records[0].active_sha256===second.sha256?second:first),revision:state.revision};
    if(action==='preparePlugin'&&options.held)return await new Promise((_resolve,reject)=>{rejectPrepare=reject;});
    if(action==='stopPluginOperation'){rejectPrepare?.(new Error('Extension preparation cancelled.'));return {type:'plugin.control',operation_id:payload.operation_id,cancelled:true};}
    if(action==='activatePlugin')state={...state,revision:state.revision!+1,records:state.records.map(record=>({...record,version:'2.0',active_sha256:String(payload.candidate_sha256),approval_profile_sha256:second.approval_profile_sha256,previous_sha256:record.active_sha256,trusted:Boolean(record.trusted),hooks_enabled:false}))};
    else if(action==='removePlugin')state={...state,revision:state.revision!+1,records:[]};
    else if(['setPluginTrust','setPluginEnabled','setPluginHooks','setPluginAutoUpdate'].includes(action)) {
      const field=action==='setPluginTrust'?'trusted':action==='setPluginEnabled'?'enabled':action==='setPluginHooks'?'hooks_enabled':'auto_update';
      state={...state,revision:state.revision!+1,records:state.records.map(record=>({...record,[field]:Boolean(payload[field]),...(action==='setPluginTrust'?{auto_update:Boolean(payload.trusted)}:{})}))};
    } else throw new Error(`Unexpected request ${action}`);
    return {type:'plugin.updated',plugin_id:'plugin-1',plugins:structuredClone(state),settings:{items:[],config_path:'fixture',workspace_mode:true}};
  });
  window.reverie={request} as unknown as typeof window.reverie;
  function Harness(){const [visible,setVisible]=useState(true);const c=usePlugins(visible,'fixture/workspace',()=>{});return <><button onClick={()=>setVisible(current=>!current)}>切页</button>{visible&&<PluginsView controller={c}/>}</>;}
  return {request,Harness};
}
it('shows native identity and requires a separate exact-profile trust confirmation',async()=>{
  const {request,Harness}=setup();render(<Harness/>);await screen.findByRole('heading',{name:'Native fixture'});
  const trust=screen.getByRole('checkbox',{name:'信任执行范围'});
  fireEvent.click(trust);const dialog=await screen.findByRole('alertdialog');
  expect(request.mock.calls.some(([action])=>action==='setPluginTrust')).toBe(false);
  expect(dialog.textContent).toContain(first.sha256);expect(dialog.textContent).toContain(first.approval_profile_sha256);
  expect((within(dialog).getByRole('button',{name:'确认操作'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(within(dialog).getByRole('checkbox',{name:'我已审阅并确认本次操作'}));fireEvent.click(within(dialog).getByRole('button',{name:'确认操作'}));
  await waitFor(()=>expect(request).toHaveBeenCalledWith('setPluginTrust',{pluginId:'plugin-1',projectRoot:'fixture/workspace',expected_revision:1,trusted:true,candidate_sha256:first.sha256,approval_profile_sha256:first.approval_profile_sha256}));
  await waitFor(()=>expect((screen.getByRole('checkbox',{name:'信任执行范围'}) as HTMLInputElement).checked).toBe(true));
  expect((screen.getByRole('checkbox',{name:'在当前项目启用'}) as HTMLInputElement).checked).toBe(false);
});
it('keeps Hooks disabled until inspected event, entry and permissions are confirmed',async()=>{
  const {request,Harness}=setup({trusted:true});render(<Harness/>);await screen.findByRole('heading',{name:'Native fixture'});
  fireEvent.click(screen.getByRole('checkbox',{name:'Hooks'}));let dialog=await screen.findByRole('alertdialog');
  expect(dialog.textContent).toContain('PreToolUse');expect(dialog.textContent).toContain('node fixture-hook.mjs');expect(dialog.textContent).toContain('files.read');
  fireEvent.click(within(dialog).getByRole('button',{name:'取消'}));
  expect(request.mock.calls.some(([action])=>action==='setPluginHooks')).toBe(false);
  fireEvent.click(screen.getByRole('checkbox',{name:'Hooks'}));dialog=await screen.findByRole('alertdialog');
  fireEvent.click(within(dialog).getByRole('checkbox',{name:'我已审阅并确认本次操作'}));fireEvent.click(within(dialog).getByRole('button',{name:'确认操作'}));
  await waitFor(()=>expect(request).toHaveBeenCalledWith('setPluginHooks',{pluginId:'plugin-1',projectRoot:'fixture/workspace',expected_revision:1,hooks_enabled:true,approval_profile_sha256:first.approval_profile_sha256}));
});
it('requires content and changed-profile approvals for the selected immutable candidate',async()=>{
  const {request,Harness}=setup({trusted:true});render(<Harness/>);await screen.findByRole('heading',{name:'Native fixture'});
  fireEvent.change(screen.getByRole('combobox',{name:'查看版本候选'}),{target:{value:second.sha256}});
  fireEvent.click(screen.getByRole('button',{name:'审阅并激活'}));const dialog=await screen.findByRole('alertdialog');
  expect(dialog.textContent).toContain(second.sha256);expect(dialog.textContent).toContain('files.write');
  const confirm=within(dialog).getByRole('button',{name:'确认操作'}) as HTMLButtonElement;
  fireEvent.click(within(dialog).getByRole('checkbox',{name:'我已审阅并确认本次操作'}));expect(confirm.disabled).toBe(true);
  fireEvent.click(within(dialog).getByRole('checkbox',{name:'批准上述候选 SHA-256'}));expect(confirm.disabled).toBe(true);
  fireEvent.click(within(dialog).getByRole('checkbox',{name:'批准上述执行范围变化'}));fireEvent.click(confirm);
  await waitFor(()=>expect(request).toHaveBeenCalledWith('activatePlugin',{plugin_id:'plugin-1',candidate_sha256:second.sha256,expected_revision:1,approved_sha256:second.sha256,approved_profile_sha256:second.approval_profile_sha256}));
});
it('retains installation drafts and the cancellable operation across navigation',async()=>{
  const {request,Harness}=setup({held:true});render(<Harness/>);await screen.findByRole('heading',{name:'Native fixture'});
  fireEvent.change(screen.getByLabelText('来源地址、目录或市场条目 ID'),{target:{value:'independent/plugin source😀'}});
  fireEvent.click(screen.getByRole('button',{name:'准备候选'}));await screen.findByRole('button',{name:'停止'});
  const payload=request.mock.calls.find(([action])=>action==='preparePlugin')![1];
  expect(payload.source).toEqual({kind:'directory',location:'independent/plugin source😀',entry_id:undefined,revision:undefined,subdirectory:undefined,sha256:undefined,signing_key:undefined,require_signature:false});
  expect(payload.operation_id).toEqual(expect.any(String));
  fireEvent.click(screen.getByRole('button',{name:'切页'}));fireEvent.click(screen.getByRole('button',{name:'切页'}));
  expect((screen.getByLabelText('来源地址、目录或市场条目 ID') as HTMLInputElement).value).toBe('independent/plugin source😀');
  fireEvent.click(screen.getByRole('button',{name:'停止'}));
  await waitFor(()=>expect(request).toHaveBeenCalledWith('stopPluginOperation',{operation_id:payload.operation_id}));
  await waitFor(()=>expect(screen.queryByRole('button',{name:'停止'})).toBeNull());
  expect(request.mock.calls.some(([action])=>['activatePlugin','setPluginTrust','setPluginEnabled'].includes(action))).toBe(false);
});
it('requires explicit removal confirmation and keeps the request revision bound',async()=>{
  const {request,Harness}=setup();render(<Harness/>);await screen.findByRole('heading',{name:'Native fixture'});
  fireEvent.click(screen.getByRole('button',{name:'移除'}));const dialog=await screen.findByRole('alertdialog');
  expect(request.mock.calls.some(([action])=>action==='removePlugin')).toBe(false);
  fireEvent.click(within(dialog).getByRole('checkbox',{name:'我已审阅并确认本次操作'}));fireEvent.click(within(dialog).getByRole('button',{name:'确认操作'}));
  await waitFor(()=>expect(request).toHaveBeenCalledWith('removePlugin',{pluginId:'plugin-1',projectRoot:'fixture/workspace',expected_revision:1,confirmed:true}));
});
it('keeps the inspected active version visible when no inactive candidate remains',async()=>{
  const {request,Harness}=setup({activeOnly:true});render(<Harness/>);
  await screen.findByText(first.sha256);
  expect(screen.getByRole('heading',{name:'当前版本'})).toBeTruthy();
  const details=document.querySelector('.plugin-detail .plugin-candidate-details')!;
  expect(details.textContent).toContain(first.approval_profile_sha256);expect(details.textContent).toContain('MIT');
  expect(details.textContent).toContain('fixture-command');expect(details.textContent).toContain('hooks/hooks.json');
  expect(screen.queryByRole('button',{name:'审阅并激活'})).toBeNull();
  expect(request.mock.calls.some(([action])=>!['listPlugins','inspectPlugin'].includes(action))).toBe(false);
});
