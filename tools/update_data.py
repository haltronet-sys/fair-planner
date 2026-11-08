#!/usr/bin/env python3
"""Rebuild data.js (show schedule, roaming acts, shop and food listings) from texrenfest.com.
Standard library only. Exits non-zero, leaving data.js untouched, if anything looks wrong.
Usage: python3 tools/update_data.py [--ent-file ent.html] [--no-shops] [--out data.js]"""
import json, re, html, sys, os, time, argparse, urllib.request, concurrent.futures as cf, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENT_URL = "https://www.texrenfest.com/p/things-to-do/entertainment-schedule"
SVC = "https://www.texrenfest.com/services/businessesservice.asmx/"
UA = {"User-Agent": "Mozilla/5.0 (compatible; FairePlannerUpdater/1.0)"}

def http(url, data=None, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=dict(UA, **({"Content-Type": "application/json; charset=utf-8"} if data else {})))
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf8", "ignore")
        except Exception as e:
            last = e; time.sleep(2 * (i + 1))
    raise RuntimeError("fetch failed: %s (%s)" % (url, last))

def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()

def lines(cell):
    return [x for x in (clean(p) for p in re.split(r"<br\s*/?>", cell)) if x]

def parse_schedule(page, ov):
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S)
    acts, roaming = [], []
    for r in rows:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if len(tds) != 3 or "<h2" in tds[0]: continue
        name = clean(tds[0]).replace("\u2019", "'")
        name = ov["rename"].get(name, name)
        vlines, tlines = lines(tds[1]), lines(tds[2])
        if not vlines or not tlines: continue
        if len(vlines) == 1: vlines = vlines * len(tlines)
        if len(vlines) != len(tlines):
            print("WARNING: could not pair stages and times for %r; using first stage" % name)
            vlines = [vlines[0]] * len(tlines)
        for venue, seg in zip(vlines, tlines):
            if "throughout the day" in seg.lower():
                if venue.lower().startswith("throughout the village"): roaming.append(name)
                else: roaming.append("%s (%s)" % (name, venue))
                continue
            times = re.findall(r"\b\d{1,2}:\d{2}\b", seg)
            if not times: continue
            days = "SU-SA"
            if re.search(r"\(\s*sat", seg, re.I): days = "SA"
            elif re.search(r"\(\s*sun", seg, re.I): days = "SU"
            venue = ov["venue_rename"].get(name, venue)
            acts.append({"name": name, "venue": venue, "times": " ".join(times), "days": days})
    return acts, sorted(set(roaming), key=lambda x: x.lower())

def apply_overrides(acts, ov):
    out = []
    for a in acts:
        o = dict(ov["acts"].get(a["name"], {}))
        d = {"name": a["name"], "venue": a["venue"], "times": a["times"]}
        if a["days"] != "SU-SA": d["days"] = a["days"]
        for k in ("adult", "len", "ticketed", "tag", "note"):
            if k in o: d[k] = o[k]
        out.append(d)
    return out

def post(m, body):
    return json.loads(http(SVC + m, body.encode()))["d"]

def scrape_shops(ov):
    ids = {}
    for c, kind in ((2, "s"), (28, "f")):
        d = post("GetBusinessBusinessListingCategoryIndex",
                 "{'categoryID':%d,'tagID':0,'keywords':'','showCategoryExceptionID':0,'customFieldFilters':[],'searchInDescription':false}" % c)
        for cat in d:
            for i in cat["BusinessIDs"]: ids.setdefault(i, kind)
    L = sorted(ids); biz = {}
    def batch(chunk):
        d = post("GetBusinessListingBusinessesByIDList",
                 "{'IDList':'%s','categoryID':2,'keywords':'','searchInDescription':false}" % ",".join(map(str, chunk)))
        return d["Businesses"] if d else []
    chunks = [L[i:i + 16] for i in range(0, len(L), 16)]
    with cf.ThreadPoolExecutor(4) as ex:
        for res in ex.map(batch, chunks):
            for b in res: biz[b["ID"]] = b
    def desc(b):
        try:
            t = http(b["DetailURL"])
            m = re.search(r'itemprop="description">(.*?)</span>', t, re.S)
            return b["ID"], clean(m.group(1)) if m else ""
        except Exception:
            return b["ID"], None
    descs = {}
    with cf.ThreadPoolExecutor(6) as ex:
        for i, s in ex.map(desc, list(biz.values())): descs[i] = s
    rows = []
    for i, b in biz.items():
        s = descs.get(i) or ""
        if len(s) > 220: s = s[:219].rsplit(" ", 1)[0] + "…"
        rows.append([b["Name"], ids[i], ", ".join(l["DisplayName"] for l in b["Locations"]),
                     ov["categories"].get(str(b["CategoryID"]), ""), s])
    rows.sort(key=lambda r: r[0].lower())
    return rows

