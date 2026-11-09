"""법원 시험정보(exam.scourt.go.kr) 시험자료실에서 2차 시험 문제 글의 첨부를 받는다.

usage: python3 -I scourt_fetch.py <bbsid> <dest_dir> [--list-only]
bbsid: data_law(법무사), data_hang(법원행정고등고시)
"""
import http.cookiejar, json, os, re, sys, time, urllib.parse, urllib.request

BASE = "https://exam.scourt.go.kr/wex/EXSuperSvl"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

bbsid, dest = sys.argv[1], sys.argv[2]
list_only = "--list-only" in sys.argv
os.makedirs(dest, exist_ok=True)

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def post(data, raw=False):
    body = urllib.parse.urlencode(data, encoding="cp949").encode()
    req = urllib.request.Request(BASE, data=body, headers={"User-Agent": UA, "Referer": BASE})
    with op.open(req, timeout=60) as r:
        b = r.read()
        return (b, r.headers) if raw else b.decode("cp949", "replace")


op.open(urllib.request.Request(BASE + "?cmd=EXHomeCmd", headers={"User-Agent": UA}), timeout=30).read()

ROW = re.compile(
    r'bbsid\[(\d+)\]= "([^"]*)";\s*list\[\1\]= "([^"]*)";\s*root\[\1\]= "([^"]*)";\s*'
    r'par\[\1\]= "([^"]*)";\s*depth\[\1\]= "([^"]*)";\s*title\[\1\]= "([^"]*)";\s*counter\[\1\]= "([^"]*)";'
)

posts, seen = [], set()
first = post({"cmd": "ex100.EX100s01Cmd", "bbsid": bbsid})
allrow = int(re.search(r'name="allRow" value="(\d+)"', first).group(1))
pages = [first]
for target in range(11, allrow + 1, 10):
    time.sleep(0.4)
    pages.append(post({"cmd": "ex100.EX100s01Cmd", "bbsid": bbsid, "choice": "1",
                       "JK_LB_ACTIVATION": "ACT", "targetRow": str(target)}))
for html in pages:
    dates = re.findall(r"(\d{4}-\d{2}-\d{2})", re.sub(r"<script.*?</script>", "", html, flags=re.S))
    for m in ROW.finditer(html):
        key = (m.group(3), m.group(4))
        if key in seen:
            continue
        seen.add(key)
        posts.append(dict(bbsid=m.group(2), list=m.group(3), root=m.group(4), parent=m.group(5),
                          depth=m.group(6), title=m.group(7), counter=m.group(8)))
print(f"{bbsid}: allRow={allrow}, collected={len(posts)}")

wanted = [p for p in posts if re.search(r"2\s*차", p["title"]) and "문제" in p["title"]
          and not re.search(r"정답|합격|접수|이의", p["title"])]
for p in wanted:
    time.sleep(0.4)
    v = post({"cmd": "ex100.EX100s02Cmd", "bbsid": p["bbsid"], "list": p["list"], "root": p["root"],
              "parent": p["parent"], "depth": p["depth"], "choice": "1", "counter": p["counter"],
              "textbox": "", "faqcheck": "", "serchyn": "", "checkhistory": "0", "row": "",
              "maincheck": "", "allRow": str(allrow)})
    p["files"] = [dict(name=n, id=i) for n, i in zip(re.findall(r'filenm\[\d+\] = "([^"]*)";', v),
                                                     re.findall(r'fileid\[\d+\] = "([^"]*)";', v))]
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", v, flags=re.S)))
    d = re.search(r"게시일\s*(\d{4}-\d{2}-\d{2})", txt)
    p["date"] = d.group(1) if d else ""
    b = re.search(r"첨부파일(.*?)다음글", txt)
    p["body"] = b.group(1).strip()[:400] if b else ""
    print(p["date"], p["title"], [f["name"] for f in p["files"]])
    if list_only:
        continue
    for f in p["files"]:
        time.sleep(0.4)
        data, hdr = post({"cmd": "EXDownloadCmd", "next": "/ex200/ex219_2.jsp", "bbsid": p["bbsid"],
                          "fileid": f["id"], "filenm": f["name"]}, raw=True)
        safe = re.sub(r'[/\\:]', "_", f["name"])
        path = os.path.join(dest, safe)
        with open(path, "wb") as fh:
            fh.write(data)
        f["bytes"] = len(data)
        f["content_type"] = hdr.get("Content-Type", "")

with open(os.path.join(dest, f"_index-{bbsid}.json"), "w", encoding="utf-8") as fh:
    json.dump(dict(source=BASE, bbsid=bbsid, fetched=time.strftime("%Y-%m-%d %H:%M %Z"),
                   allRow=allrow, posts=wanted), fh, ensure_ascii=False, indent=1)
print("wanted:", len(wanted))
