/* 기록 옮기기 공용 코드: esqsoy/tangogoyang index.html @ f652afe 의 RECORD_TRANSFER 구간에서 RT_CONFIG 아래를 그대로 떼어 옴(2026-11-07).
   탄고고양 사본은 보카고양 공개 index(26.11.06)에서 가져온 것이다. 고치지 말고, 본가가 바뀌면 다시 떼어 온다. 설정은 build.py의 RT_CONFIG. */
var RT_CFG=typeof RT_CONFIG!=='undefined'?RT_CONFIG:require('./config.json');
var RT_APP=RT_CFG.app,RT_VERSION=1,RT_PREFIX=RT_CFG.prefix,RT_GAME=RT_CFG.game;
var RT_SKIP=RT_CFG.skip||[];                // 검사용 키 등 옮기지 않는 것
var RT_KINDS=Object.keys(RT_CFG.kinds||{}).map(kind=>[kind,new RegExp(RT_CFG.kinds[kind])]);   // 위에서부터 처음 맞는 종류
var RT_PACE_KEEP=600;                       // pace 런타임의 paceKeep과 같다

function rtWanted(k){return typeof k==='string'&&k.startsWith(RT_PREFIX)&&!RT_SKIP.includes(k);}
function rtCollect(store){
  const data={};
  for(let i=0;i<store.length;i++){const k=store.key(i);if(!rtWanted(k))continue;const v=store.getItem(k);if(typeof v==='string')data[k]=v;}
  return data;
}
function rtPack(data,now){return {app:RT_APP,v:RT_VERSION,exportedAt:new Date(now).toISOString(),data};}
function rtParse(text){
  let o;try{o=JSON.parse(text);}catch(e){throw new Error('파일이 깨졌다고양. 내보낸 파일을 그대로 골라 달라고양.');}
  if(!o||typeof o!=='object'||o.app!==RT_APP||!o.data||typeof o.data!=='object'||Array.isArray(o.data))throw new Error(RT_GAME+' 기록 파일이 아니라고양.');
  if(!(Number(o.v)>=1))throw new Error(RT_GAME+' 기록 파일이 아니라고양.');
  if(Number(o.v)>RT_VERSION)throw new Error('더 새 판에서 만든 파일이라고양. 이 화면을 새로고침하고 다시 해 보라고양.');
  const data={};Object.keys(o.data).forEach(k=>{if(rtWanted(k)&&typeof o.data[k]==='string')data[k]=o.data[k];});
  return {exportedAt:typeof o.exportedAt==='string'?o.exportedAt:'',data};
}