def read_old(path):
    try:
        t = open(path, encoding="utf8").read()
        return t
    except OSError:
        return ""

def body_of(acts, roam, shops):
    return ("var SCHEDULE = %s;\nvar ROAMING = %s;\nvar SHOPS = %s;\n" % (
        json.dumps(acts, ensure_ascii=False, separators=(",", ":")).replace("},{", "},\n{"),
        json.dumps(roam, ensure_ascii=False), json.dumps(shops, ensure_ascii=False, separators=(",", ":")).replace("],[", "],\n[")))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ent-file"); ap.add_argument("--no-shops", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "data.js"))
    a = ap.parse_args()
    ov = json.load(open(os.path.join(HERE, "overrides.json"), encoding="utf8"))
    old = read_old(a.out)
    page = open(a.ent_file, encoding="utf8", errors="ignore").read() if a.ent_file else http(ENT_URL)
    acts, roam = parse_schedule(page, ov)
    acts = apply_overrides(acts, ov)
    unknown = sorted({x["name"] for x in acts if x["name"] not in ov["acts"] and x["name"] not in ov.get("known", [])})
    # sanity checks: refuse to publish a broken pull
    if len(acts) < 30 or len(roam) < 5:
        sys.exit("ERROR: schedule looks wrong (%d acts, %d roaming). data.js left unchanged." % (len(acts), len(roam)))
    if any(not re.fullmatch(r"\d{1,2}:\d{2}( \d{1,2}:\d{2})*", x["times"]) for x in acts):
        sys.exit("ERROR: bad time format. data.js left unchanged.")
    if a.no_shops:
        m = re.search(r"var SHOPS = (\[.*\]);", old, re.S)
        if not m: sys.exit("ERROR: --no-shops needs an existing data.js")
        shops = json.loads(m.group(1))
    else:
        shops = scrape_shops(ov)
        m = re.search(r"var SHOPS = (\[.*\]);", old, re.S)
        prev = len(json.loads(m.group(1))) if m else 0
        if len(shops) < 300 or (prev and len(shops) < prev * 0.8):
            sys.exit("ERROR: shop list looks wrong (%d now vs %d before). data.js left unchanged." % (len(shops), prev))
        if sum(1 for r in shops if r[4]) < len(shops) * 0.5:
            # descriptions failed to load: keep the previous descriptions
            pm = {r[0]: r[4] for r in json.loads(m.group(1))} if m else {}
            for r in shops:
                if not r[4]: r[4] = pm.get(r[0], "")
    body = body_of(acts, roam, shops)
    oldbody = re.sub(r'^var DATA_UPDATED = .*\n', "", old, flags=re.M)
    if body == oldbody:
        print("No change in festival data."); changed = False
    else:
        today = datetime.date.today().isoformat()
        open(a.out, "w", encoding="utf8").write('var DATA_UPDATED = "%s";\n' % today + body)
        print("data.js updated: %d acts, %d roaming, %d listings" % (len(acts), len(roam), len(shops))); changed = True
    if unknown: print("NOTE new/unrecognised acts (check adult status): " + "; ".join(unknown))
    # keep the offline cache version in step with the files, so phones notice updates
    import hashlib
    h = hashlib.sha1()
    for f in ("index.html", "data.js", "trf-map.jpg", "manifest.webmanifest"):
        p = os.path.join(ROOT, f)
        if os.path.exists(p): h.update(open(p, "rb").read())
    swp = os.path.join(ROOT, "sw.js")
    if os.path.exists(swp):
        sw = open(swp, encoding="utf8").read()
        sw2 = re.sub(r"const CACHE='[^']*';", "const CACHE='faire-planner-%s';" % h.hexdigest()[:10], sw, count=1)
        if sw2 != sw: open(swp, "w", encoding="utf8").write(sw2); print("sw.js cache version bumped")
if __name__ == "__main__":
    main()
