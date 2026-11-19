// Decode SSE across arbitrary network chunks, preserving tool events before the answer.
export type Asset = { id: string; name: string; parent_id: string | null; description: string };
export type Sensor = { id: string; name: string; unit: string };
export type Trace = { agent: string; tool: string; detail: string; evidence: string[] };
export type Answer = { text: string; citations: string[]; route: string; source: string; limitations: string[]; trace: Trace[] };
export type Signal = {
 id: string; name: string; unit: string; points: {timestamp: number; value: number}[];
 statistics: { mean: number; minimum: number; maximum: number; count: number;
  anomalies: {timestamp: number; value: number; z_score: number}[]; method: string }
};
export async function get<T>(url: string, signal?: AbortSignal): Promise<T> {
 const response = await fetch(url, {signal});
 if (!response.ok) throw new Error(`Request failed (${response.status})`);
 return response.json() as Promise<T>;
}
export async function chat(payload: object, onStep: (step: Trace) => void, onAnswer: (answer: Answer) => void, signal: AbortSignal) {
 const response = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload), signal});
 if (!response.ok || !response.body) throw new Error(`Chat failed (${response.status})`);
 const reader = response.body.getReader();
 const decoder = new TextDecoder();
 let buffered = '';
 while (true) {
  const {done,value} = await reader.read();
  buffered += decoder.decode(value, {stream: !done});
  let split;
  while ((split = buffered.indexOf('\n\n')) >= 0) {
   const event = buffered.slice(0,split); buffered = buffered.slice(split+2);
   const type = event.split('\n').find(x=>x.startsWith('event: '))?.slice(7);
   const raw = event.split('\n').filter(x=>x.startsWith('data: ')).map(x=>x.slice(6)).join('\n');
   if (!raw) continue;
   const data = JSON.parse(raw);
   if (type === 'step') onStep(data);
   if (type === 'answer') onAnswer(data);
   if (type === 'error') throw new Error(data.message);
  }
  if (done) break;
 }
}
