import os, json, time, random, redis, psycopg, requests

r = redis.Redis(host=os.environ["REDIS_HOST"], password=os.environ["REDIS_PASS"],
                decode_responses=True)
DSN = os.environ["DB_DSN"]
LOW, BATCH = int(os.getenv("LOW", "10")), int(os.getenv("BATCH", "10"))
NTFY, TOPIC = os.getenv("NTFY_URL"), os.getenv("NTFY_TOPIC")

SUBJECTS = """dog cat horse eagle owl butterfly whale shark oak tree rose mushroom cactus fern
sunflower apple banana pumpkin volcano mountain waterfall compass telescope microscope hat key
clock anchor sailboat locomotive bicycle violin guitar piano trumpet skull heart brain hand eye
tooth crystal diamond meteor planet moon comet lighthouse castle windmill pyramid bridge sword
shield helmet lantern book globe hourglass scissors teapot fox wolf bear deer rabbit turtle
frog snake spider bee beetle dragonfly seahorse octopus""".split()
SUBJECTS += ["quill pen", "hot air balloon", "steam engine", "sea shell"]
MODS = ["red", "blue", "green", "yellow", "black", "white", "golden", "silver",
        "small", "large", "old", "wild", "brown", "purple", "orange", "striped"]

def notify(msg):
    if NTFY:
        try: requests.post(f"{NTFY}/{TOPIC}", data=msg.encode(),
                           headers={"Title": "Planner"}, timeout=3)
        except Exception: pass

def pick():
    s = random.choice(SUBJECTS)
    return f"{random.choice(MODS)} {s}" if random.random() < 0.7 else s

def exists(name):
    with psycopg.connect(DSN) as c:
        return c.execute("SELECT 1 FROM images WHERE name=%s LIMIT 1", (name,)).fetchone()

last = 0
while True:
    if r.llen("q:bg") < LOW:
        added = 0
        for _ in range(BATCH * 20):
            if added >= BATCH: break
            name = pick()
            if r.sadd("planned", name) and not exists(name):
                r.rpush("q:bg", json.dumps({"name": name})); added += 1
        if added: print("queued", added, flush=True)
    if time.time() - last > 600:
        with psycopg.connect(DSN) as c:
            n = c.execute("SELECT COUNT(*) FROM images").fetchone()[0]
        notify(f"images={n} q_bg={r.llen('q:bg')} q_prio={r.llen('q:priority')} "
               f"workers={len(r.keys('hb:*'))}")
        last = time.time()
    time.sleep(5)
