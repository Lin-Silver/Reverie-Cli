import { powerMonitor } from 'electron';
import { AiOWindow,type AiOMessage } from './aio-window';
type RecordValue=Record<string,unknown>;
type Request=(action:string,payload:RecordValue)=>Promise<RecordValue>;

export class AiOHost {
  private timer:ReturnType<typeof setInterval>|null=null;
  private judging=false;
  private judgingProactive=false;
  private judgmentCancelled=false;
  private wakeRequested=false;
  private stopped=false;
  private popup:AiOWindow;
  private lastJudgment=0;
  private tasks=new Map<string,Promise<void>>();
  private taskOwners=new Map<string,RecordValue>();
  private previousControl:{enabled:boolean;paused:boolean}|null=null;
  constructor(private request:Request,private decide:Request,private execute:Request,private workspaces:()=>string[],private navigate:(message:AiOMessage)=>void,private report:(event:RecordValue)=>void,private cancelDecision:()=>Promise<void>=async()=>{}){
    this.popup=new AiOWindow(async(message,text,replyId)=>{
      await this.request('aioReply',{assistantId:'aio',messageId:message.id,text,replyId});
      void this.tick(undefined,true).catch(error=>this.report({type:'aio.error',error:String(error)}));
    },navigate,async(message,latency)=>{
      await this.request('aioMessageState',{assistantId:'aio',messageId:message.id,state:'presented'});
      this.report({type:'aio.popup-readable',message_id:message.id,latency_ms:latency});
    });
  }
  start(){
    if(this.timer)return;
    this.stopped=false;
    this.timer=setInterval(()=>void this.tick().catch(error=>this.report({type:'aio.error',error:String(error)})),60000);
    void this.request('aioRecoverHost',{assistantId:'aio'}).then(async()=>{await this.controlsChanged();}).catch(error=>this.report({type:'aio.error',error:String(error)}));
  }
  stop(){this.stopped=true;if(this.timer)clearInterval(this.timer);this.timer=null;this.popup.stop();}
  async controlsChanged(){
    const response=await this.request('aioState',{assistantId:'aio'});const state=response.aio as RecordValue;
    if(this.judging && (!state.enabled || state.paused || (!state.proactive && this.judgingProactive))){
      this.judgmentCancelled=true;
      await this.cancelDecision();
    }
    if(this.previousControl && (this.previousControl.enabled!==state.enabled || this.previousControl.paused!==state.paused)){
      const action=!state.enabled?'stopPrompt':state.paused?'pausePrompt':'continuePrompt';
      for(const task of this.taskOwners.values())await this.execute(action,{assistantId:'aio',projectRoot:task.workspace,sessionId:task.branch}).catch(error=>this.report({type:'aio.control-error',task_id:task.id,error:String(error)}));
    }
    this.previousControl={enabled:Boolean(state.enabled),paused:Boolean(state.paused)};
    if(!state.enabled || !state.proactive || state.paused){
      for(const messageId of this.popup.stop())await this.request('aioMessageState',{assistantId:'aio',messageId,state:'queued'});
    }else await this.deliver();
    if(state.enabled && !state.paused){
      const pending=await this.request('aioPendingTasks',{assistantId:'aio'});
      for(const task of pending.tasks as RecordValue[])this.dispatch(task);
      await this.tick(undefined,true);
    }
  }
  private dispatch(task:RecordValue){
    const id=String(task.id);
    if(this.stopped || this.tasks.has(id))return;
    this.taskOwners.set(id,task);
    const pending=this.run(task).catch(error=>this.report({type:'aio.error',task_id:id,error:String(error)})).finally(()=>{this.tasks.delete(id);this.taskOwners.delete(id);});
    this.tasks.set(id,pending);
  }
  async tick(_event?:RecordValue,urgent=false){
    if(this.stopped)return;
    if(this.judging){this.wakeRequested=true;return;}
    this.judging=true;
    let drained=false;
    try{
      let observed=false;
      while(!this.stopped){
        const state=(await this.request('aioState',{assistantId:'aio'})).aio as RecordValue;
        if(!state.enabled || state.paused)return;
        const signals=(await this.request('aioPendingSignals',{assistantId:'aio'})).signals as RecordValue[];
        let observation=signals[0];
        const saved=Boolean(observation);
        if(!saved){
          if(urgent || observed || !state.proactive || Date.now()-this.lastJudgment<60000)break;
          const response=await this.request('aioObserve',{assistantId:'aio',excludePids:[process.pid],idleSeconds:powerMonitor.getSystemIdleTime()});
          observation=response.observation as RecordValue;
          if(!observation)break;
          observed=true;this.lastJudgment=Date.now();
        }
        this.judgingProactive=!saved;
        this.judgmentCancelled=false;
        let response:RecordValue;
        try{response=await this.decide('aioDecision',{assistantId:'aio',observation,workspaces:this.workspaces(),urgent:saved});}
        catch(error){if(this.judgmentCancelled)break;throw error;}
        finally{this.judgingProactive=false;}
        if(this.stopped)return;
        const latest=(await this.request('aioState',{assistantId:'aio'})).aio as RecordValue;
        if(this.judgmentCancelled || !latest.enabled || latest.paused || (!saved && !latest.proactive))break;
        if(saved)await this.request('aioAcknowledgeSignal',{assistantId:'aio',eventId:observation.event_id});
        const decision=response.decision as {tasks?:Array<RecordValue>};
        for(const task of decision.tasks || [])this.dispatch(task);
      }
      await this.deliver();
      drained=true;
    }finally{
      this.judging=false;
      const wake=this.wakeRequested;this.wakeRequested=false;
      if(wake && drained && !this.stopped)void this.tick(undefined,true).catch(error=>this.report({type:'aio.error',error:String(error)}));
    }
  }
  private async run(task:RecordValue){
    const taskId=String(task.id);let revision=Number(task.revision || 1);
    let finalized=false;
    const update=async(state:string,result?:RecordValue)=>{const response=await this.request('aioTaskState',{assistantId:'aio',taskId,state,revision,result});revision=Number(response.revision);};
    try{
      await update('running');
      const response=await this.execute('runPrompt',{assistantId:'aio',projectRoot:task.workspace,sessionId:task.branch,prompt:task.prompt,promptAlreadySaved:true,configuration:task.configuration,acceptance:task.acceptance,runType:task.runType,freshSession:false});
      const result=response.result as RecordValue;
      await update(String(result.completion_state || (result.success?'completed':result.verification?'waiting_user':'failed')),result);
      finalized=true;
      await this.tick(undefined,true);
    }catch(error){if(!finalized)await update('interrupted',{error:String(error)});throw error;}
  }
  private async deliver(){
    const state=(await this.request('aioState',{assistantId:'aio'})).aio as RecordValue;
    if(this.stopped || !state.enabled || !state.proactive || state.paused)return;
    const response=await this.request('aioMessages',{assistantId:'aio'});
    for(const item of response.messages as Array<RecordValue>){
      const claimed=await this.request('aioMessageState',{assistantId:'aio',messageId:item.id,state:'displaying'});if(!claimed.claimed)continue;
      const payload=JSON.parse(String(item.payload)) as RecordValue;
      this.popup.enqueue({id:String(item.id),branch:String(item.branch),root:String(item.workspace || this.workspaces()[0] || ''),text:String(payload.text || ''),queuedAt:Date.now()});
    }
  }
}
