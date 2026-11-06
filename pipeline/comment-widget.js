/* 줄 댓글: .ln 줄을 누르면 입력칸이 열리고 Enter로 바로 Claude에게 보낸다(comments 권한의 sendToClaude).
   보카고양 직검수 방식(26.10.11 영신)을 법학고양 페이지에 맞게 옮긴 것. 페이지에 #cmhint가 있어야 한다.
   Artifact를 capabilities {comments: {}}로 올려야 동작한다. */
(function(){
const hint=document.getElementById('cmhint');
const ERR={consent_required:'허락 창에서 허용해야 보낼 수 있어. 쓴 글은 그대로 뒀어.',
forbidden:'이 화면에선 페이지에서 댓글 달기가 꺼져 있어. 범위를 지정하는 기존 댓글로 달아 줘.',
rate_limited:'너무 빨리 보냈어. 잠깐 뒤에 Enter를 다시 눌러 줘.',
claude_unavailable:'Claude에게 바로 보내기가 지금 안 돼. 쓴 글은 그대로 뒀어.',
invalid:'글이 너무 길거나 쓸 수 없는 글자가 있어.'};
let cm=null,open=null,shift=false;
function say(box,msg,cls){const s=box.querySelector('.st');s.textContent=msg;s.className='st'+(cls?' '+cls:'');}
function closeBox(){if(!open)return;open.box.remove();open.line.classList.remove('on');open=null;}
function off(msg){document.body.classList.remove('cm-on');closeBox();hint.textContent=msg;}
async function send(o){
  const ta=o.box.querySelector('textarea'),go=o.box.querySelector('.go'),text=ta.value.trim();
  if(!text||o.busy)return;
  o.busy=true;ta.readOnly=true;go.disabled=true;say(o.box,'보내는 중…');
  try{
    const anchor=await cm.anchorFor(o.line);
    let can='off';try{can=await cm.canSendToClaude();}catch(_){}
    if(can==='available'){await cm.sendToClaude({anchor,text});say(o.box,'Claude에게 보냈어.','ok');}
    else{await cm.create({anchor,text});say(o.box,'댓글로 남겼어. 바로 보내기가 지금 안 돼서, 대화창에 "댓글 봐줘"라고 해 줘.','err');}
    o.line.classList.add('sent');ta.value='';
    setTimeout(()=>{if(open===o)closeBox();},1500);
  }catch(err){
    const c=err&&err.code;
    say(o.box,ERR[c]||'못 보냈어. 쓴 글은 그대로 뒀어. 잠깐 뒤에 Enter를 다시 눌러 줘.','err');
    if(c==='forbidden'||c==='not_granted'||c==='capability_disabled'||c==='capability_removed')setTimeout(()=>off('이 화면에선 줄 댓글이 꺼져 있어. 범위를 지정하는 기존 댓글로 달아 줘.'),2500);
  }finally{o.busy=false;ta.readOnly=false;go.disabled=false;}
}
function openBox(line){
  if(open&&open.line===line){open.box.querySelector('textarea').focus();return;}
  if(open&&open.box.querySelector('textarea').value.trim()){open.box.querySelector('textarea').focus();say(open.box,'쓰던 글이 있어. 보내거나 Esc로 닫고 옮겨 줘.','err');return;}
  closeBox();
  const box=document.createElement(line.tagName==='LI'?'li':(line.tagName==='TR'?'tr':'div'));
  box.className='cbox';box.setAttribute('data-uncommentable','');
  const inner='<textarea rows="1" enterkeyhint="send" maxlength="1300"></textarea><div class="row"><span class="st">Enter로 바로 보내기 · 줄바꿈은 Shift+Enter · Esc 닫기</span><button type="button" class="go">보내기</button></div>';
  box.innerHTML=line.tagName==='TR'?'<td colspan="3"><div class="cbox" style="border:0;padding:0;margin:0">'+inner+'</div></td>':inner;
  if(line.tagName==='TR'){box.className='';box.setAttribute('data-uncommentable','');}
  const ta=box.querySelector('textarea');ta.setAttribute('aria-label','이 줄에 댓글');ta.placeholder='이 줄에 대한 의견';
  line.after(box);line.classList.add('on');
  const o={line,box,busy:false};open=o;
  ta.addEventListener('keydown',ev=>{
    if(ev.key==='Shift')shift=true;
    if(ev.key==='Escape'){ev.preventDefault();closeBox();return;}
    if(ev.key==='Enter'&&!ev.shiftKey){if(ev.isComposing||ev.keyCode===229)return;ev.preventDefault();send(o);}
  });
  ta.addEventListener('keyup',ev=>{if(ev.key==='Shift')shift=false;});
  ta.addEventListener('beforeinput',ev=>{if((ev.inputType==='insertLineBreak'||ev.inputType==='insertParagraph')&&!shift){ev.preventDefault();send(o);}});
  ta.addEventListener('input',()=>{ta.style.height='auto';ta.style.height=ta.scrollHeight+'px';});
  box.querySelector('.go').addEventListener('click',()=>send(o));
  ta.focus();
}
document.addEventListener('click',ev=>{
  if(!document.body.classList.contains('cm-on'))return;
  if(ev.target.closest('.cbox,[data-uncommentable],a,button'))return;
  const line=ev.target.closest('.ln');if(!line)return;
  const sel=window.getSelection();if(sel&&!sel.isCollapsed)return;
  openBox(line);
});
(async()=>{
  try{cm=await window.claude.use('comments');}catch(_){cm=null;}
  if(!cm){hint.textContent='이 화면에선 줄 댓글을 쓸 수 없어. 범위를 지정하는 기존 댓글로 달아 줘.';return;}
  document.body.classList.add('cm-on');
  hint.textContent='줄을 누르면 입력칸이 열려. 쓰고 Enter를 누르면 바로 Claude에게 가. 줄바꿈은 Shift+Enter.';
})();
})();
