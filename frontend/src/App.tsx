// Equipment selection scopes the evidence; abort controllers prevent stale responses.
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceDot } from 'recharts';
import { chat, get, type Answer, type Asset, type Sensor, type Signal, type Trace } from './api';

const time = (timestamp: number) => new Date(timestamp).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit'});
export default function App() {
 const [assets,setAssets] = useState<Asset[]>([]);
 const [selected,setSelected] = useState('');
 const [sensors,setSensors] = useState<Sensor[]>([]);
 const [sensor,setSensor] = useState('');
 const [signal,setSignal] = useState<Signal|null>(null);
 const [source,setSource] = useState('Connecting');
 const [snapshot,setSnapshot] = useState('');
 const [provider,setProvider] = useState('');
 const [mode,setMode] = useState<'operator'|'executive'>('operator');
 const [question,setQuestion] = useState('');
 const [answer,setAnswer] = useState<Answer|null>(null);
 const [steps,setSteps] = useState<Trace[]>([]);
 const [busy,setBusy] = useState(false);
 const [error,setError] = useState('');
 const request = useRef<AbortController|null>(null);
 const [submitted,setSubmitted] = useState('');
 // A previous answer must never appear to describe a newly selected asset or mode.
 useEffect(()=>{setAnswer(null);setSteps([]);setSubmitted('');},[selected,mode]);
 useEffect(()=>{
  const controller = new AbortController();
  Promise.all([get<Asset[]>('/api/assets',controller.signal),get<{source:string;snapshot_at:string;llm_provider:string}>('/api/health',controller.signal)])
   .then(([rows,health])=>{setAssets(rows);setSelected(rows.find(x=>!x.parent_id)?.id||rows[0]?.id||'');setSource(health.source);setSnapshot(health.snapshot_at);setProvider(health.llm_provider);})
   .catch(e=>{if(e.name!=='AbortError')setError(e.message);});
  return ()=>{controller.abort();request.current?.abort();};
 },[]);
 useEffect(()=>{
  if(!selected)return;
  const controller = new AbortController();
  setSensors([]);setSensor('');setSignal(null);
  get<{series:Sensor[]}>(`/api/assets/${encodeURIComponent(selected)}`,controller.signal)
   .then(x=>{setSensors(x.series);setSensor(x.series[0]?.id||'');})
   .catch(e=>{if(e.name!=='AbortError')setError(e.message);});
  return ()=>controller.abort();
 },[selected]);
 useEffect(()=>{
  if(!sensor)return;
  const controller=new AbortController();setSignal(null);
  get<Signal>(`/api/timeseries/${encodeURIComponent(sensor)}`,controller.signal)
   .then(setSignal).catch(e=>{if(e.name!=='AbortError')setError(e.message);});
  return ()=>controller.abort();
 },[sensor]);
 async function ask(text: string) {
  if(!text.trim()||busy||!selected)return;
  setError('');setAnswer(null);setSteps([]);setBusy(true);setSubmitted(text);setQuestion('');
  const controller=new AbortController();request.current=controller;
  try {
   await chat({question:text,asset_id:selected,mode},step=>setSteps(old=>[...old,step]),setAnswer,controller.signal);
  } catch(e){if(e instanceof Error&&e.name!=='AbortError')setError(e.message);}
  finally{setBusy(false);}
 }
 function submit(e:FormEvent){e.preventDefault();void ask(question);}
 function tree(parent:string|null,level=0): React.ReactNode {
  return assets.filter(x=>x.parent_id===parent).map(asset=><div key={asset.id}>
   <button className={selected===asset.id?'asset selected':'asset'} style={{paddingLeft:12+level*14}}
    disabled={busy} onClick={()=>setSelected(asset.id)}><span className="asset-icon">{level?'◇':'▱'}</span>{asset.name}</button>
   {tree(asset.id,level+1)}
  </div>);
 }
 const selectedAsset=assets.find(x=>x.id===selected);
 const stats=signal?.statistics;
 return <div className="shell">
  <header className="topbar"><div className="brand"><span className="brandmark">V</span><div><b>Valhall</b><span>OPS COPILOT</span></div></div>
   <div className="top-context">Industrial intelligence <span>/</span> Compressor train</div>
   <span className="source-tag">{source==='synthetic'?'Synthetic workspace':source==='cdf_snapshot'?'CDF snapshot':source}</span>
  </header>
  <main className="workspace">
   <aside className="explorer"><div className="eyebrow">ASSET EXPLORER</div><h2>Equipment context</h2>
    <p className="muted">Select a subsystem to scope the tools and supporting evidence.</p>
    <nav aria-label="Asset hierarchy" className="tree">{tree(null)}</nav>
    <div className="provenance"><span className="eyebrow">DATA PROVENANCE</span><b>{source==='synthetic'?'Generated demonstration':'Read only snapshot'}</b>
     <p>{source==='synthetic'?'Signals and equipment labels in this workspace are fictional.':'Evidence is replayed from a locally acquired CDF snapshot.'}</p>
     <small>Snapshot {snapshot?new Date(snapshot).toLocaleDateString():'—'}</small>
    </div>
   </aside>
   <section className="content">
    <div className="page-heading"><div><div className="eyebrow">OPERATIONS WORKSPACE</div><h1>{selectedAsset?.name||'Loading equipment'}</h1><p className="muted">{selectedAsset?.description}</p></div>
     <div className="mode-control" aria-label="Answer mode">{(['operator','executive'] as const).map(x=><button key={x} className={mode===x?'active':''} disabled={busy} onClick={()=>setMode(x)}>{x==='operator'?'Operator':'Executive'}</button>)}</div>
    </div>
    {error&&<div className="error" role="alert">{error}<button onClick={()=>setError('')} aria-label="Dismiss error">×</button></div>}
    <section className="metrics" aria-label="Selected signal summary">
     <div><span>Mean {sensor?'signal':''}</span><strong>{stats?stats.mean.toFixed(2):'—'}<small>{signal?.unit}</small></strong><p>Selected recorded window</p></div>
     <div><span>Observed maximum</span><strong>{stats?stats.maximum.toFixed(2):'—'}<small>{signal?.unit}</small></strong><p>Descriptive statistic</p></div>
     <div><span>Statistical deviations</span><strong>{stats?.anomalies.length??'—'}</strong><p>Trailing window · |z| ≥ 3</p></div>
     <div><span>Evidence coverage</span><strong>{stats?.count??'—'}<small>samples</small></strong><p>{signal?time(signal.points[0].timestamp)+' — '+time(signal.points.at(-1)!.timestamp):'Select a sensor'}</p></div>
    </section>
    {mode==='executive'&&<section className="executive panel"><span className="eyebrow">EXECUTIVE BRIEF</span><h2>What the snapshot shows</h2><p>{stats?`${signal!.name} averages ${stats.mean.toFixed(2)} ${signal!.unit} across ${stats.count} samples, with ${stats.anomalies.length} statistical deviations. These observations require operating context and approved procedures before action.`:'Select a sensor to summarize its recorded evidence.'}</p></section>}
    <div className="work-panels">
     <section className="panel trend"><div className="panel-heading"><div><h2>Signal history</h2><p className="muted">Statistical markers highlight observations for review</p></div>
      <select aria-label="Select sensor" value={sensor} onChange={e=>setSensor(e.target.value)}>{sensors.map(x=><option value={x.id} key={x.id}>{x.name}</option>)}</select>
     </div>
      <div className="chart">{signal?<ResponsiveContainer width="100%" height="100%"><AreaChart data={signal.points} margin={{top:12,right:12,left:-12,bottom:10}}>
       <defs><linearGradient id="fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#169e91" stopOpacity={.26}/><stop offset="100%" stopColor="#169e91" stopOpacity={0}/></linearGradient></defs>
       <CartesianGrid stroke="#e8edf1" vertical={false}/><XAxis dataKey="timestamp" type="number" domain={['dataMin','dataMax']} tickFormatter={time} minTickGap={50} tick={{fontSize:11,fill:'#65788b'}} axisLine={false} tickLine={false}/>
       <YAxis domain={['auto','auto']} tick={{fontSize:12,fill:'#65788b'}} axisLine={false} tickLine={false}/><Tooltip labelFormatter={v=>time(Number(v))} formatter={v=>[Number(v).toFixed(2),signal.unit]}/>
       <Area type="linear" dataKey="value" stroke="#159c91" fill="url(#fill)" strokeWidth={2} isAnimationActive={false}/>
       {stats?.anomalies.map(p=><ReferenceDot key={p.timestamp} x={p.timestamp} y={p.value} r={4} fill="#d97649" stroke="#fff"/>)}
      </AreaChart></ResponsiveContainer>:<div className="empty">No sensor data in this scope.</div>}</div>
      <div className="chart-caption"><span className="legend-line"/> {signal?.unit||'Sensor signal'} <span className="anomaly-dot"/> Statistical deviation <span className="caption-end">Snapshot data · hourly samples</span></div>
      <div className="sensor-list"><span className="eyebrow">LINKED SENSORS</span>{sensors.map(x=><button className={sensor===x.id?'sensor current':'sensor'} key={x.id} onClick={()=>setSensor(x.id)}><span>{x.name}</span><small>{x.unit}</small></button>)}</div>
     </section>
     <section className="panel chat"><div className="panel-heading"><div><h2>Ask the copilot</h2><p className="muted">Answers grounded in the selected equipment</p></div><span className="provider">{provider==='extractive'?'Evidence mode':provider||'Connecting'}</span></div>
      <div className="conversation" aria-live="polite">
       {!submitted&&<><div className="intro-icon">✦</div><h3>Start with a question.</h3><p className="muted">Explore sensors, investigate deviations, or find a synthetic maintenance reference.</p><div className="suggestions">{['What sensors are on this compressor?','Were there unusual pressure spikes?','Find the discharge temperature alarm procedure.','Summarize compressor health for my VP.'].map(q=><button key={q} disabled={busy||!selected} onClick={()=>void ask(q)}>{q}</button>)}</div></>}
       {submitted&&<p className="user-question">{submitted}</p>}
       {busy&&<p className="working">Reading scoped evidence… {steps.length} tool steps</p>}
       {answer&&<><div className="answer-text">{answer.text}</div>{answer.limitations.map((text,i)=><p className="limitation" key={i}>{text}</p>)}</>}
       {steps.length>0&&<details className="trace" open={busy}><summary>How I got this · {steps.length} steps</summary>{steps.map((step,i)=><div className="trace-step" key={i}><b>{step.agent}</b><code>{step.tool}</code><p>{step.detail}</p>{step.evidence.length>0&&<small>{step.evidence.join(' · ')}</small>}</div>)}</details>}
      </div>
      <form onSubmit={submit}><label className="sr-only" htmlFor="question">Question about selected equipment</label><textarea id="question" value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Ask about the selected equipment…" maxLength={2000} rows={2} disabled={busy}/><div className="composer-footer"><span>Read only · no control actions</span>{busy?<button type="button" onClick={()=>request.current?.abort()}>Stop</button>:<button type="submit" disabled={question.trim().length<3||!selected}>Ask copilot</button>}</div></form>
     </section>
    </div>
    <footer className="workspace-foot">Personal research project · Synthetic procedures are clearly labeled · No affiliation with Cognite or Aker BP</footer>
   </section>
  </main>
 </div>;
}
