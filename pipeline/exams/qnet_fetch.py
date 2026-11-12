"""큐넷 전문자격 > 자료실 > 기출문제 내려받기(게시판 Q004)에서 2차 문제 글의 첨부를 받는다.

usage: python3 -I qnet_fetch.py <검색어> <dest_dir> <from_year> <to_year> [--list-only] [--skip 글자]
검색어: 공인노무사, 변리사, 감정평가사 (글제목 검색)
제목에 '2차'가 있고 제목 속 연도(2026년, 22년도 꼴)가 범위 안인 글만 받는다. --skip 글자가 든 첨부는 받지 않는다(예: 선택). 글마다 게시일·제목·첨부·공공누리 표시를
<dest_dir>/_index-qnet.json에 남긴다. 받은 파일 이름은 '<연도>_<첨부 이름>'.
"""
import http.cookiejar, html as H, json, os, re, sys, time, urllib.parse, urllib.request

SITE = "https://www.q-net.or.kr/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
LIST_PAGE = SITE + "cst003.do?id=cst00309&gSite=L&gId="

kw, dest, y0, y1 = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
list_only = "--list-only" in sys.argv
skip = sys.argv[sys.argv.index("--skip") + 1] if "--skip" in sys.argv else None
os.makedirs(dest, exist_ok=True)

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def get(url, data=None, raw=False):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Referer": LIST_PAGE})
    with op.open(req, timeout=120) as r:
        b = r.read()
        return (b, r.headers) if raw else b.decode("utf-8", "replace")


def text(s):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", "", s))).strip()


get(LIST_PAGE)
posts, page = [], 1
while True:
    q = urllib.parse.urlencode({"id": "cst00301s01", "gSite": "L", "gId": "", "page": page, "schText": kw,
                                "schType": "T", "boardId": "Q004", "code": "1008"})
    t = get(SITE + "cst003.do?" + q)
    rows = re.findall(r"goNext\(\s*'?(\d+)'?\s*,\s*'?\d+'?\s*,\s*'?([^')]*)'?\s*\)[^>]*>(.*?)</a>", t, re.S)
    if not rows:
        break
    for seq, cst, title in rows:
        posts.append({"artlSeq": seq, "cst": cst, "title": text(title)})
    pages = [int(p) for p in re.findall(r"goPage\((\d+)\)", t)]
    if not pages or page >= max(pages):
        break
    page += 1
    time.sleep(0.5)

picked = []
for p in posts:
    m = re.search(r"(?<!\d)(20\d\d|\d\d)\s*년", p["title"])
    if not m or "2차" not in p["title"]:
        continue
    y = int(m.group(1))
    p["year"] = y if y > 1000 else 2000 + y
    if y0 <= p["year"] <= y1:
        picked.append(p)
print(f"글 {len(posts)}개 중 2차·{y0}~{y1}: {len(picked)}개")

for p in picked:
    data = urllib.parse.urlencode({"page": 1, "schType": "T", "schText": "", "artlSeq": p["artlSeq"], "boardId": "Q004",
                                   "code": "1008", "menuType": "cst00309", "cst": p["cst"]}).encode()
    t = get(SITE + "cst003.do?id=cst00302&gSite=L&gId=", data)
    m = re.search(r"등록일\s*(?:</[^>]+>\s*<[^>]+>\s*)*(20\d\d[.-]\d\d[.-]\d\d)", t)
    p["posted"] = m.group(1) if m else ""
    p["kogl"] = "공공누리 1유형" if "공공누리 1유형" in t else ("공공누리" if "공공누리" in t else "")
    p["files"] = []
    for path, name, fseq in re.findall(r"fileDown\('([^']+)'\s*,\s*'([^']+)'\s*,\s*'(\d+)'\)", t):
        f = {"name": name, "path": path, "fileSeq": fseq}
        if skip and skip in name:
            f["skipped"] = True
        elif not list_only:
            q = urllib.parse.urlencode({"id": "cst00302s01", "gSite": "L", "gId": "", "fileCode": "R001", "filePath": path,
                                        "fileName": name, "fileSeq": fseq, "artlSeq": p["artlSeq"], "href": "0"})
            b, hd = get(SITE + "cst003.do?" + q, raw=True)
            out = os.path.join(dest, f"{p['year']}_{name}")
            with open(out, "wb") as fh:
                fh.write(b)
            f["bytes"] = len(b)
            f["content_type"] = hd.get("Content-Type", "")
            time.sleep(0.5)
        p["files"].append(f)
    print(p["year"], p["posted"], p["kogl"] or "-", p["title"], "|", ", ".join(f"{f['name']}({f.get('bytes', '?')})" for f in p["files"]))
    time.sleep(0.5)

with open(os.path.join(dest, "_index-qnet.json"), "w", encoding="utf-8") as fh:
    json.dump({"keyword": kw, "range": [y0, y1], "posts": picked}, fh, ensure_ascii=False, indent=1)
