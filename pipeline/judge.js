/* 법학고양 판정 핵심(브라우저·node 둘 다). build.py가 게임 HTML에 그대로 넣는다.
   - 구두점·괄호·가운뎃점·공백은 치지 않는다(영신 26.11.07 "구두점을 제외하고는 그대로").
     띄어쓰기는 칸 배치로 보여 주고 치지 않는다(설계안 D, 영신 "모두 동의해").
   - 판정은 어절 단위다. 친 글자를 정답과 줄 맞춤(편집 거리)해서, 글자 하나를 빼먹거나 더 쳐도
     뒤 어절이 줄줄이 틀리지 않게 한다.
   - 인용(다 맞음)·일부인용(어절 3분의 1 이하 틀림)·기각·각하(아무것도 안 침). 일부인용도 오답이다. */
(function (root) {
  'use strict';
  var FIXED = /[\s.,·ㆍ・'"“”‘’()（）「」『』<>〈〉《》\[\]{}:;!?…~\-–—\/]/;

  function isFixed(ch) { return FIXED.test(ch); }
  function norm(s) { return Array.from(String(s || '')).filter(function (c) { return !isFixed(c); }); }

  /* 원문 한 덩어리 → 어절 목록. 어절마다 글자 칸(slot)과 미리 찍는 기호(fixed). */
  function words(text, extra) {
    return String(text || '').split(/\s+/).filter(Boolean).map(function (w) {
      var o = { chars: Array.from(w).map(function (c) { return { ch: c, slot: !isFixed(c) }; }) };
      if (extra) Object.keys(extra).forEach(function (k) { o[k] = extra[k]; });
      return o;
    }).filter(function (w) { return w.chars.some(function (c) { return c.slot; }); });
  }
  function wordText(w) { return w.chars.filter(function (c) { return c.slot; }).map(function (c) { return c.ch; }).join(''); }

  /* 빈칸 사다리(설계안 C): 어느 칸을 미리 보여 줄지.
     1 핵심어만 · 2 어절 절반 · 3 첫 글자만 · 4 통빈칸. 번호(cite) 어절은 늘 빈칸. */
  function givenMap(ws, stage) {
    var n = ws.length, blank = ws.map(function (w) { return !!(w.cite || stage >= 3 || (stage === 1 && w.key)); });
    if (stage === 2) {
      var need = Math.ceil(n / 2);
      ws.forEach(function (w, i) { if (w.cite || w.key) blank[i] = true; });
      var count = blank.filter(Boolean).length;
      for (var i = 1; i < n && count < need; i += 2) if (!blank[i]) { blank[i] = true; count++; }
      for (var j = 0; j < n && count < need; j++) if (!blank[j]) { blank[j] = true; count++; }
    }
    if (stage === 1 && !ws.some(function (w) { return w.key && !w.cite; })) {
      // 핵심어를 안 정한 조문은 절반 쪽으로
      return givenMap(ws, 2);
    }
    return ws.map(function (w, i) {
      var first = true;
      return w.chars.map(function (c) {
        if (!c.slot) return true;
        var g = !blank[i];
        if (stage === 3 && !w.cite && first) g = true;
        first = false;
        return g;
      });
    });
  }

  /* 정답 칸(미리 보인 칸 빼고) 차례대로: [{ch, w}] */
  function expected(ws, given) {
    var out = [];
    ws.forEach(function (w, i) { w.chars.forEach(function (c, k) { if (c.slot && !given[i][k]) out.push({ ch: c.ch, w: i }); }); });
    return out;
  }

  /* 편집 거리 줄 맞춤. E: 정답 글자 배열, T: 친 글자 배열.
     반환: st[i] = 'ok'|'sub'|'del', got[i] = 그 자리에 친 글자, ins[k] = E[k] 앞에 더 친 글자들(k=0..n) */
  function align(E, T) {
    var n = E.length, m = T.length, d = [], i, j;
    for (i = 0; i <= n; i++) { d.push(new Array(m + 1)); d[i][0] = i; }
    for (j = 0; j <= m; j++) d[0][j] = j;
    for (i = 1; i <= n; i++) for (j = 1; j <= m; j++) {
      var s = d[i - 1][j - 1] + (E[i - 1] === T[j - 1] ? 0 : 1);
      d[i][j] = Math.min(s, d[i - 1][j] + 1, d[i][j - 1] + 1);
    }
    var st = new Array(n), got = new Array(n), ins = [];
    for (i = 0; i <= n; i++) ins.push([]);
    i = n; j = m;
    while (i > 0 || j > 0) {
      if (i > 0 && j > 0 && d[i][j] === d[i - 1][j - 1] + (E[i - 1] === T[j - 1] ? 0 : 1)) {
        st[i - 1] = E[i - 1] === T[j - 1] ? 'ok' : 'sub'; got[i - 1] = T[j - 1]; i--; j--;
      } else if (i > 0 && d[i][j] === d[i - 1][j] + 1) {
        st[i - 1] = 'del'; got[i - 1] = ''; i--;
      } else {
        ins[i].unshift(T[j - 1]); j--;
      }
    }
    return { st: st, got: got, ins: ins };
  }

  /* 판정. near: {정답 어절: [뜻은 같은 다른 말…]}(사람이 확인한 것만), others: [{label, text}] 헷갈림 알림용 */
  function judge(ws, given, typed, near, others) {
    var exp = expected(ws, given), E = exp.map(function (x) { return x.ch; }), T = norm(typed);
    var res = { verdict: '', wrong: [], near: [], confuse: null, blankWords: 0 };
    var blankIdx = [];
    ws.forEach(function (w, i) { if (exp.some(function (x) { return x.w === i; })) blankIdx.push(i); });
    res.blankWords = blankIdx.length;
    if (!T.length) { res.verdict = '각하'; res.wrong = blankIdx.slice(); return res; }
    var a = align(E, T), span = {};
    exp.forEach(function (x, k) { (span[x.w] = span[x.w] || []).push(k); });
    blankIdx.forEach(function (wi) {
      var ks = span[wi], bad = false, typedW = '';
      ks.forEach(function (k, t) {
        if (a.st[k] !== 'ok') bad = true;
        if (t > 0 && a.ins[k].length) bad = true;   // 어절 안에 더 친 글자
        if (t > 0) typedW += a.ins[k].join('');
        typedW += a.got[k] || '';
      });
      var last = ks[ks.length - 1] + 1;              // 어절 끝 뒤에 더 친 글자는 이 어절 몫
      if (last === E.length && a.ins[last].length) { bad = true; typedW += a.ins[last].join(''); }
      else if (last < E.length && exp[last].w !== wi && a.ins[last].length) { bad = true; typedW += a.ins[last].join(''); }
      if (ks[0] === 0 && a.ins[0].length) { bad = true; typedW = a.ins[0].join('') + typedW; }
      if (bad) {
        res.wrong.push(wi);
        var want = wordText(ws[wi]), alts = (near && near[want]) || [];
        if (alts.indexOf(typedW) >= 0) res.near.push({ w: wi, typed: typedW, want: want });
      }
    });
    if (!res.wrong.length) res.verdict = '인용';
    else if (res.wrong.length <= Math.max(1, Math.floor(res.blankWords / 3))) res.verdict = '일부인용';
    else res.verdict = '기각';
    if (res.wrong.length && others && others.length) res.confuse = confusion(T, E, others);
    return res;
  }

  /* 친 글 가운데 정답에 없는 5글자 이상 덩어리가 다른 조문에 있으면 그 조문을 알린다(아이디어 3). */
  function confusion(T, E, others) {
    var want = E.join(''), L = 5;
    for (var s = 0; s + L <= T.length; s++) {
      var piece = T.slice(s, s + L).join('');
      if (want.indexOf(piece) >= 0) continue;
      for (var o = 0; o < others.length; o++) if (norm(others[o].text).join('').indexOf(piece) >= 0) return others[o].label;
    }
    return null;
  }

  var api = { norm: norm, words: words, wordText: wordText, givenMap: givenMap, expected: expected, align: align, judge: judge, confusion: confusion, isFixed: isFixed };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.LawJudge = api;
})(this);
