import os, re, json, uuid, requests
import redis
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from minio import Minio
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

app = FastAPI()
tpl = Jinja2Templates(directory="templates")
r = redis.Redis(host=os.environ["REDIS_HOST"], password=os.environ["REDIS_PASS"],
                decode_responses=True)
mc = Minio(os.environ["MINIO_ENDPOINT"], os.environ["MINIO_USER"],
           os.environ["MINIO_PASS"], secure=False)
pool = ConnectionPool(os.environ["DB_DSN"], kwargs={"row_factory": dict_row},
                      min_size=1, max_size=8, open=True)
NTFY, TOPIC = os.getenv("NTFY_URL"), os.getenv("NTFY_TOPIC")

def notify(msg):
    if NTFY:
        try: requests.post(f"{NTFY}/{TOPIC}", data=msg.encode(),
                           headers={"Title": "Web"}, timeout=3)
        except Exception: pass

def q_all(sql, params=()):
    with pool.connection() as c:
        return c.execute(sql, params).fetchall()

def norm(q):
    q = re.sub(r"[^a-z0-9 ]+", " ", (q or "").lower())
    return " ".join(q.split())[:60]

def latest(n=50):
    return q_all("SELECT id,name,filename FROM images ORDER BY created_at DESC, id DESC LIMIT %s", (n,))

def stats():
    return q_all("SELECT member_id, ai_no, COUNT(*) AS n FROM images GROUP BY 1,2 ORDER BY 1,2")

def find(name):
    pats = [f"%{t}%" for t in name.split()]
    return q_all("""SELECT id,name,filename FROM images WHERE name ILIKE ALL(%s::text[])
                    ORDER BY (name=%s) DESC, similarity(name,%s) DESC, created_at DESC
                    LIMIT 50""", (pats, name, name))

def nearest(name):
    return q_all("""SELECT id,name,filename FROM images
                    ORDER BY similarity(name,%s) DESC, created_at DESC LIMIT 12""", (name,))

def page(request, **kw):
    st = stats()
    ctx = dict(q="", images=[], generating=False, req_id=None,
               stats=st, total=sum(s["n"] for s in st))
    ctx.update(kw)
    return tpl.TemplateResponse(request, "index.html", ctx)

@app.get("/")
def home(request: Request):
    return page(request, images=latest(50))

@app.get("/search")
def search(request: Request, q: str = ""):
    name = norm(q)
    if not name:
        return page(request, images=latest(50))
    found = find(name)
    if found:
        return page(request, q=name, images=found)
    key = f"pending:{name}"
    req_id = uuid.uuid4().hex
    if r.set(key, req_id, nx=True, ex=600):
        r.rpush("q:priority", json.dumps({"name": name, "req_id": req_id}))
        notify(f"MISS '{name}' -> queued for generation")
    else:
        req_id = r.get(key) or req_id
    return page(request, q=name, images=nearest(name) or latest(24),
                generating=True, req_id=req_id)

@app.get("/api/result/{req_id}")
def result(req_id: str):
    return {"status": "done" if r.get(f"res:{req_id}") else "pending"}

@app.get("/img/{img_id}")
def img(img_id: int):
    rows = q_all("SELECT s3_key FROM images WHERE id=%s", (img_id,))
    if not rows: raise HTTPException(404)
    o = mc.get_object("images", rows[0]["s3_key"])
    try: data = o.read()
    finally:
        o.close(); o.release_conn()
    return Response(data, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})

@app.get("/api/health")
def health():
    ks = r.keys("hb:*")
    return {"status": "OK" if ks else "DEGRADED",
            "workers_alive": sorted(k[3:] for k in ks),
            "q_priority": r.llen("q:priority"), "q_bg": r.llen("q:bg")}
