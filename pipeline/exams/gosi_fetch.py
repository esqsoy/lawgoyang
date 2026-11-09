"""gosi_list.py가 만든 목록에서 5급(행정) 2차 첨부를 받는다.

usage: python3 -I gosi_fetch.py <list.json> <dest_dir> <from_year> <to_year> [--only-first]
첨부 위젯(RAON K Upload)이 브라우저에서 보내는 다운로드 요청과 같은 꼴로 보낸다.
"""
import base64, http.cookiejar, json, os, re, sys, time, urllib.parse, urllib.request, uuid

SITE = "https://gongmuwon.gosi.kr"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
lst, dest, y0, y1 = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
only_first = "--only-first" in sys.argv
os.makedirs(dest, exist_ok=True)

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open(urllib.request.Request(SITE + "/oprut/EvmArDescriptionPrblmLst.do", headers={"User-Agent": UA}), timeout=30).read()


def k00(plain):
    c = base64.b64encode(plain.encode("utf-8")).decode()
    for pos, ch in [(8, "r"), (6, "a"), (9, "o"), (7, "n"), (8, "w"), (6, "i"), (9, "z")]:
        c = c[:pos] + ch + c[pos:]
    return c.replace("+", "%2B")


posts = json.load(open(lst, encoding="utf-8"))
done = []
for p in posts:
    yr = int(p["date"][:4]) if p.get("date") else 0
    if not (y0 <= yr <= y1) or "행정" not in p["title"] or "기술" in p["title"]:
        continue
    for f in p["files"]:
        FF, VT = "\x0c", "\x0b"
        plain = (f"kc{FF}c11{VT}k01{FF}1{VT}k12{FF}{uuid.uuid4().hex}{VT}k05{FF}0{VT}"
                 f"k26{FF}/NAS/raonk/file/upload{f['webPath']}{VT}k31{FF}{f['name']}{VT}k21{FF}")
        body = urllib.parse.urlencode({"k00": k00(plain)}).encode()
        req = urllib.request.Request(SITE + "/rccom/raonkproxyhandler.do", data=body, headers={
            "User-Agent": UA, "Referer": SITE + "/oprut/EvmArDescriptionPrblmDtl.do"})
        with op.open(req, timeout=300) as r:
            data = r.read()
            ctype = r.headers.get("Content-Type", "")
        ok = len(data) == int(f["size"])
        name = f"{yr}_" + re.sub(r'[/\\:]', "_", f["name"])
        if ok:
            with open(os.path.join(dest, name), "wb") as fh:
                fh.write(data)
        f.update(saved=name if ok else "", bytes=len(data), content_type=ctype, ok=ok)
        print(("OK  " if ok else "BAD ") + f"{yr} {len(data):>9}/{f['size']:>9} {f['name']}", flush=True)
        if not ok:
            print("   head:", data[:200])
        time.sleep(0.5)
        if only_first:
            sys.exit(0)
    done.append(p)

json.dump(dict(source=SITE + "/oprut/EvmArDescriptionPrblmLst.do", fetched=time.strftime("%Y-%m-%d %H:%M %Z"),
               posts=done), open(os.path.join(dest, "_index-5급행정.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