function rtJson(s){if(typeof s!=='string')return undefined;try{return JSON.parse(s);}catch(e){return undefined;}}
function rtObj(v){return v&&typeof v==='object'&&!Array.isArray(v)?v:null;}
function rtKind(k){
  for(const [kind,re] of RT_KINDS)if(RT_MERGE[kind]&&re.test(k))return kind;
  return 'keep';                              // 설정·이어하기 자리 등: 이 기기에 없을 때만 가져온다
}
/* 종류마다 합친다. 반환값: {value: 새 문자열(바뀌지 않으면 null), n: 늘어난 개수} */
var RT_MERGE={
  // 진도 {묶음: {연습: {completed, bestMs…}}}: 한쪽이라도 클리어했으면 클리어. 둘 다면 이 기기 것을 두고 최고 시간만 더 빠른 쪽으로.
  progress(a,b){
    const L=rtObj(rtJson(a))||{},I=rtObj(rtJson(b));if(!I)return {value:null,n:0};
    let n=0,changed=false;
    Object.keys(I).forEach(lid=>{const ib=rtObj(I[lid]);if(!ib)return;
      Object.keys(ib).forEach(t=>{const r=rtObj(ib[t]);if(!r)return;
        const lb=rtObj(L[lid])||(L[lid]={}),cur=rtObj(lb[t]);
        if(!cur){lb[t]=r;changed=true;if(r.completed)n++;return;}
        if(!cur.completed&&r.completed){lb[t]=r;changed=true;n++;return;}
        if(cur.completed&&r.completed&&Number(r.bestMs)>0&&!(Number(cur.bestMs)>0&&Number(cur.bestMs)<=Number(r.bestMs))){cur.bestMs=Number(r.bestMs);changed=true;}
      });});
    return {value:changed?JSON.stringify(L):null,n};
  },
  // 모아둔 카드 [{id, addedAt}]: 양쪽에 담은 카드를 다 남긴다. 이 기기 순서를 두고 새 카드는 담은 순서대로 뒤에.
  saved(a,b){
    const list=r=>Array.isArray(r)?r.filter(x=>x&&typeof x.id==='string'):[];
    const L=list(rtJson(a)),I=list(rtJson(b)),at=new Map(L.map(x=>[x.id,x]));
    let n=0,changed=false;
    I.slice().sort((x,y)=>(Number(x.addedAt)||0)-(Number(y.addedAt)||0)).forEach(x=>{
      const cur=at.get(x.id),t=Number(x.addedAt)||0;
      if(!cur){const r={id:x.id,addedAt:t};L.push(r);at.set(x.id,r);n++;changed=true;}
      else if(t>0&&!(Number(cur.addedAt)>0&&Number(cur.addedAt)<=t)){cur.addedAt=t;changed=true;}
    });
    return {value:changed?JSON.stringify(L):null,n};
  },
  // 익힌 단어 {교재: [표제어…]}: 교재마다 합집합(이 기기 순서 먼저). 교재를 열면 진도로 다시 맞춘다.
  learned(a,b){
    const L=rtObj(rtJson(a))||{},I=rtObj(rtJson(b));if(!I)return {value:null,n:0};
    let changed=false;
    Object.keys(I).forEach(c=>{if(!Array.isArray(I[c]))return;const cur=Array.isArray(L[c])?L[c]:(L[c]=[]),has=new Set(cur);
      I[c].forEach(k=>{if(typeof k==='string'&&k&&!has.has(k)){has.add(k);cur.push(k);changed=true;}});});
    return {value:changed?JSON.stringify(L):null,n:0};
  },
  // 틀렸던 단어 {표제어: 횟수}: 더 큰 쪽. 더하면 같은 파일을 두 번 합칠 때 부풀어 오른다.
  missed(a,b){
    const L=rtObj(rtJson(a))||{},I=rtObj(rtJson(b));if(!I)return {value:null,n:0};
    let changed=false;
    Object.keys(I).forEach(k=>{const v=Number(I[k])||0;if(v>(Number(L[k])||0)){L[k]=v;changed=true;}});
    return {value:changed?JSON.stringify(L):null,n:0};
  },
  // 돌파 축하 {seen}: 더 큰 쪽(이미 본 축하를 다시 띄우지 않는다).
  milestone(a,b){
    const l=Number(rtObj(rtJson(a))?.seen)||0,i=Number(rtObj(rtJson(b))?.seen)||0;
    return {value:i>l?JSON.stringify({seen:i}):null,n:0};
  },
  // 세트 도장 {세트: 받은 때}: 어느 쪽에서든 받은 도장은 남긴다. 둘 다 있으면 이 기기 것.
  stamps(a,b){
    const L=rtObj(rtJson(a)),I=rtObj(rtJson(b));if(!I)return {value:null,n:0};
    const out=L||{};let n=0,changed=!L&&Object.keys(I).length>0;
    Object.keys(I).forEach(k=>{if(!Object.prototype.hasOwnProperty.call(out,k)){out[k]=Number(I[k])||0;n++;changed=true;}});
    return {value:changed?JSON.stringify(out):null,n};
  },
  // 진행 속도 기록 [{at, ms, u, k}]: 합쳐서 시간순, 최근 600판.
  pace(a,b){
    const list=r=>Array.isArray(r)?r.filter(x=>x&&Number(x.at)>0):[];
    const L=list(rtJson(a)),I=list(rtJson(b)),key=x=>x.at+'|'+x.ms,seen=new Set(L.map(key));
    const add=I.filter(x=>!seen.has(key(x)));if(!add.length)return {value:null,n:0};
    const all=L.concat(add).sort((x,y)=>x.at-y.at).slice(-RT_PACE_KEEP);
    return {value:JSON.stringify(all),n:0};
  },
  // 진행 속도 메타 {total, target…}: 판 수는 큰 쪽, 나머지는 이 기기에 없을 때만.
  paceMeta(a,b){
    const L=rtObj(rtJson(a))||{},I=rtObj(rtJson(b));if(!I)return {value:null,n:0};
    let changed=false;
    Object.keys(I).forEach(k=>{
      if(k==='total'){const v=Number(I.total);if(Number.isFinite(v)&&!(Number.isFinite(Number(L.total))&&Number(L.total)>=v)){L.total=v;changed=true;}}
      else if(!Object.prototype.hasOwnProperty.call(L,k)){L[k]=I[k];changed=true;}
    });
    return {value:changed?JSON.stringify(L):null,n:0};
  },
  keep(a,b){return {value:a==null&&typeof b==='string'?b:null,n:0};}
};
/* local·incoming: {키: 문자열}. 반환: {writes: {키: 새 문자열}, summary: {exercises, saved, stamps}} */
function rtMerge(local,incoming){
  const writes={},summary={exercises:0,saved:0,stamps:0};
  Object.keys(incoming||{}).forEach(k=>{
    if(!rtWanted(k)||typeof incoming[k]!=='string')return;
    const kind=rtKind(k),a=Object.prototype.hasOwnProperty.call(local,k)?local[k]:null;
    const r=a==null&&kind!=='keep'?{value:incoming[k],n:RT_COUNT[kind]?RT_COUNT[kind](incoming[k]):0}:RT_MERGE[kind](a,incoming[k]);
    if(r.value!=null&&r.value!==a)writes[k]=r.value;
    if(kind==='progress')summary.exercises+=r.n;else if(kind==='saved')summary.saved+=r.n;else if(kind==='stamps')summary.stamps+=r.n;
  });
  return {writes,summary};
}
/* 이 기기에 그 키가 아예 없을 때 가져오는 개수 */
var RT_COUNT={
  progress(s){let n=0;const o=rtObj(rtJson(s))||{};Object.values(o).forEach(b=>{if(rtObj(b))Object.values(b).forEach(r=>{if(rtObj(r)?.completed)n++;});});return n;},
  saved(s){const r=rtJson(s);return Array.isArray(r)?r.filter(x=>x&&typeof x.id==='string').length:0;},
  stamps(s){const o=rtObj(rtJson(s));return o?Object.keys(o).length:0;}
};
(function(){
  const $=id=>document.getElementById(id);
  const sheet=$('rtSheet'),status=$('rtStatus'),file=$('rtFile'),confirmBox=$('rtConfirm');
  if(!sheet)return;
  let pending=null;
  function say(text,kind){status.textContent=text;status.className='rt-status'+(kind?' '+kind:'');}
  function open(){sheet.hidden=false;document.body.classList.add('rt-lock');say('');confirmBox.hidden=true;pending=null;$('rtMake').focus();}
  function close(){sheet.hidden=true;document.body.classList.remove('rt-lock');pending=null;if(location.hash==='#records')history.replaceState(null,'',location.pathname+location.search);}
  function store(){try{return window.localStorage;}catch(e){return null;}}
  function today(){const d=new Date(),p=n=>String(n).padStart(2,'0');return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate());}
  $('rtOpen').addEventListener('click',open);
  $('rtClose').addEventListener('click',close);
  sheet.addEventListener('click',e=>{if(e.target===sheet)close();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!sheet.hidden)close();});
  if(location.hash==='#records')open();

  // ① 기록 파일 만들기: 폰이면 공유 시트(카톡 '나와의 채팅' 등), 아니면 파일로 저장.
  $('rtMake').addEventListener('click',async()=>{
    const s=store();if(!s){say('이 브라우저는 기록을 저장하지 못한다고양.','bad');return;}
    const data=rtCollect(s);
    if(!Object.keys(data).length){say('아직 옮길 기록이 없다고양. 한 판이라도 하고 오라고양.','bad');return;}
    const text=JSON.stringify(rtPack(data,Date.now())),name=RT_GAME+'-기록-'+today()+'.json';
    const blob=new Blob([text],{type:'application/json'});
    try{
      const f=new File([blob],name,{type:'application/json'});
      if(navigator.canShare&&navigator.canShare({files:[f]})&&matchMedia('(pointer:coarse)').matches){
        await navigator.share({files:[f],title:RT_GAME+' 기록'});
        say('보냈다고양. 다른 기기에서 그 파일을 열면 된다고양.','ok');return;
      }
    }catch(e){if(e&&e.name==='AbortError'){say('');return;}}
    const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;document.body.appendChild(a);a.click();
    setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},1000);
    say('‘'+name+'’을 저장했다고양. 이 파일을 다른 기기로 보내라고양.','ok');
  });

  // ② 기록 파일 열기: 읽고, 무엇이 늘어나는지 보여 준 뒤 합친다.
  file.addEventListener('change',()=>{
    const f=file.files&&file.files[0];file.value='';if(!f)return;
    const s=store();if(!s){say('이 브라우저는 기록을 저장하지 못한다고양.','bad');return;}
    const r=new FileReader();
    r.onerror=()=>say('파일을 못 읽었다고양.','bad');
    r.onload=()=>{
      let got;try{got=rtParse(String(r.result||''));}catch(e){say(e.message,'bad');confirmBox.hidden=true;return;}
      const m=rtMerge(rtCollect(s),got.data),keys=Object.keys(m.writes);
      if(!keys.length){say('이미 이 기기에 다 있는 기록이라고양. 합칠 게 없다고양.','ok');confirmBox.hidden=true;return;}
      pending=m;
      const parts=[];
      if(m.summary.exercises)parts.push('클리어한 연습 '+m.summary.exercises+'개');
      if(m.summary.stamps)parts.push('세트 도장 '+m.summary.stamps+'개');
      if(m.summary.saved)parts.push('모아둔 카드 '+m.summary.saved+'장');
      say((parts.length?parts.join(' · ')+'이 늘어난다고양.':'자잘한 기록이 더해진다고양.')+' 이 기기 기록은 지우지 않고 합친다고양.');
      confirmBox.hidden=false;$('rtMerge').focus();
    };
    r.readAsText(f);
  });
  $('rtMerge').addEventListener('click',()=>{
    const s=store();if(!pending||!s)return;
    const w=pending.writes;
    try{Object.keys(w).forEach(k=>s.setItem(k,w[k]));}
    catch(e){say('저장 공간이 모자라서 다 못 합쳤다고양. 브라우저 저장 공간을 확인하라고양.','bad');return;}
    pending=null;confirmBox.hidden=true;
    say('합쳤다고양! 이제 교재를 열면 이어서 할 수 있다고양. 다른 탭에 게임이 열려 있으면 새로고침하라고양.','ok');
  });
  $('rtCancel').addEventListener('click',()=>{pending=null;confirmBox.hidden=true;say('안 합쳤다고양.');});
})();
