#!/usr/bin/env python3
"""
daily_tasks.py — 매일 저녁 6:30 (KST) 실행
내일의 할 일을 data.json에 자동 등록합니다.
소스: Jira (open issues) + data.json schedule (evs)
"""
import os, json, base64, urllib.request, datetime, zoneinfo

GH_TOKEN   = os.environ["GH_TOKEN"]
JIRA_TOKEN = os.environ.get("JIRA_TOKEN", "")
JIRA_USER  = "inkwang.song"
OWNER, REPO, PATH = "inkwangsong", "my-plan", "data.json"
API_BASE   = f"https://api.github.com/repos/{OWNER}/{REPO}/contents"
KST        = zoneinfo.ZoneInfo("Asia/Seoul")

# ── 날짜 계산 ─────────────────────────────────────────────────
def next_biz_day(from_date: datetime.date) -> datetime.date:
    """다음 영업일 반환 (토/일 건너뜀)"""
    d = from_date + datetime.timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d += datetime.timedelta(days=1)
    return d

today    = datetime.datetime.now(tz=KST).date()
tomorrow = next_biz_day(today)
TARGET   = tomorrow.strftime("%Y-%m-%d")
print(f"오늘: {today} / 등록 대상: {TARGET}")

# ── data.json 읽기 ────────────────────────────────────────────
def gh_get(path):
    req = urllib.request.Request(f"{API_BASE}/{path}",
        headers={"Authorization": f"Bearer {GH_TOKEN}",
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req) as r:
        d = json.load(r)
    return (base64.b64decode(d["content"].replace("\n","")).decode("utf-8"),
            d["sha"])

raw, sha = gh_get(PATH)
data     = json.loads(raw)
todos    = data.get("todos", [])
evs      = data.get("evs", [])
pm       = data.get("pm", {})
existing = {t["id"] for t in todos}
print(f"현재 todos: {len(todos)}건")

new_tasks = []

def add(task_id, text, project="etc", url="", weight="S"):
    if task_id not in existing:
        new_tasks.append({
            "id": task_id,
            "date": TARGET,
            "text": text,
            "project": project,
            "status": "todo",
            "schedRef": None,
            "url": url,
            "mood": "",
            "weight": weight,
        })

# ── Jira: open/in-progress issues ────────────────────────────
if JIRA_TOKEN:
    jql = (f"(reporter=\"{JIRA_USER}\" OR assignee=\"{JIRA_USER}\")"
           " AND status NOT IN (Closed, Done, Resolved, Cancelled)"
           " AND updatedDate >= -7d"
           " ORDER BY priority ASC, updated DESC")
    import urllib.parse
    url = (f"https://jira.workers-hub.com/rest/api/2/search"
           f"?jql={urllib.parse.quote(jql)}&fields=summary,status,priority&maxResults=10")
    req = urllib.request.Request(url,
        headers={"Authorization": f"Bearer {JIRA_TOKEN}"})
    try:
        with urllib.request.urlopen(req) as r:
            result = json.load(r)
        issues = result.get("issues", [])
        print(f"Jira open issues: {len(issues)}건")
        for i in issues:
            key  = i["key"]
            summ = i["fields"].get("summary","")[:60]
            prio = i["fields"].get("priority",{}).get("name","Medium")
            if prio in ("Highest","High"):
                w = "M"
            else:
                w = "S"
            add(f"ev-jira-{key.lower()}-{TARGET.replace('-','')}",
                f"[Jira/{key}] {summ}",
                url=f"https://jira.workers-hub.com/browse/{key}",
                weight=w)
    except Exception as e:
        print(f"Jira 조회 실패: {e}")

# ── Schedule: 내일 활성 이벤트 체크 ─────────────────────────
active_ev = [e for e in evs
             if e.get("start","") <= TARGET <= e.get("end","")
             and e.get("status") in ("in-progress","upcoming")]
print(f"내일 활성 일정: {len(active_ev)}건")
for ev in active_ev:
    m = pm.get(ev["p"], {})
    short = m.get("short", ev["p"])
    phase = ev.get("phase","")
    add(f"ev-sched-{ev['id']}-{TARGET.replace('-','')}",
        f"[일정 F/up] {short}: {phase} 진행 상황 확인",
        project=ev["p"],
        weight="S")

# ── Push ─────────────────────────────────────────────────────
if not new_tasks:
    print(f"✅ {TARGET} 에 추가할 태스크 없음 (이미 최신)")
    exit(0)

todos.extend(new_tasks)
data["todos"] = todos
payload = json.dumps({
    "message": f"🤖 Auto: add {len(new_tasks)} tasks for {TARGET}",
    "content": base64.b64encode(
        json.dumps(data, ensure_ascii=False, separators=(',',':')).encode()
    ).decode(),
    "sha": sha,
})
req = urllib.request.Request(f"{API_BASE}/{PATH}",
    data=payload.encode(), method="PUT",
    headers={"Authorization": f"Bearer {GH_TOKEN}",
             "Accept": "application/vnd.github+json",
             "Content-Type": "application/json"})
with urllib.request.urlopen(req) as r:
    d = json.load(r)
print(f"✅ {len(new_tasks)}건 등록 완료: {d['commit']['sha'][:8]}")
print("   태스크 목록:")
for t in new_tasks:
    print(f"   - {t['text'][:70]}")

