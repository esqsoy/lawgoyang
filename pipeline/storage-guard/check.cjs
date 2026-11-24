'use strict';
/* 저장 키 검사기(같이 쓰는 파일, SHARED.md). 같은 주소(esqsoy.github.io)의 게임들이 저장 공간을 함께 쓰므로,
   한 게임이 남의 키를 쓰거나 저장 공간을 통째로 지우면 다른 게임의 학생 기록이 섞이거나 사라진다.
   26.11.13 Claude(영신 "나머지는 네 판단에 맡길게"). 규칙과 이유는 README.
   사용: node pipeline/storage-guard/check.cjs [--json]   (config.json의 targets를 registry.json 기준으로 본다) */
const fs=require('fs'),path=require('path');
const DIR=__dirname,ROOT=path.join(DIR,'..','..');

// 장부 검사: 앞머리는 구분 기호로 끝나고, 어느 게임의 앞머리도 다른 게임 앞머리로 시작하지 않는다.
function checkRegistry(reg){
  const out=[],all=[];
  for(const g of reg.games||[])for(const p of g.prefixes||[]){
    if(!/^[a-z0-9]+(?:[-_][a-z0-9]+)*[-_]$/.test(p))out.push(`장부: ${g.game} 앞머리 '${p}'는 소문자로 시작해 - 또는 _로 끝나야 한다`);
    all.push([g.game,p]);
  }
  for(const [ga,a] of all)for(const [gb,b] of all)if(ga!==gb&&b.startsWith(a))out.push(`장부: ${gb}의 '${b}'가 ${ga}의 '${a}'로 시작한다. ${ga} 기록 옮기기가 ${gb} 키까지 집는다`);
  return out;
}
// /* */ 주석은 빼고 본다(설명 글의 'goyang-' 같은 언급은 키가 아니다).
function stripBlockComments(s){return s.replace(/\/\*[\s\S]*?\*\//g,' ');}
function checkPage(src,own,foreign,label){
  const out=[],s=stripBlockComments(src);
  const banned=[[/\blocalStorage\s*\.\s*clear\s*\(/,'localStorage.clear(): 같은 주소의 모든 게임 기록을 지운다'],
    [/\bsessionStorage\b/,'sessionStorage: 이 시리즈는 localStorage만 쓴다'],
    [/\bindexedDB\s*\.\s*(?:open|deleteDatabase)\s*\(/,'indexedDB: 저장 공간 규칙 밖이다'],
    [/\bserviceWorker\s*\.\s*register\s*\(/,'serviceWorker.register: 범위를 잘못 잡으면 같은 주소의 다른 게임까지 가로챈다'],
    [/\bdocument\s*\.\s*cookie\s*=/,'document.cookie 쓰기: 같은 주소의 모든 게임에 붙는다']];
  for(const [re,msg] of banned)if(re.test(s))out.push(`${label}: ${msg}`);
  // 저장 함수에 글자 그대로 넘긴 키는 이 게임 앞머리로 시작해야 한다.
  for(const m of s.matchAll(/\blocalStorage\s*\.\s*(?:getItem|setItem|removeItem)\s*\(\s*(["'`])([^"'`]*)\1/g)){
    if(!own.some(p=>m[2].startsWith(p)))out.push(`${label}: 앞머리 없는 저장 키 '${m[2]}' (이 게임 앞머리 ${own.join(', ')})`);
  }
  // 다른 게임 앞머리로 시작하는 글자(앞머리보다 긴 것)는 남의 키를 베껴 온 것이다.
  const seen=new Set();
  for(const m of s.matchAll(/(["'`])([a-z0-9_][a-z0-9_.:-]{1,80})\1/g)){
    const v=m[2];
    for(const p of foreign)if(v.startsWith(p)&&v.length>p.length&&!own.some(o=>v.startsWith(o))&&!seen.has(v)){seen.add(v);out.push(`${label}: 다른 게임 키 '${v}' (앞머리 '${p}')`);}
  }
  return out;
}
function run(opts={}){
  const reg=opts.registry||JSON.parse(fs.readFileSync(path.join(DIR,'registry.json'),'utf8'));
  const cfg=opts.config||JSON.parse(fs.readFileSync(path.join(DIR,'config.json'),'utf8'));
  const root=opts.root||ROOT;
  const me=(reg.games||[]).find(g=>g.game===cfg.game);
  const problems=checkRegistry(reg);
  if(!me){problems.push(`장부에 '${cfg.game}'가 없다. registry.json에 먼저 올린다(본가에 요청)`);return problems;}
  const foreign=reg.games.filter(g=>g!==me).flatMap(g=>g.prefixes);
  for(const t of cfg.targets||[]){
    const f=path.join(root,t);
    if(!fs.existsSync(f)){problems.push(`${t}: 파일이 없다`);continue;}
    problems.push(...checkPage(fs.readFileSync(f,'utf8'),me.prefixes,foreign,t));
  }
  return problems;
}
module.exports={checkRegistry,checkPage,run};
if(require.main===module){
  const p=run();
  if(process.argv.includes('--json'))console.log(JSON.stringify(p,null,1));
  else console.log(p.length?p.join('\n'):'storage-guard: 문제 없음');
  process.exit(p.length?1:0);
}
