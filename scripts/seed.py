"""Generate a realistic, fully synthetic Bricoram dataset with PLANTED TRAPS.

    uv run python scripts/seed.py            # after `scripts/db.py init`

Deterministic (SEED). No real person or pro is represented. Grounded in:
  * public price guide (evidence/2026-11-22/prices.csv) → services & quote prices;
  * founder's monetization notes → points 0–20 by competition, 1 pt = 10 DZD,
    pros pay on response, top-ups mostly via CCP / BaridiMob;
  * 69-wilaya geography (data/ref).

Planted traps (documented in docs/planted-traps.md, verified by tests):
  1. FAN-OUT     every response creates a lead_unlock: joining requests → quotes
                 → point_transactions in one query multiplies revenue.
  2. SIMPSON     Oct-2026 campaign shifts demand to interior wilayas: fill rate
                 rises in BOTH segments yet falls nationally vs Sept.
  3. RANKING     40 pros who joined in Oct-2026 have exactly one 5★ review and
                 top any raw-average leaderboard.
"""
import csv
import math
import random
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db

SEED = 20261122
ROOT = Path(__file__).resolve().parent.parent

# Metro wilayas with deep supply ("core"); everything else is "interior".
CORE_WILAYAS = {16: 30, 31: 14, 25: 9, 9: 8, 35: 7, 19: 7, 6: 6, 15: 5, 42: 5}
MONTHS = [(2026, m) for m in range(5, 11)]            # May → Oct 2026
REQUESTS_PER_MONTH = {5: 2600, 6: 2900, 7: 3000, 8: 3100, 9: 3300, 10: 4600}
# Share of requests coming from interior wilayas (Oct = acquisition campaign).
INTERIOR_SHARE = {5: 0.22, 6: 0.22, 7: 0.23, 8: 0.22, 9: 0.22, 10: 0.52}
# P(first quote within 24h) by segment and month: both segments IMPROVE in Oct.
FILL_PROB = {"core": {9: 0.80, 10: 0.84}, "interior": {9: 0.42, 10: 0.47}}
FILL_DEFAULT = {"core": 0.79, "interior": 0.41}
CATEGORY_WEIGHT = {"plomberie": 0.34, "electricite": 0.30, "peinture": 0.16,
                   "maconnerie": 0.15, "genie-civil": 0.05}
CATEGORY_COMPETITION = {"plomberie": 1.2, "electricite": 1.15, "peinture": 1.0,
                        "maconnerie": 0.85, "genie-civil": 0.5}
N_PROS, N_CLIENTS, N_TRAP_PROS = 2500, 15000, 40
TOPUP_METHODS = (["ccp"] * 45 + ["baridimob"] * 27 + ["cib_edahabia_satim"] * 18
                 + ["bna_transfer"] * 10)


def segment(wilaya: int) -> str:
    return "core" if wilaya in CORE_WILAYAS else "interior"


def load_ref():
    with open(ROOT / "data/ref/communes_1541.csv", encoding="utf-8") as f:
        communes = [(int(r["id"]), int(r["wilaya_code"])) for r in csv.DictReader(f)]
    with open(ROOT / "evidence/2026-11-22/prices.csv", encoding="utf-8") as f:
        services = []
        for i, r in enumerate(csv.DictReader(f), start=1):
            mn, mean, mx = int(r["min_dzd"]), int(r["mean_dzd"]), int(r["max_dzd"])
            if not mn <= mean <= mx:              # the guide's own errors: use geo-mean
                mean = round(math.sqrt(mn * mx))
            slug = f"{r['category']}-{i:02d}"
            services.append({"id": i, "slug": slug, "category": r["category"],
                             "name": r["item"], "unit": r["unit"],
                             "min": mn, "mean": mean, "max": mx})
    return communes, services


