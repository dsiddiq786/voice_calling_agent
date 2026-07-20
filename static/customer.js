if(location.hostname==='127.0.0.1'&&location.port==='8000')location.replace('http://127.0.0.1:8010/customer');
let session=null, recorder=null, chunks=[], callActive=false, closingCall=false, turnBusy=false, callStartedAt=0, timerHandle=null, activeStream=null, audioContext=null, silenceFrame=null, voiceAudio=null, voiceDone=null, callMetrics={humanMs:0,aiMs:0,delays:[],ttsChars:0};
const messages=document.querySelector('#messages'), input=document.querySelector('#message');
const callScreen=document.querySelector('#call-screen'), orb=document.querySelector('#voice-orb');
const callState=document.querySelector('#call-state'), callCaption=document.querySelector('#call-caption');

function selectFemaleVoice(){
  const voices=speechSynthesis.getVoices();
  const femaleNames=['Flo','Samantha','Sandy','Shelley','Moira','Tessa','Karen','Veena'];
  for(const name of femaleNames){const voice=voices.find(v=>v.name.includes(name));if(voice)return voice}
  return voices.find(v=>['ur-PK','hi-IN','en-IN','en-GB'].some(lang=>v.lang===lang))||voices[0];
}
function phoneticRomanUrdu(text){
  return text.toLowerCase()
    .replaceAll('assalam-o-alaikum','assalaam o alaikum')
    .replaceAll('nomnosh','nom nosh')
    .replaceAll('aap','aahp')
    .replaceAll('chahein ge','chaa hain gay')
    .replaceAll('rupay','ru pay')
    .replaceAll('bohat','bo hat')
    .replaceAll('tabdeeli','tab dee lee');
}
function setCallState(state,caption=''){
  orb.className=`voice-orb ${state}`; callState.textContent=state==='speaking'?'Fatima is speaking':state==='listening'?'Fatima is listening':state==='thinking'?'Understanding your order…':'Ready';
  if(caption)callCaption.textContent=caption;
}
function stopCallAudio(){if(silenceFrame)cancelAnimationFrame(silenceFrame);silenceFrame=null;if(activeStream)activeStream.getTracks().forEach(track=>track.stop());activeStream=null;if(audioContext){audioContext.close().catch(()=>{});audioContext=null}if(voiceAudio){voiceAudio.pause();URL.revokeObjectURL(voiceAudio.src);voiceAudio=null}if(voiceDone){voiceDone();voiceDone=null}}
async function startLocalListening(){
  if(!callActive||closingCall||turnBusy||speechSynthesis.speaking||voiceAudio||recorder?.state==='recording')return;
  try{
    activeStream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1}});
    chunks=[];let liveFinal=null,finalizeSent=false;const listeningStarted=performance.now();
    const protocol=location.protocol==='https:'?'wss':'ws';
    const liveSocket=new WebSocket(`${protocol}://${location.host}/api/live-transcribe`);
    await new Promise((resolve,reject)=>{liveSocket.onopen=resolve;liveSocket.onerror=reject});
    recorder=new MediaRecorder(activeStream);
    recorder.ondataavailable=e=>{if(!e.data.size)return;chunks.push(e.data);if(liveSocket.readyState===WebSocket.OPEN)liveSocket.send(e.data)};
    let heardSpeech=false,silentSince=0,startedAt=performance.now();
    liveSocket.onmessage=event=>{const data=JSON.parse(event.data);if(data.type==='interim'&&data.text){heardSpeech=true;setCallState('listening',data.text)}if(data.type==='final'&&data.text){liveFinal=data;if(recorder?.state==='recording')recorder.stop()}};
    recorder.onstop=async()=>{callMetrics.humanMs+=performance.now()-listeningStarted;
      if(liveSocket.readyState<2)liveSocket.close();stopCallAudio();if(!callActive||closingCall)return;if(!heardSpeech){setCallState('idle','Jee, main sun rahi hoon…');setTimeout(startLocalListening,250);return}turnBusy=true;setCallState('thinking','Jee…');
      if(liveFinal?.text){turnBusy=false;await send(liveFinal.text,true,liveFinal.display_text);return}
      const blob=new Blob(chunks,{type:recorder.mimeType});const form=new FormData();form.append('audio',blob,'call.webm');
      try{const res=await fetch('/api/transcribe',{method:'POST',body:form});const data=await res.json();if(!res.ok||!data.text?.trim()){turnBusy=false;await speak('Maazrat jee, awaaz clear nahi aayi. Aik dafa dobara boliye.');return}turnBusy=false;await send(data.text,true,data.display_text)}catch{turnBusy=false;await speak('Maazrat jee, line mein masla aa gaya tha. Dobara boliye.')}
    };
    const AudioEngine=window.AudioContext||window.webkitAudioContext;audioContext=new AudioEngine();await audioContext.resume();const source=audioContext.createMediaStreamSource(activeStream);const analyser=audioContext.createAnalyser();analyser.fftSize=1024;source.connect(analyser);const levels=new Uint8Array(analyser.fftSize);
    setCallState('listening','Jee, boliye…');recorder.start(100);
    const monitor=()=>{if(!callActive||recorder.state!=='recording')return;analyser.getByteTimeDomainData(levels);let energy=0;for(const value of levels){const sample=(value-128)/128;energy+=sample*sample}const rms=Math.sqrt(energy/levels.length);const now=performance.now();if(rms>.010){heardSpeech=true;silentSince=0;finalizeSent=false}else if(heardSpeech){if(!silentSince)silentSince=now;if(now-silentSince>650&&!finalizeSent&&liveSocket.readyState===WebSocket.OPEN){finalizeSent=true;liveSocket.send(JSON.stringify({type:'Finalize'}))}if(now-silentSince>1550){recorder.stop();return}}if(now-startedAt>(heardSpeech?16000:6500)){recorder.stop();return}silenceFrame=requestAnimationFrame(monitor)};monitor();
  }catch{setCallState('idle','Microphone ki ijazat dein, phir call dobara karein.')}
}
function speakInBrowser(text){
  if(!('speechSynthesis' in window))return Promise.resolve();
  return new Promise(resolve=>{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(phoneticRomanUrdu(text));u.voice=selectFemaleVoice();u.rate=.9;u.pitch=1.06;u.onend=resolve;u.onerror=resolve;speechSynthesis.speak(u)});
}
async function speak(text){
  stopCallAudio();speechSynthesis.cancel();if(callActive)setCallState('speaking',text);
  try{
    const speechStarted=performance.now();callMetrics.ttsChars+=text.length;
    let res=null;for(let attempt=0;attempt<2;attempt++){res=await fetch('/api/synthesize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});if(res.ok)break}
    if(!res?.ok)throw new Error('azure unavailable');
    if(res.body&&window.MediaSource&&MediaSource.isTypeSupported('audio/mpeg')){
      const mediaSource=new MediaSource();voiceAudio=new Audio(URL.createObjectURL(mediaSource));
      mediaSource.addEventListener('sourceopen',async()=>{const sourceBuffer=mediaSource.addSourceBuffer('audio/mpeg');const reader=res.body.getReader();const append=value=>new Promise((resolve,reject)=>{sourceBuffer.addEventListener('updateend',resolve,{once:true});sourceBuffer.addEventListener('error',reject,{once:true});sourceBuffer.appendBuffer(value)});try{voiceAudio.play().catch(()=>{});while(true){const {done,value}=await reader.read();if(done)break;if(value?.length)await append(value)}if(mediaSource.readyState==='open')mediaSource.endOfStream()}catch{if(mediaSource.readyState==='open')mediaSource.endOfStream('network')}} ,{once:true});
    }else{const blob=await res.blob();voiceAudio=new Audio(URL.createObjectURL(blob))}
    await new Promise((resolve,reject)=>{voiceDone=resolve;voiceAudio.onplay=()=>{if(window.turnSentAt){callMetrics.delays.push(performance.now()-window.turnSentAt);window.turnSentAt=0}};voiceAudio.onended=()=>{callMetrics.aiMs+=performance.now()-speechStarted;resolve()};voiceAudio.onerror=reject;voiceAudio.play().catch(reject)});voiceDone=null;
    if(voiceAudio){URL.revokeObjectURL(voiceAudio.src);voiceAudio=null}
  }catch{if(callActive)setCallState('idle','Awaaz reconnect ho rahi hai…')}
  if(callActive&&!closingCall)setTimeout(startLocalListening,120);
}
function bubble(text,who,withVoice=false){const el=document.createElement('div');el.className=`bubble ${who}`;el.textContent=text;messages.appendChild(el);messages.scrollTop=messages.scrollHeight;if(who==='agent'&&withVoice)speak(text)}
function renderCart(){const cart=document.querySelector('#cart');cart.innerHTML='';if(!session.cart.length)cart.innerHTML='<div class="empty">No items yet</div>';session.cart.forEach(item=>{const row=document.createElement('div');row.className='cart-row';const variant=item.notes?` <small>(${item.notes})</small>`:'';row.innerHTML=`<span>${item.quantity} × ${item.name}${variant}</span><strong>Rs. ${item.quantity*item.unit_price}</strong>`;cart.appendChild(row)});document.querySelector('#total').textContent=`Rs. ${session.total}`}
async function start(speakGreeting=false){const callerPhone=localStorage.getItem('nomnosh_customer_phone');const res=await fetch('/api/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({caller_phone:callerPhone})});session=await res.json();messages.innerHTML='';bubble(session.last_reply,'agent');renderCart();if(speakGreeting)await speak(session.last_spoken_reply||session.last_reply)}
async function send(text,fromCall=false,displayText=null){text=text.trim();if(!text||!session||turnBusy)return;turnBusy=true;stopCallAudio();bubble(displayText||text,'customer');if(fromCall)setCallState('thinking','Jee…');input.value='';const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),16000);try{const res=await fetch(`/api/sessions/${session.id}/messages`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text}),signal:controller.signal});const data=await res.json();if(!res.ok){const message=data.detail||'Conversation service unavailable';document.querySelector('#hint').textContent=message;throw new Error(message)}session=data.session;bubble(session.last_reply,'agent');renderCart();turnBusy=false;if(data.order&&session.customer_phone)localStorage.setItem('nomnosh_customer_phone',session.customer_phone);if(fromCall&&(data.order||session.end_call_requested)){closingCall=true;if(data.order)document.querySelector('#hint').textContent=`Order ${data.order.id} kitchen ko bhej diya gaya.`;await speak(session.last_spoken_reply||session.last_reply);setCallState('idle',data.order?'Order confirmed':'Call ended');setTimeout(endCall,250);return}if(fromCall)await speak(session.last_spoken_reply||session.last_reply)}catch(error){turnBusy=false;if(fromCall){setCallState('idle','OpenAI connection available nahi hai');await speak('Maazrat jee, call service filhaal available nahi hai.')}}finally{clearTimeout(timeout)}}
async function record(button,fromCall=false){
  if(recorder&&recorder.state==='recording'){recorder.stop();return}
  try{const stream=await navigator.mediaDevices.getUserMedia({audio:true});chunks=[];recorder=new MediaRecorder(stream);recorder.ondataavailable=e=>chunks.push(e.data);recorder.onstop=async()=>{button.classList.remove('recording');stream.getTracks().forEach(t=>t.stop());if(fromCall)setCallState('thinking','Aik lamha jee…');else document.querySelector('#hint').textContent='Transcribing locally…';const blob=new Blob(chunks,{type:recorder.mimeType});const form=new FormData();form.append('audio',blob,'order.webm');const res=await fetch('/api/transcribe',{method:'POST',body:form});const data=await res.json();if(!res.ok){const msg=friendlySpeechError(data.detail);if(fromCall)setCallState('idle',msg);else document.querySelector('#hint').textContent=msg;return}if(fromCall)await send(data.text,true);else{input.value=data.text;document.querySelector('#hint').textContent='Transcription ready—review it, then press Send.'}};recorder.start();button.classList.add('recording');if(fromCall)setCallState('listening','Jee, boliye…');else document.querySelector('#hint').textContent='Recording… tap stop when finished.'}catch(err){const msg='Microphone permission was not granted.';if(fromCall)setCallState('idle',msg);else document.querySelector('#hint').textContent=msg}
}
async function beginCall(){if(callActive)return;callActive=true;closingCall=false;turnBusy=false;callMetrics={humanMs:0,aiMs:0,delays:[],ttsChars:0};callStartedAt=Date.now();callScreen.classList.add('open');callScreen.setAttribute('aria-hidden','false');timerHandle=setInterval(()=>{const seconds=Math.floor((Date.now()-callStartedAt)/1000);document.querySelector('#call-timer').textContent=`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`},1000);await start(true)}
async function endCall(){const finishedSession=session;const duration=Math.max(0,(Date.now()-callStartedAt)/1000);callActive=false;closingCall=false;turnBusy=false;stopCallAudio();if(recorder&&recorder.state==='recording')recorder.stop();speechSynthesis.cancel();clearInterval(timerHandle);callScreen.classList.remove('open');callScreen.setAttribute('aria-hidden','true');if(!finishedSession)return;try{const res=await fetch(`/api/sessions/${finishedSession.id}/call-summary`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({duration_seconds:duration,human_talk_seconds:callMetrics.humanMs/1000,ai_talk_seconds:callMetrics.aiMs/1000,response_delays_ms:callMetrics.delays,elevenlabs_characters:callMetrics.ttsChars})});const report=await res.json();showCallReport(report)}catch{}}
function showCallReport(r){document.querySelector('#call-report')?.remove();const el=document.createElement('section');el.id='call-report';el.className='call-report';el.innerHTML=`<button aria-label="Close call report">×</button><strong>Call summary</strong><div>Total call <b>${r.duration_seconds}s</b> · You spoke <b>${r.human_talk_seconds}s</b> · Fatima spoke <b>${r.ai_talk_seconds}s</b></div><div>Average response delay <b>${r.average_response_delay_ms} ms</b></div><div>GPT: ${r.openai.input_tokens} input + ${r.openai.output_tokens} output tokens · <b>$${r.openai.estimated_usd.toFixed(4)}</b></div><div>Deepgram: ${r.deepgram.audio_seconds}s audio · ElevenLabs: ${r.elevenlabs.characters} characters</div><small>GPT cost uses current model list price. Deepgram and ElevenLabs show billable units because your plan pricing can differ.</small>`;el.querySelector('button').onclick=()=>el.remove();document.body.appendChild(el)}

document.querySelector('#composer').addEventListener('submit',e=>{e.preventDefault();send(input.value)});
document.querySelector('#finish').addEventListener('click',()=>send('bas order confirm karein'));
document.querySelector('#new-order').addEventListener('click',()=>start(false));
document.querySelector('#mic').addEventListener('click',e=>record(e.currentTarget,false));
document.querySelector('#call-fatima').addEventListener('click',beginCall);
document.querySelector('#call-mic').addEventListener('click',()=>{if(voiceAudio){stopCallAudio();turnBusy=false;startLocalListening();return}if(recorder?.state==='recording'){recorder.stop()}else startLocalListening()});
document.querySelector('#end-call').addEventListener('click',endCall);
speechSynthesis.onvoiceschanged=selectFemaleVoice;
start(false);
