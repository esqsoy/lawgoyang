// node pipeline/tests/judge.test.cjs — 판정 핵심 검사(설계안 C·D). 원문은 sources/web/minbeop-20260317.json.
const assert = require('assert');
const path = require('path');
const J = require(path.join(__dirname, '..', 'judge.js'));
const src = require(path.join(__dirname, '..', '..', 'sources', 'web', 'minbeop-20260317.json'));
let n = 0;
function t(name, f) { f(); n++; console.log('ok', name); }

const A750 = src.articles['750'].paras[0].text;
const ws = J.words('750조', { cite: true }).concat(J.words(A750).map(w => ({ ...w, key: ['고의', '과실로', '배상할', '책임이'].includes(J.wordText(w)) })));
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
t('사다리 1단계: 번호와 핵심어만 빈칸', () => {
  const g = J.givenMap(ws, 1);
  const blank = ws.filter((w, i) => g[i].some(x => !x)).map(J.wordText);
  assert.deepStrictEqual(blank, ['750조', '고의', '과실로', '배상할', '책임이']);
  assert.strictEqual(J.judge(ws, g, '750조고의과실로배상할책임이').verdict, '인용');
});
t('사다리 2단계: 어절 절반 이상, 번호·핵심어 포함', () => {
  const g = J.givenMap(ws, 2);
  const blank = ws.filter((w, i) => g[i].some(x => !x)).map(J.wordText);
  assert.ok(blank.length >= Math.ceil(ws.length / 2));
  ['750조', '고의', '과실로', '배상할', '책임이'].forEach(k => assert.ok(blank.includes(k), k));
});
t('사다리 3단계: 어절마다 첫 글자만 보임, 번호는 다 빈칸', () => {
  const g = J.givenMap(ws, 3);
  assert.deepStrictEqual(g[0], [false, false, false, false]);
  const i = ws.findIndex(w => J.wordText(w) === '위법행위로');
  assert.deepStrictEqual(g[i], [true, false, false, false, false]);
});
t('헷갈림 알림: 다른 조문 구절을 치면 그 조문을 알린다', () => {
  const others = [{ label: '제396조', text: src.articles['396'].paras[0].text }];
  const r = J.judge(ws, all4, '750조 채무불이행에 관하여 채권자에게 과실이 있는 때에는', {}, others);
  assert.strictEqual(r.confuse, '제396조');
});
t('원문 속 링크 말이 빠지지 않았다(제763조의 조 번호들)', () => {
  assert.strictEqual(src.articles['763'].paras[0].text, '제393조, 제394조, 제396조, 제399조의 규정은 불법행위로 인한 손해배상에 준용한다.');
});
console.log(n + '개 통과');
