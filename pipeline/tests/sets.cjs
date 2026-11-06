// node pipeline/tests/sets.cjs [proto.html] — 모든 세트를 브라우저로 한 판씩 돈다(그 단계 정답을 그대로 쳐서 인용).
// 세트 데이터가 화면에서 깨지지 않는지, 페이지 오류가 없는지, 가로로 넘치지 않는지 본다.
const { chromium } = require('playwright');
const path = require('path');
const assert = require('assert');
const file = path.resolve(process.argv[2] || path.join(__dirname, '..', '..', 'proto.html'));
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  const errs = [];
  p.on('pageerror', e => errs.push(String(e)));
  await p.goto('file://' + file);
  const ids = await p.$$eval('.set', xs => xs.map(x => x.dataset.id));
  let cards = 0, maxW = 0;
  for (const id of ids) {
    await p.evaluate(() => { localStorage.removeItem('lawgoyang-stage-v1'); });
    await p.goto('file://' + file);
    await p.click(`.set[data-id="${id}"]`);
    const n = await p.evaluate(sid => JSON.parse(document.getElementById('law-data').textContent).sets.find(s => s.id === sid).cards.length, id);
    for (let i = 0; i < n; i++) {
      const want = await p.evaluate(sid => {
        const D = JSON.parse(document.getElementById('law-data').textContent), J = window.LawJudge;
        const k = Number(document.getElementById('prog').textContent.split('/')[0]) - 1, c = D.sets.find(s => s.id === sid).cards[k];
        const ws = J.words(c.cite, { cite: true }).concat(J.words(c.text));
        const st = Number((JSON.parse(localStorage.getItem('lawgoyang-stage-v1') || '{}'))[c.skey]) || 1; // 같은 조문이 세트에 두 번 나오면 둘째는 오른 단계로 나온다
        return J.expected(ws, J.givenMap(ws, st, c.phrase)).map(x => x.ch).join('');
      }, id);
      await p.focus('#ans');
      await p.keyboard.insertText(want);
      const v = await p.$eval('.stamp', e => e.textContent).catch(async () => { const st = await p.evaluate(() => ({ val: document.getElementById('ans').value, chip: document.getElementById('stageChip').textContent, prog: document.getElementById('prog').textContent })); throw new Error(`${id} ${i + 1}장 판정 없음: want=${want} ${JSON.stringify(st)}`); });
      assert.strictEqual(v, '인용', `${id} ${i + 1}장: ${v}`);
      maxW = Math.max(maxW, await p.evaluate(() => document.documentElement.scrollWidth));
      await p.keyboard.press('Enter');
      cards++;
    }
    assert.ok(!(await p.$eval('#result', e => e.hidden)), id + ' 결과 화면');
  }
  assert.ok(maxW <= 390, 'scrollWidth ' + maxW);
  assert.deepStrictEqual(errs, []);
  console.log(`sets ok: 세트 ${ids.length}, 카드 ${cards}, 가로 최대 ${maxW}px`);
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
