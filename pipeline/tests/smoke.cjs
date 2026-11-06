// node pipeline/tests/smoke.cjs [proto.html 경로] [캡처 폴더] — 시제품 한 판을 브라우저로 돌려 본다.
// 1장 정답(인용) → 2장 '제1항'을 '제2항'으로(오답 → 틀린 어절만 따라쓰기) → 3·4장 넘기기(각하 → 따라쓰기) → 결과·숙련도.
const { chromium } = require('playwright');
const path = require('path');
const file = path.resolve(process.argv[2] || path.join(__dirname, '..', '..', 'proto.html'));
const shots = process.argv[3];
const assert = require('assert');

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  const errs = [];
  p.on('pageerror', e => errs.push(String(e)));
  await p.goto('file://' + file);
  await p.click('#start');
  // 지금 장에서 쳐야 할 글(미리 보인 칸 빼고)
  const want = () => p.evaluate(() => {
    const D = JSON.parse(document.getElementById('law-data').textContent), J = window.LawJudge;
    const i = Number(document.getElementById('prog').textContent.split('/')[0]) - 1, c = D.cards[i];
    const st = Number((JSON.parse(localStorage.getItem('lawgoyang-stage-v1') || '{}'))[c.skey]) || 1;
    const ws = J.words(c.cite, { cite: true }).concat(J.words(c.text));
    return J.expected(ws, J.givenMap(ws, st, c.phrase)).map(x => x.ch).join('');
  });
  const stampText = () => p.$eval('.stamp', e => e.textContent);
  const mode = () => p.evaluate(() => document.getElementById('nextBox').hidden ? 'ask-or-copy' : 'show');

  // 1장: 정답 → 인용, 자동 판정
  await p.focus('#ans');
  await p.keyboard.insertText(await want());
  assert.strictEqual(await stampText(), '인용');
  assert.strictEqual(await mode(), 'show');
  if (shots) await p.screenshot({ path: path.join(shots, '1-inyong.png'), fullPage: true });
  await p.keyboard.press('Enter');

  // 2장: 1단계는 번호만 빈칸. 제1항 → 제2항으로 틀린다
  const w2 = await want();
  assert.strictEqual(w2, '756조제1항본문');
  await p.keyboard.insertText('756조 제2항 본문');
  await p.keyboard.press('Enter');
  const v2 = await stampText();
  assert.strictEqual(v2, '일부인용');
  const ghost = await p.$$eval('#blank .bx.ghost', xs => xs.map(x => x.textContent).join(''));
  assert.strictEqual(ghost, '제1항');
  if (shots) await p.screenshot({ path: path.join(shots, '2-copy.png'), fullPage: true });
  await p.keyboard.insertText('제1항');
  assert.strictEqual(await mode(), 'show');
  await p.keyboard.press('Enter');

  // 3·4장: 넘기기 → 각하 → 따라쓰기
  for (let k = 0; k < 2; k++) {
    const w = await want();
    await p.click('#skip');
    assert.strictEqual(await stampText(), '각하');
    await p.focus('#ans');
    await p.keyboard.insertText(w);
    assert.strictEqual(await mode(), 'show');
    await p.keyboard.press('Enter');
  }
  // 결과·숙련도
  assert.ok(!(await p.$eval('#result', e => e.hidden)));
  const rows = await p.$$eval('#resRows tr', xs => xs.map(x => x.textContent));
  assert.strictEqual(rows.length, 4);
  const st = JSON.parse(await p.evaluate(() => localStorage.getItem('lawgoyang-stage-v1')));
  assert.strictEqual(st['민법:750'], 2);
  assert.strictEqual(st['민법:756:1:본문'], 1);
  if (shots) await p.screenshot({ path: path.join(shots, '3-result.png'), fullPage: true });
  // 한 판 더: 750은 2단계(첫 단어까지)로 나온다
  await p.click('#again');
  assert.ok((await p.textContent('#stageChip')).includes('2단계 · 첫 단어까지'));
  assert.strictEqual(await want(), '750조고의');
  const sw = await p.evaluate(() => document.documentElement.scrollWidth);
  assert.ok(sw <= 390, 'scrollWidth ' + sw);
  assert.deepStrictEqual(errs, []);
  console.log('smoke ok:', rows.join(' / '));
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
