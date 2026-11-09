"""공무원시험정보 서술형 문제 게시판에서 5급 2차 글과 첨부 목록을 모은다.

usage: python3 -I gosi_list.py <out.json>
"""
import http.cookiejar, json, re, sys, time, urllib.parse, urllib.request, html as H

BASE = "https://gongmuwon.gosi.kr/oprut/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def post(path, data):
    req = urllib.request.Request(BASE + path, data=urllib.parse.urlencode(data).encode(),
                                 headers={"User-Agent": UA, "Referer": BASE + "EvmArDescriptionPrblmLst.do"})
    with op.open(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


op.open(urllib.request.Request(BASE + "EvmArDescriptionPrblmLst.do", headers={"User-Agent": UA}), timeout=30).read()

posts = {}
for kw in ("5급", "행정고등고시", "행정고시"):
    for page in range(1, 15):
        t = post("EvmArDescriptionPrblmLst.do", {"hdn_curr_page": str(page), "sGubun": "T", "sKeyword": kw})
        rows = re.findall(r"fn_detail\('(\d+)'\)\" title=\"([^\"]*)\"", t)
        new = [(i, x) for i, x in rows if i not in posts]
        for i, x in new:
            posts[i] = {"pstId": i, "title": H.unescape(x)}
        print(kw, page, len(rows), len(new), flush=True)
        if not new:
            break
        time.sleep(0.3)
print("posts", len(posts), flush=True)

out = []
for p in posts.values():
    if not re.search(r"5급|행정고등고시|행정고시", p["title"]):
        continue
    if not re.search(r"2\s*차", p["title"]) or re.search(r"과학기술|\(기술\)|외교관", p["title"]):
        continue
    time.sleep(0.3)
    d = post("EvmArDescriptionPrblmDtl.do", {"hdn_curr_page": "1", "pstId": p["pstId"]})
    m = re.search(r'fn_getFile\("([^"]+)"', d)
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", d, flags=re.S)))
    g = re.search(r"게시일\s*(\d{4}-\d{2}-\d{2})", txt)
    p["date"] = g.group(1) if g else ""
    p["atchFileId"] = m.group(1) if m else ""
    p["files"] = []
    if p["atchFileId"]:
        time.sleep(0.3)
        j = json.loads(post("GetAtchFileLst.do", {"atchFileId": p["atchFileId"]}))
        p["files"] = [{"name": f["strgFileNm"], "webPath": f["filePathNm"], "size": f["atchFileSz"]} for f in j]
    out.append(p)
    print(p["date"], p["pstId"], p["title"], [(f["name"], f["size"]) for f in p["files"]])

json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
