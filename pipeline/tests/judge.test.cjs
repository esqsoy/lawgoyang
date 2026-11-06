// node pipeline/tests/judge.test.cjs — 판정 핵심 검사(설계안 C·D). 원문은 sources/web/minbeop-20260317.json.
const assert = require('assert');
const path = require('path');
const J = require(path.join(__dirname, '..', 'judge.js'));
const src = require(path.join(__dirname, '..', '..', 'sources', 'web', 'minbeop-20260317.json'));
let n = 0;
function t(name, f) { f(); n++; console.log('ok', name); }

const A750 = src.articles['750'].paras[0].text;
const ws = J.words('750조', { cite: true }).concat(J.words(A750));
const P750 = '고의 또는 과실로 인한 위법행위로';
const all4 = J.givenMap(ws, 4);
const answer = '750조' + A750;

t('구두점·공백은 치지 않는다', () => {
  assert.deepStrictEqual(J.norm('있다.)'), Array.from('있다'));
  assert.deepStrictEqual(J.norm('선임ㆍ감독'), Array.from('선임감독'));
});
t('원문 그대로 치면 인용(공백 없이 쳐도)', () => {
  assert.strictEqual(J.judge(ws, all4, answer.replace(/\s/g, '')).verdict, '인용');
  assert.strictEqual(J.judge(ws, all4, answer).verdict, '인용');
});
t('아무것도 안 치면 각하', () => { assert.strictEqual(J.judge(ws, all4, '').verdict, '각하'); });
t('한 글자 빼먹어도 그 어절만 틀린다(뒤 어절이 줄줄이 틀리지 않음)', () => {
  const r = J.judge(ws, all4, answer.replace('위법행위로', '위법위로'));
  assert.deepStrictEqual(r.wrong.map(i => J.wordText(ws[i])), ['위법행위로']);
  assert.strictEqual(r.verdict, '일부인용');
});
t('한 글자 더 쳐도 그 어절만 틀린다', () => {
  const r = J.judge(ws, all4, answer.replace('타인에게', '타인에게서'));
  assert.deepStrictEqual(r.wrong.map(i => J.wordText(ws[i])), ['타인에게']);
});
t('같은 뜻 다른 말은 틀림 + 뜻은 맞음 표시(사람이 확인한 짝만)', () => {
  const r = J.judge(ws, all4, answer.replace('가한', '입힌'), { '가한': ['입힌'] });
  assert.strictEqual(r.verdict, '일부인용');
  assert.deepStrictEqual(r.near.map(x => x.want), ['가한']);
  const r2 = J.judge(ws, all4, answer.replace('가한', '입힌'), {});
  assert.strictEqual(r2.near.length, 0);
});
t('틀린 어절이 3분의 1을 넘으면 기각', () => {
  const r = J.judge(ws, all4, '750조 누구든지 다른 사람을 다치게 하면 물어 주어야 한다');
  assert.strictEqual(r.verdict, '기각');
});
t('번호를 틀리면 번호 어절이 틀린다', () => {
  const r = J.judge(ws, all4, answer.replace('750조', '751조'));
  assert.deepStrictEqual(r.wrong.map(i => J.wordText(ws[i])), ['750조']);
});
const blankWords = g => ws.filter((w, i) => g[i].some(x => !x)).map(J.wordText);
t('사다리 1단계: 번호만 빈칸', () => {
  assert.deepStrictEqual(blankWords(J.givenMap(ws, 1, P750)), ['750조']);
  assert.strictEqual(J.judge(ws, J.givenMap(ws, 1, P750), '750조').verdict, '인용');
});
t('사다리 2단계: 번호 + 첫 단어', () => {
  assert.deepStrictEqual(blankWords(J.givenMap(ws, 2, P750)), ['750조', '고의']);
});
t('사다리 3단계: 번호 + 첫 문구(카드에 정한 것)', () => {
  assert.deepStrictEqual(blankWords(J.givenMap(ws, 3, P750)), ['750조', '고의', '또는', '과실로', '인한', '위법행위로']);
  assert.strictEqual(J.stage3Len(ws, P750).kind, '첫 문구');
});
t('사다리 3단계: 두 문장 이상이면 첫 문장', () => {
  const t756 = src.articles['756'].paras[0].text; // 본문 + 단서(그러나 …) 두 문장
  const w2 = J.words('756조 제1항', { cite: true }).concat(J.words(t756));
  const r = J.stage3Len(w2, '');
  assert.strictEqual(r.kind, '첫 문장');
  assert.strictEqual(J.wordText(w2.filter(w => !w.cite)[r.len - 1]), '있다');
});
t('사다리 3단계: 첫 문구가 원문과 안 맞으면 쉼표·절반으로 대신', () => {
  assert.strictEqual(J.stage3Len(ws, '엉뚱한 문구').len, Math.ceil(14 / 2));
});
t('사다리 4단계: 통빈칸, 앞에서부터만 커진다', () => {
  assert.strictEqual(blankWords(J.givenMap(ws, 4, P750)).length, ws.length);
  for (let s = 1; s < 4; s++) {
    const a = blankWords(J.givenMap(ws, s, P750)), b = blankWords(J.givenMap(ws, s + 1, P750));
    assert.deepStrictEqual(b.slice(0, a.length), a);
  }
});
t('헷갈림 알림: 다른 조문 구절을 치면 그 조문을 알린다', () => {
  const others = [{ label: '제396조', text: src.articles['396'].paras[0].text }];
  const r = J.judge(ws, all4, '750조 채무불이행에 관하여 채권자에게 과실이 있는 때에는', {}, others);
  assert.strictEqual(r.confuse, '제396조');
});
t('원문 속 링크 말이 빠지지 않았다(제763조의 조 번호들)', () => {
  assert.strictEqual(src.articles['763'].paras[0].text, '제393조, 제394조, 제396조, 제399조의 규정은 불법행위로 인한 손해배상에 준용한다.');
});
t('괄호 속 한자 풀이는 치지 않는다(보여 주기만)', () => {
  const w = J.words('경정결정(更正決定)을');
  assert.strictEqual(J.wordText(w[0]), '경정결정을');
  assert.deepStrictEqual(J.norm('경정결정(更正決定)을'), Array.from('경정결정을'));
});
console.log(n + '개 통과');