class Gen:
    def __init__(self, rnd: random.Random):
        self.r = rnd
        self.communes, self.services = load_ref()
        self.by_wilaya = defaultdict(list)
        for cid, w in self.communes:
            self.by_wilaya[w].append(cid)
        self.svc_by_cat = defaultdict(list)
        for s in self.services:
            self.svc_by_cat[s["category"]].append(s)
        interior = [w for w in self.by_wilaya if w not in CORE_WILAYAS]
        # Interior demand: older wilayas weigh more than the 2026 ones.
        self.interior_w = {w: (0.5 if w >= 59 else 1.0 + self.r.random() * 2) for w in interior}
        self.users, self.pros, self.pro_services = [], [], []
        self.requests, self.quotes, self.reviews, self.txs = [], [], [], []

    # ── helpers ──
    def pick_wilaya(self, seg: str) -> int:
        pool = CORE_WILAYAS if seg == "core" else self.interior_w
        return self.r.choices(list(pool), weights=list(pool.values()))[0]

    def ts(self, year: int, month: int) -> datetime:
        days = (datetime(year + month // 12, month % 12 + 1, 1) - datetime(year, month, 1)).days
        # Local (UTC+1) activity peaks in the evening; 22:00–00:59 local is common,
        # so a share of requests straddles the UTC/Algiers date boundary.
        local_hour = self.r.choices(range(24), weights=[2, 1, 1, 1, 1, 1, 2, 4, 7, 9, 9, 8,
                                                         7, 7, 8, 8, 9, 10, 11, 11, 10, 9, 7, 4])[0]
        local = datetime(year, month, self.r.randint(1, days), local_hour,
                         self.r.randrange(60), self.r.randrange(60))
        return (local - timedelta(hours=1)).replace(tzinfo=UTC)

    def price(self, s) -> float:
        sigma = 0.35
        v = s["mean"] * math.exp(self.r.gauss(0, sigma) - sigma**2 / 2)
        return round(min(max(v, s["min"] * 0.8), s["max"] * 1.2), -1)

    # ── actors ──
    def make_people(self):
        uid = 0
        self.clients_by_seg = defaultdict(list)
        for _ in range(N_CLIENTS):
            uid += 1
            seg = "core" if self.r.random() < 0.55 else "interior"
            w = self.pick_wilaya(seg)
            commune = self.r.choice(self.by_wilaya[w])
            created = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=self.r.randrange(640))
            self.users.append((uid, "client", f"Client {uid}", f"05{self.r.randrange(10**8):08d}",
                               f"client{uid}@example.test", commune, created))
            self.clients_by_seg[(seg, w)].append(uid)

        self.pros_by = defaultdict(list)                 # (wilaya, category) -> pro ids
        self.pros_by_cat = defaultdict(list)
        self.pro_quality, self.balance, self.pro_activity = {}, {}, {}
        self._cum = {}
        for pid in range(1, N_PROS + 1):
            uid += 1
            seg = "core" if self.r.random() < 0.75 else "interior"
            w = self.pick_wilaya(seg)
            created = datetime(2024, 6, 1, tzinfo=UTC) + timedelta(days=self.r.randrange(600))
            self._add_pro(pid, uid, w, created, verified=self.r.random() < 0.6)

    def _add_pro(self, pid, uid, wilaya, created, verified):
        commune = self.r.choice(self.by_wilaya[wilaya])
        self.users.append((uid, "pro", f"Pro {pid}", f"06{self.r.randrange(10**8):08d}",
                           f"pro{pid}@example.test", commune, created))
        cats = self.r.sample(list(CATEGORY_WEIGHT), k=self.r.choice([1, 1, 2, 2, 3]))
        for cat in cats:
            self.pros_by[(wilaya, cat)].append(pid)
            self.pros_by_cat[cat].append(pid)
            for s in self.svc_by_cat[cat]:                 # M:N — one row per service
                self.pro_services.append((pid, s["id"], s["mean"]))
        self.pro_quality[pid] = self.r.uniform(3.9, 4.85)
        # Heavy-tailed activity: a few pros answer (and win) most requests.
        self.pro_activity[pid] = self.r.paretovariate(1.1)
        self.balance[pid] = 0
        self.pros.append([pid, uid, verified, 0, created])

    def pick_responders(self, key, candidates, n) -> list[int]:
        """Weighted sample without replacement, by pro activity (cached cum-weights)."""
        if key not in self._cum:
            acc, cw = 0.0, []
            for pid in candidates:
                acc += self.pro_activity[pid]
                cw.append(acc)
            self._cum[key] = cw
        chosen = []
        while len(chosen) < n:
            for pid in self.r.choices(candidates, cum_weights=self._cum[key], k=n * 3):
                if pid not in chosen:
                    chosen.append(pid)
                    if len(chosen) == n:
                        break
        return chosen

    # ── marketplace flow ──
    def points_price(self, seg, cat) -> int:
        base = 12 if seg == "core" else 3
        return max(0, min(20, round(base * CATEGORY_COMPETITION[cat] + self.r.gauss(0, 3))))

    def respond(self, rid, pid, at, price_pts, status, quoted):
        qid = len(self.quotes) + 1
        self.quotes.append((qid, rid, pid, status, quoted, at))
        if price_pts > 0:
            if self.balance[pid] < price_pts:
                pts = self.r.choice([100, 100, 200, 300, 500])
                self.txs.append((pid, "topup", self.r.choice(TOPUP_METHODS),
                                 None, None, pts, pts * 10,
                                 at - timedelta(minutes=self.r.randint(5, 600))))
                self.balance[pid] += pts
            self.balance[pid] -= price_pts
            self.txs.append((pid, "lead_unlock", None, rid, qid, -price_pts, -price_pts * 10, at))
        return qid

    def make_requests(self):
        rid = 0
        for year, month in MONTHS:
            for _ in range(REQUESTS_PER_MONTH[month]):
                rid += 1
                seg = "interior" if self.r.random() < INTERIOR_SHARE[month] else "core"
                w = self.pick_wilaya(seg)
                pool = self.clients_by_seg.get((seg, w)) or [self.r.randrange(1, N_CLIENTS + 1)]
                client = self.r.choice(pool)
                commune = self.r.choice(self.by_wilaya[w])
                cat = self.r.choices(list(CATEGORY_WEIGHT), weights=list(CATEGORY_WEIGHT.values()))[0]
                svc = self.r.choice(self.svc_by_cat[cat])
                created = self.ts(year, month)
                pts = self.points_price(seg, cat)
                filled = self.r.random() < FILL_PROB[seg].get(month, FILL_DEFAULT[seg])
                self._quotes_for(rid, seg, w, cat, svc, created, pts, filled, client, commune)
        self.n_regular_requests = rid

    def _quotes_for(self, rid, seg, w, cat, svc, created, pts, filled, client, commune):
        r = self.r
        key = (w, cat) if self.pros_by.get((w, cat)) else cat
        candidates = self.pros_by.get((w, cat)) or self.pros_by_cat[cat]
        if filled:
            median_min = 45 if seg == "core" else 240
            while (first := median_min * math.exp(r.gauss(0, 1.0))) > 24 * 60:
                pass
            n = min(len(candidates), max(1, round(r.gammavariate(2.2, 1.6 if seg == "core" else 0.7))))
        elif r.random() < 0.4:                              # late responses only
            first, n = r.uniform(24 * 60 + 1, 96 * 60), min(len(candidates), 1 + (r.random() < 0.3))
        else:
            first, n = None, 0

        if n == 0:
            status = 6 if r.random() < 0.7 else 5
        else:
            status = r.choices([2, 3, 4, 5], weights=[25, 15, 52, 8])[0]
        self.requests.append((rid, client, svc["id"], commune, status, r.random() < 0.12, pts,
                              None, "Synthetic request", created))
        if n == 0:
            return
        winner = r.randrange(n) if status in (3, 4) else None
        at = created + timedelta(minutes=first)
        for i, pid in enumerate(self.pick_responders(key, candidates, n)):
            q_status = 2 if i == winner else (3 if winner is not None else 1)
            quoted = self.price(svc)
            self.respond(rid, pid, at, pts, q_status, quoted)
            if i == winner and status == 4 and r.random() < 0.45:
                rating = max(1, min(5, round(r.gauss(self.pro_quality[pid], 0.7))))
                self.reviews.append((rid, pid, rating, round(quoted * r.uniform(0.9, 1.05), -1),
                                     None, at + timedelta(days=r.uniform(1, 10))))
            at += timedelta(minutes=r.expovariate(1 / 90))

    def plant_ranking_trap(self):
        """40 pros joining Oct-2026, one completed job each, one 5★ review."""
        rid = len(self.requests)
        uid = len(self.users)
        for k in range(N_TRAP_PROS):
            pid, uid, rid = len(self.pros) + 1, uid + 1, rid + 1
            w = self.pick_wilaya("core")
            cat = self.r.choice(list(CATEGORY_WEIGHT))
            self._add_pro(pid, uid, w, datetime(2026, 10, 1, tzinfo=UTC) + timedelta(days=k % 20),
                          verified=False)
            svc = self.r.choice(self.svc_by_cat[cat])
            created = datetime(2026, 10, 21, tzinfo=UTC) + timedelta(hours=k * 3)
            client = self.r.choice(self.clients_by_seg[("core", w)] or [1])
            self.requests.append((rid, client, svc["id"], self.r.choice(self.by_wilaya[w]), 4,
                                  False, 10, None, "Synthetic request", created))
            at = created + timedelta(minutes=30)
            quoted = self.price(svc)
            self.respond(rid, pid, at, 10, 2, quoted)
            self.reviews.append((rid, pid, 5, quoted, None, at + timedelta(days=2)))

    def finalize(self):
        for p in self.pros:
            p[3] = self.balance[p[0]]


def copy(cur, table, cols, rows):
    with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
        for row in rows:
            cp.write_row(row)


def write(url: str, g: Gen):
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        copy(cur, "services", ["id", "slug", "category_slug", "name_fr", "pricing_unit"],
             [(s["id"], s["slug"], s["category"], s["name"], s["unit"]) for s in g.services])
        copy(cur, "users", ["id", "role", "full_name", "phone", "email", "commune_id", "created_at"],
             g.users)
        copy(cur, "pros", ["id", "user_id", "is_id_verified", "points_balance", "created_at"],
             g.pros)
        copy(cur, "pro_services", ["pro_id", "service_id", "base_price_dzd"], g.pro_services)
        copy(cur, "requests", ["id", "client_id", "service_id", "commune_id", "status_code",
                               "is_urgent", "points_price", "budget_dzd", "description",
                               "created_at"], g.requests)
        copy(cur, "quotes", ["id", "request_id", "pro_id", "status_code", "quoted_price_dzd",
                             "created_at"], g.quotes)
        copy(cur, "reviews", ["request_id", "pro_id", "rating", "paid_price_dzd", "comment",
                              "created_at"], g.reviews)
        copy(cur, "point_transactions", ["pro_id", "transaction_type", "payment_method",
                                         "request_id", "quote_id", "points_delta", "amount_dzd",
                                         "created_at"], g.txs)
        for t in ("users", "pros", "requests", "quotes", "reviews", "point_transactions"):
            cur.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                        f"(SELECT COALESCE(MAX(id), 1) FROM {t}))")


def generate(seed: int = SEED) -> Gen:
    g = Gen(random.Random(seed))
    g.make_people()
    g.make_requests()
    g.plant_ranking_trap()
    g.finalize()
    return g


def main():
    db.load_dotenv()
    url = db.with_db(db.admin_url(), db.DB_NAME)
    g = generate()
    write(url, g)
    print(f"users={len(g.users)} pros={len(g.pros)} pro_services={len(g.pro_services)} "
          f"requests={len(g.requests)} quotes={len(g.quotes)} reviews={len(g.reviews)} "
          f"point_transactions={len(g.txs)}")


if __name__ == "__main__":
    main()
