import os, io, json, time, random, traceback
import torch, redis, psycopg, requests
from PIL import Image
from minio import Minio
from diffusers import AutoPipelineForText2Image

MEMBER_ID = int(os.environ["MEMBER_ID"])
AI_NO     = int(os.environ["AI_NO"])
TAG       = f"{MEMBER_ID}.{AI_NO}"
MODEL     = os.getenv("MODEL", "stabilityai/sd-turbo")
STEPS     = int(os.getenv("STEPS", "2"))
GUIDANCE  = float(os.getenv("GUIDANCE", "0.0"))
SIZE      = int(os.getenv("SIZE", "512"))
OUT       = int(os.getenv("OUT_SIZE", "256"))
STYLE     = os.environ["STYLE"]
BUCKET    = "images"
NTFY      = os.getenv("NTFY_URL")
TOPIC     = os.getenv("NTFY_TOPIC")
DSN       = os.environ["DB_DSN"]

def notify(msg, tags=""):
    if not NTFY: return
    try:
        requests.post(f"{NTFY}/{TOPIC}", data=msg.encode(),
                      headers={"Title": f"AI {TAG}", "Tags": tags}, timeout=3)
    except Exception:
        pass

r  = redis.Redis(host=os.environ["REDIS_HOST"], password=os.environ["REDIS_PASS"],
                 decode_responses=True)
mc = Minio(os.environ["MINIO_ENDPOINT"], os.environ["MINIO_USER"],
           os.environ["MINIO_PASS"], secure=False)
try:
    if not mc.bucket_exists(BUCKET): mc.make_bucket(BUCKET)
except Exception:
    pass

torch.set_num_threads(os.cpu_count() or 4)
print("Loading model", MODEL, flush=True)
pipe = AutoPipelineForText2Image.from_pretrained(
    MODEL, torch_dtype=torch.float32, variant="fp16")
pipe.set_progress_bar_config(disable=True)
notify(f"started, model={MODEL}", "rocket")

def generate(name):
    g = torch.Generator("cpu").manual_seed(random.randrange(2**31))
    img = pipe(f"{name}, {STYLE}", num_inference_steps=STEPS,
               guidance_scale=GUIDANCE, height=SIZE, width=SIZE,
               generator=g).images[0]
    return img.resize((OUT, OUT), Image.LANCZOS)

def handle(job, qname):
    name = " ".join(job["name"].lower().split())[:60]
    req_id = job.get("req_id")
    with psycopg.connect(DSN) as conn:
        row = conn.execute("SELECT id FROM images WHERE name=%s ORDER BY id LIMIT 1",
                           (name,)).fetchone()
    if row:
        if req_id: r.set(f"res:{req_id}", row[0], ex=900)
        return
    t0 = time.time()
    img = generate(name)
    filename = f"{name} {TAG}.jpg"
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=90)
    size = buf.tell(); buf.seek(0)
    mc.put_object(BUCKET, filename, buf, size, content_type="image/jpeg")
    source = "on_demand" if qname == "q:priority" else "auto"
    with psycopg.connect(DSN) as conn:
        iid = conn.execute(
            """INSERT INTO images(name,filename,member_id,ai_no,s3_key,source)
               VALUES(%s,%s,%s,%s,%s,%s)
               ON CONFLICT (filename) DO UPDATE SET filename=EXCLUDED.filename
               RETURNING id""",
            (name, filename, MEMBER_ID, AI_NO, filename, source)).fetchone()[0]
    if req_id: r.set(f"res:{req_id}", iid, ex=900)
    notify(f"{'USER' if source=='on_demand' else 'auto'}: {filename} ({time.time()-t0:.0f}s)",
           "frame_with_picture")

while True:
    r.set(f"hb:{TAG}", int(time.time()), ex=90)
    item = r.blpop(["q:priority", "q:bg"], timeout=10)
    if not item: continue
    qname, raw = item
    job = json.loads(raw)
    try:
        handle(job, qname)
    except Exception as e:
        traceback.print_exc()
        notify(f"ERROR {job.get('name')}: {e}", "x")
        job["tries"] = job.get("tries", 0) + 1
        if job["tries"] < 3: r.rpush(qname, json.dumps(job))
        time.sleep(5)
