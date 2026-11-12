"""국회채용시스템 자료실(gosi.assembly.go.kr)에서 입법고시 2차 문제 글의 첨부를 받는다.

usage: python3 -I assembly_fetch.py <dest_dir> <from_year> <to_year> [--list-only]
제목에 '입법고시'와 '2차시험 문제'가 있는 글만 고른다(통계자료 글은 뺀다). 첨부 가운데 PDF판 ZIP이 있으면
그것만, 없으면 모든 첨부를 받는다. 글마다 게시일·제목·첨부를 <dest_dir>/_index-assembly.json에 남긴다.
받은 파일 이름은 '<연도>_<첨부 이름>'.
"""
import http.cookiejar, html as H, json, os, re, sys, time, urllib.parse, urllib.request

SITE = "https://gosi.assembly.go.kr/board/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

dest, y0, y1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
list_only = "--list-only" in sys.argv
os.makedirs(dest, exist_ok=True)

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def post(path, data, raw=False):
    req = urllib.request.Request(SITE + path, data=urllib.parse.urlencode(data).encode(),
                                 headers={"User-Agent": UA, "Referer": SITE + "pdsList.do"})
    with op.open(req, timeout=120) as r:
        b = r.read()
        return (b, r.headers) if raw else b.decode("utf-8", "replace")


def text(s):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", "", s))).strip()


op.open(urllib.request.Request(SITE + "pdsList.do", headers={"User-Agent": UA}), timeout=60).read()
posts, seen, page = [], set(), 1
while page < 200:
    t = post("pdsList.do", {"pageIndex": page, "blng_inst_cd": "", "search_gb": "", "search_txt": "", "brd_id": "001003"})
    rows = re.findall(r"fn_detail\('(\d+)'\)[^>]*>(.*?)</a>", t, re.S)
    new = [(n, text(s)) for n, s in rows if n not in seen]
    if not new:
        break
    years = []
    for n, title in new:
        seen.add(n)
        m = re.search(r"(20\d\d)\s*년", title)
        if m:
            years.append(int(m.group(1)))
        if "입법고시" in title and "2차시험 문제" in title.replace(" ", "").replace("2차시험문제", "2차시험 문제"):
            posts.append({"brdi_no": n, "title": title, "year": int(m.group(1)) if m else None})
    if years and max(years) < y0:
        break
    page += 1
    time.sleep(0.3)

picked = [p for p in posts if p["year"] and y0 <= p["year"] <= y1]
print(f"목록 {len(seen)}글, 입법고시 2차 문제 글 {len(posts)}개 중 {y0}~{y1}: {len(picked)}개")

for p in picked:
    t = post("pdsDetail.do", {"brd_id": "001003", "brdi_no": p["brdi_no"]})
    m = re.search(r"(20\d\d-\d\d-\d\d)", t[t.find("postView"):] if "postView" in t else t)
    p["posted"] = m.group(1) if m else ""
    files = re.findall(r"fUsrFileDown\('([^']+)'\s*,\s*'([^']+)'\)", t)
    pdf = [f for f in files if "PDF" in f[1].upper()]
    p["files"] = []
    for sysname, orgname in files:
        f = {"name": orgname, "sys": sysname}
        if pdf and (sysname, orgname) not in pdf:
            f["skipped"] = True
        elif not list_only:
            b, hd = post("fileDown.do", {"sys_file_nm": sysname, "org_file_nm": orgname}, raw=True)
            with open(os.path.join(dest, f"{p['year']}_{orgname}"), "wb") as fh:
                fh.write(b)
            f["bytes"] = len(b)
            f["content_type"] = hd.get("Content-Type", "")
            time.sleep(0.5)
        p["files"].append(f)
    print(p["year"], p["posted"], p["title"], "|", ", ".join(f"{f['name']}({f.get('bytes', '건너뜀' if f.get('skipped') else '?')})" for f in p["files"]))

with open(os.path.join(dest, "_index-assembly.json"), "w", encoding="utf-8") as fh:
    json.dump({"range": [y0, y1], "posts": picked}, fh, ensure_ascii=False, indent=1)
