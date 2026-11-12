"""법무사·법원행정고시 2차 문제 PDF의 글자를 점검한다: 과목별 쪽 바닥글과 【문 N】 머리.

usage: python3 -I court_check.py <txt 폴더>
txt는 pdftext.swift 출력(첫 줄 'PAGES\t<n>')이다. 파일마다 다음을 본다.
- 쪽 바닥글 '(과목 N-k)'가 과목마다 1~N쪽 모두 있는지(줄 끝에 붙은 바닥글도 찾는다).
- 【문 N】(【문 1-1】 꼴 포함) 번호가 과목마다 1부터 빠짐없는지. 문항은 다음에 나오는 바닥글의 과목에 붙인다.
- 'N교시 과목' 표지 줄.
26.11.11 법무사 13개·법원행정고시 10개(2017~2026)를 이것으로 점검했다(WORK_LOG).
"""
import os
import re
import sys
import unicodedata
from collections import OrderedDict

FOOT = re.compile(r"\((?P<subj>[가-힣][가-힣\s]*?)\s*(?P<n>\d+)\s*-\s*(?P<k>\d+)\)$")
QHEAD = re.compile(r"【\s*문\s*(\d+)(?:\s*-\s*(\d+))?\s*】")
GYOSI = re.compile(r"^(\d)교시\s*(.+)$")


def norm(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", s))


def check(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    pages = int(lines[0].split("\t")[1])
    body = [unicodedata.normalize("NFC", l).strip() for l in lines[1:]]

    subjects = OrderedDict()  # subj -> {"n": set, "k": set, "q": [nums]}
    gyosi = []
    pending_q = []
    for line in body:
        m = GYOSI.match(line)
        if m:
            gyosi.append(f"{m.group(1)}교시 {norm(m.group(2))}")
        for q, sub in QHEAD.findall(line):
            pending_q.append((int(q), sub))
        m = FOOT.search(line)
        if m:
            subj = norm(m.group("subj"))
            d = subjects.setdefault(subj, {"n": set(), "k": set(), "q": []})
            d["n"].add(int(m.group("n")))
            d["k"].add(int(m.group("k")))
            d["q"].extend(pending_q)
            pending_q = []
    return pages, gyosi, subjects, pending_q


def summarize(subjects):
    out = []
    problems = []
    for subj, d in subjects.items():
        n = max(d["n"])
        missing_pages = sorted(set(range(1, n + 1)) - d["k"])
        if len(d["n"]) > 1:
            problems.append(f"{subj}: footer totals disagree {sorted(d['n'])}")
        if missing_pages:
            problems.append(f"{subj}: missing footer pages {missing_pages}")
        qs = [q for q, _ in d["q"]]
        tokens = ",".join(f"{q}-{sub}" if sub else str(q) for q, sub in d["q"])
        if qs:
            qmax = max(qs)
            missing_q = sorted(set(range(1, qmax + 1)) - set(qs))
            if missing_q:
                problems.append(f"{subj}: missing 【문】 {missing_q}")
            out.append(f"{subj} {len(d['k'])}/{n}쪽 [{tokens}]")
        else:
            out.append(f"{subj} {len(d['k'])}/{n}쪽 (【문】없음)")
    return out, problems


def main():
    d = sys.argv[1]
    for name in sorted(os.listdir(d)):
        if not name.endswith(".txt"):
            continue
        pages, gyosi, subjects, trailing = check(os.path.join(d, name))
        out, problems = summarize(subjects)
        if trailing:
            problems.append(f"【문】 after last footer: {trailing}")
        print(f"## {name[:-4]}")
        print(f"   PDF {pages}쪽 | 표지: {', '.join(gyosi)}")
        print(f"   과목: {' / '.join(out)}")
        print(f"   문제점: {'; '.join(problems) if problems else '없음'}")


if __name__ == "__main__":
    main()
