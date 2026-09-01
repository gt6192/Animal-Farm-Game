from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
import base64
import binascii
import hashlib
import hmac
import os
import secrets
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

ROOT = Path(__file__).resolve().parent.parent
DATABASE = ROOT / "animal-farm.db"
UTC = timezone.utc
TRACKER_ROOT = Path("/Users/gt/Developer/daily-target-tracker")
TRACKER_DATABASE = TRACKER_ROOT / "targets.db"
TRACKER_SECRET = TRACKER_ROOT / ".session-secret"
FARM_SECRET = ROOT / ".session-secret"
PUBLIC_PATHS = {"/login"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("animal_farm")
app = FastAPI(title="Animal Farm")
app.mount("/static", StaticFiles(directory=ROOT / "app/static"), name="static")
templates = Jinja2Templates(directory=ROOT / "app/templates")


def load_secret(path: Path) -> str:
    if path.exists(): return path.read_text().strip()
    secret = secrets.token_urlsafe(48)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output: output.write(secret)
    return secret


def decode_session(cookie: str, secret: str) -> int | None:
    try:
        payload_text, signature_text = cookie.split(".", 1)
        signature = base64.urlsafe_b64decode(signature_text + "===")
        expected = hmac.new(secret.encode(), payload_text.encode("ascii"), hashlib.sha256).digest()
        payload = json.loads(base64.urlsafe_b64decode(payload_text + "==="))
        if hmac.compare_digest(signature, expected) and int(payload.get("expires", 0)) >= int(time.time()):
            return int(payload["user_id"])
    except (ValueError, TypeError, KeyError, binascii.Error, json.JSONDecodeError):
        return None
    return None


def encode_session(user_id: int, secret: str) -> str:
    payload = json.dumps({"user_id": user_id, "expires": int(time.time()) + 3600}, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{encoded}.{signature}"


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16); digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240000)
    return f"pbkdf2_sha256$240000${salt.hex()}${digest.hex()}"


def password_ok(password: str, encoded: str) -> bool:
    try:
        _, iterations, salt, digest = encoded.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(actual, digest)
    except ValueError: return False


class HybridAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        identity = None
        daily_id = decode_session(request.cookies.get("daily_tracker_session", ""), load_secret(TRACKER_SECRET)) if TRACKER_SECRET.exists() else None
        if daily_id and TRACKER_DATABASE.exists():
            with sqlite3.connect(TRACKER_DATABASE) as tracker:
                tracker.row_factory = sqlite3.Row
                user = tracker.execute("SELECT id,email,name,role FROM users WHERE id=?", (daily_id,)).fetchone()
            if user:
                with connection() as db:
                    db.execute("""INSERT INTO users(id,email,name,role,auth_source,farmies) VALUES (?,?,?,?,?,COALESCE((SELECT CAST(value AS INTEGER) FROM settings WHERE key='starting_farmies'),2000))
                        ON CONFLICT(id) DO UPDATE SET email=excluded.email,name=excluded.name,role=excluded.role""", (user["id"], user["email"], user["name"] or user["email"], user["role"], "daily_tracker"))
                    ensure_farm(db, user["id"])
                identity = {"id": user["id"], "name": user["name"] or user["email"], "role": user["role"], "source": "daily_tracker"}
        if not identity:
            farm_id = decode_session(request.cookies.get("animal_farm_session", ""), load_secret(FARM_SECRET))
            if farm_id:
                with connection() as db: user = db.execute("SELECT id,name,role FROM users WHERE id=?", (farm_id,)).fetchone()
                if user: identity = {"id": user["id"], "name": user["name"], "role": user["role"], "source": "animal_farm"}
        request.state.identity = identity
        if request.url.path not in PUBLIC_PATHS and not request.url.path.startswith("/static/") and not identity:
            return RedirectResponse("/login", 303)
        return await call_next(request)


app.add_middleware(HybridAuthMiddleware)


@app.exception_handler(HTTPException)
async def friendly_form_error(request: Request, exc: HTTPException):
    """Keep HTML form failures inside the game instead of showing raw JSON."""
    content_type = request.headers.get("content-type", "")
    is_form = request.method == "POST" and (
        content_type.startswith("application/x-www-form-urlencoded")
        or content_type.startswith("multipart/form-data")
    )
    if is_form:
        destination = "/admin" if request.url.path.startswith("/admin/") else "/"
        if request.url.path.startswith("/market/fish-seed"):
            open_dialog = "&open=market-dialog&market=fishery"
        elif request.url.path.startswith("/ponds/"):
            open_dialog = "&open=fishery-screen"
        elif request.url.path.startswith("/animals/sell"):
            open_dialog = "&open=my-animals-screen"
        elif request.url.path.startswith("/inventory/"):
            open_dialog = "&open=inventory-screen"
        elif request.url.path.startswith(("/market/", "/upgrades/", "/animals/buy")):
            open_dialog = "&open=market-dialog"
        else:
            open_dialog = ""
        return RedirectResponse(f"{destination}?error={quote_plus(str(exc.detail))}{open_dialog}", status_code=303)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


@contextmanager
def connection():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def now() -> datetime:
    return datetime.now(UTC)


def dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def initialize_database() -> None:
    with connection() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT UNIQUE,name TEXT NOT NULL,
            password_hash TEXT NOT NULL DEFAULT '',role TEXT NOT NULL DEFAULT 'user',auth_source TEXT NOT NULL DEFAULT 'animal_farm',
            farmies INTEGER NOT NULL DEFAULT 2000,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        settings = {'starting_farmies':'2000','farm_price':'1000','initial_land_blocks':'150','fixed_land_blocks':'30','inventory_blocks':'20','inventory_capacity':'100','bicycle_capacity':'50','bicycle_seconds':'3600','xp_sales_rate':'10','xp_development_rate':'20','fishery_sales_xp_enabled':'1','fishery_development_xp_enabled':'1','capacity_per_land':'5','land_50_price':'1200','land_100_price':'2600','land_250_price':'7500'}
        db.executemany("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", settings.items())
        db.execute("""CREATE TABLE IF NOT EXISTS farms(
            user_id INTEGER PRIMARY KEY,name TEXT NOT NULL DEFAULT '',owned INTEGER NOT NULL DEFAULT 0,total_blocks INTEGER NOT NULL DEFAULT 150,
            fixed_blocks INTEGER NOT NULL DEFAULT 30,inventory_blocks INTEGER NOT NULL DEFAULT 20,
            inventory_capacity REAL NOT NULL DEFAULT 100,transport_key TEXT NOT NULL DEFAULT 'bicycle',updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        farm_columns = {row["name"] for row in db.execute("PRAGMA table_info(farms)")}
        if "name" not in farm_columns:
            db.execute("ALTER TABLE farms ADD COLUMN name TEXT NOT NULL DEFAULT ''")
        for column, definition in (("inventory_level", "INTEGER NOT NULL DEFAULT 1"), ("transport_level", "INTEGER NOT NULL DEFAULT 1"),
                                   ("transport_capacity", "REAL NOT NULL DEFAULT 50"), ("transport_seconds", "INTEGER NOT NULL DEFAULT 3600")):
            if column not in farm_columns: db.execute(f"ALTER TABLE farms ADD COLUMN {column} {definition}")
        db.execute("""CREATE TABLE IF NOT EXISTS species(
            species_key TEXT PRIMARY KEY,name TEXT NOT NULL,icon TEXT NOT NULL,land_blocks INTEGER NOT NULL,buy_price INTEGER NOT NULL,
            sell_price INTEGER NOT NULL DEFAULT 0,
            product_key TEXT NOT NULL,product_name TEXT NOT NULL,product_icon TEXT NOT NULL,product_size REAL NOT NULL,
            product_price INTEGER NOT NULL,production_seconds INTEGER NOT NULL,feed_price INTEGER NOT NULL,feed_hours INTEGER NOT NULL)""")
        species_columns = {row["name"] for row in db.execute("PRAGMA table_info(species)")}
        if "feed_key" not in species_columns:
            db.execute("ALTER TABLE species ADD COLUMN feed_key TEXT")
        if "required_level" not in species_columns:
            db.execute("ALTER TABLE species ADD COLUMN required_level INTEGER")
        if "sell_price" not in species_columns:
            db.execute("ALTER TABLE species ADD COLUMN sell_price INTEGER NOT NULL DEFAULT 0")
            db.execute("UPDATE species SET sell_price=MAX(1,CAST(buy_price * 0.5 AS INTEGER))")
        seeds = [
            ('hen','Hen','🐔',1,20,10,'egg','Egg','🥚',.5,4,7200,2,6),
            ('goat','Goat','🐐',2,120,60,'goat_milk','Goat milk','🥛',2,22,21600,10,8),
            ('sheep','Sheep','🐑',3,220,110,'wool','Wool','🧶',3,45,43200,16,12),
            ('cow','Cow','🐄',5,500,250,'cow_milk','Cow milk','🥛',4,70,36000,28,12),
        ]
        db.executemany("""INSERT OR IGNORE INTO species
            (species_key,name,icon,land_blocks,buy_price,sell_price,product_key,product_name,product_icon,product_size,product_price,production_seconds,feed_price,feed_hours)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", seeds)
        db.execute("""CREATE TABLE IF NOT EXISTS feeds(
            feed_key TEXT PRIMARY KEY,species_key TEXT NOT NULL UNIQUE,name TEXT NOT NULL,icon TEXT NOT NULL,
            pack_size REAL NOT NULL DEFAULT 0.1,pack_price INTEGER NOT NULL,description TEXT NOT NULL DEFAULT '')""")
        feed_seeds = [
            ('hen_feed','hen','Hen grain','🌾',0.1,1,'One pack feeds one hen for a full cycle.'),
            ('goat_feed','goat','Goat fodder','🥬',0.1,4,'One pack feeds one goat for a full cycle.'),
            ('sheep_feed','sheep','Sheep hay','🌿',0.1,6,'One pack feeds one sheep for a full cycle.'),
            ('cow_feed','cow','Cattle feed','🫘',0.1,9,'One pack feeds one cow for a full cycle.'),
        ]
        db.executemany("INSERT OR IGNORE INTO feeds VALUES (?,?,?,?,?,?,?)", feed_seeds)
        db.execute("""UPDATE species SET feed_key=(SELECT f.feed_key FROM feeds f WHERE f.species_key=species.species_key)
            WHERE feed_key IS NULL OR feed_key=''""")
        db.execute("""CREATE TABLE IF NOT EXISTS animal_groups(
            user_id INTEGER NOT NULL,species_key TEXT NOT NULL,quantity INTEGER NOT NULL DEFAULT 0,
            fed_until TEXT,last_production_at TEXT NOT NULL,pending_units INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,species_key))""")
        db.execute("""CREATE TABLE IF NOT EXISTS animal_batches(
            id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,species_key TEXT NOT NULL,quantity INTEGER NOT NULL,
            fed_until TEXT,last_production_at TEXT NOT NULL,pending_units INTEGER NOT NULL DEFAULT 0,
            purchased_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("CREATE INDEX IF NOT EXISTS animal_batches_user_species ON animal_batches(user_id,species_key,id)")
        db.execute("""INSERT INTO animal_batches(user_id,species_key,quantity,fed_until,last_production_at,pending_units,purchased_at)
            SELECT g.user_id,g.species_key,g.quantity,g.fed_until,g.last_production_at,g.pending_units,CURRENT_TIMESTAMP
            FROM animal_groups g WHERE g.quantity>0 AND NOT EXISTS(
                SELECT 1 FROM animal_batches b WHERE b.user_id=g.user_id AND b.species_key=g.species_key)""")
        db.execute("""CREATE TABLE IF NOT EXISTS inventory(
            user_id INTEGER NOT NULL,product_key TEXT NOT NULL,quantity INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,product_key))""")
        db.execute("""CREATE TABLE IF NOT EXISTS deliveries(
            id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,product_key TEXT NOT NULL,quantity INTEGER NOT NULL,
            capacity_used REAL NOT NULL,revenue INTEGER NOT NULL,started_at TEXT NOT NULL,arrives_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'travelling',settled_at TEXT)""")
        db.execute("CREATE INDEX IF NOT EXISTS deliveries_user_status ON deliveries(user_id,status,arrives_at)")
        db.execute("""CREATE TABLE IF NOT EXISTS transport_cargo(
            user_id INTEGER NOT NULL,product_key TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>0),
            loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,product_key))""")
        db.execute("""CREATE TABLE IF NOT EXISTS farmies_ledger(
            id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,amount INTEGER NOT NULL,event_key TEXT NOT NULL,
            reason TEXT NOT NULL,metadata TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id,event_key))""")
        db.execute("CREATE INDEX IF NOT EXISTS ledger_user_id ON farmies_ledger(user_id,id DESC)")
        db.execute("CREATE TABLE IF NOT EXISTS expansion_prices(blocks INTEGER PRIMARY KEY,price INTEGER NOT NULL)")
        db.executemany("INSERT OR IGNORE INTO expansion_prices(blocks,price) VALUES (?,?)", [(50,1200),(100,2600),(250,7500)])
        expansion_columns={row['name'] for row in db.execute('PRAGMA table_info(expansion_prices)')}
        if 'required_level' not in expansion_columns: db.execute('ALTER TABLE expansion_prices ADD COLUMN required_level INTEGER')
        db.execute('UPDATE expansion_prices SET required_level=2 WHERE blocks=50 AND required_level IS NULL')
        db.execute("CREATE TABLE IF NOT EXISTS levels(level INTEGER PRIMARY KEY,name TEXT NOT NULL,xp_required INTEGER NOT NULL UNIQUE,enabled INTEGER NOT NULL DEFAULT 1)")
        db.executemany("INSERT OR IGNORE INTO levels VALUES (?,?,?,1)", [(1,'Farm Starter',0),(2,'Growing Farmer',100)])
        db.execute("UPDATE species SET required_level=1 WHERE species_key IN ('hen','goat') AND required_level IS NULL")
        db.execute("UPDATE species SET required_level=2 WHERE species_key IN ('duck','goose') AND required_level IS NULL")
        db.execute("""CREATE TABLE IF NOT EXISTS xp_wallets(user_id INTEGER PRIMARY KEY,total_xp INTEGER NOT NULL DEFAULT 0,
            highest_level INTEGER NOT NULL DEFAULT 1,sales_remainder INTEGER NOT NULL DEFAULT 0,development_remainder INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE IF NOT EXISTS xp_ledger(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,amount INTEGER NOT NULL,
            event_key TEXT NOT NULL,category TEXT NOT NULL,reason TEXT NOT NULL,metadata TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id,event_key))""")
        db.execute("CREATE INDEX IF NOT EXISTS xp_ledger_user_id ON xp_ledger(user_id,id DESC)")
        db.execute("""CREATE TABLE IF NOT EXISTS xp_sources(user_id INTEGER NOT NULL,source_key TEXT NOT NULL,category TEXT NOT NULL,
            farmies INTEGER NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,source_key))""")
        db.execute("UPDATE OR IGNORE xp_sources SET source_key=substr(source_key,10) WHERE source_key LIKE 'backfill:%'")
        db.execute("""CREATE TABLE IF NOT EXISTS upgrade_catalog(upgrade_key TEXT PRIMARY KEY,upgrade_type TEXT NOT NULL,upgrade_level INTEGER NOT NULL,
            name TEXT NOT NULL,required_player_level INTEGER NOT NULL,cost INTEGER NOT NULL,capacity REAL NOT NULL,seconds INTEGER,enabled INTEGER NOT NULL DEFAULT 1)""")
        db.executemany("INSERT OR IGNORE INTO upgrade_catalog VALUES (?,?,?,?,?,?,?,?,1)", [
            ('inventory_2','inventory',2,'Inventory Level 2',2,1000,110,None),
            ('transport_2','transport',2,'Bike',2,1500,75,2700)])
        db.execute("UPDATE upgrade_catalog SET name='Bike' WHERE upgrade_key='transport_2' AND name='Bicycle Level 2'")
        db.execute("""CREATE TABLE IF NOT EXISTS user_upgrades(user_id INTEGER NOT NULL,upgrade_key TEXT NOT NULL,purchased_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id,upgrade_key))""")
        db.execute("""CREATE TABLE IF NOT EXISTS fish_species(
            fish_key TEXT PRIMARY KEY,name TEXT NOT NULL,icon TEXT NOT NULL,product_key TEXT NOT NULL UNIQUE,
            product_name TEXT NOT NULL,product_icon TEXT NOT NULL,product_size REAL NOT NULL,sale_price INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1)""")
        db.execute("""CREATE TABLE IF NOT EXISTS fish_seeds(
            seed_key TEXT PRIMARY KEY,fish_key TEXT NOT NULL,name TEXT NOT NULL,icon TEXT NOT NULL,
            pack_size REAL NOT NULL,pack_price INTEGER NOT NULL,seeds_per_sack INTEGER NOT NULL,enabled INTEGER NOT NULL DEFAULT 1)""")
        db.execute("""CREATE TABLE IF NOT EXISTS pond_catalog(
            pond_level INTEGER PRIMARY KEY,name TEXT NOT NULL,icon TEXT NOT NULL,required_player_level INTEGER NOT NULL,
            cost INTEGER NOT NULL,land_blocks INTEGER NOT NULL,sack_capacity INTEGER NOT NULL,fish_per_sack INTEGER NOT NULL,
            growth_seconds INTEGER NOT NULL,fish_key TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1)""")
        db.execute("""CREATE TABLE IF NOT EXISTS user_ponds(
            id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,name TEXT NOT NULL,pond_level INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'idle',stocked_sacks INTEGER NOT NULL DEFAULT 0,cycle_started_at TEXT,ready_at TEXT,
            ready_fish INTEGER NOT NULL DEFAULT 0,lifetime_harvest INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("CREATE INDEX IF NOT EXISTS user_ponds_user ON user_ponds(user_id,id)")
        db.execute("""CREATE TABLE IF NOT EXISTS pond_cycles(
            id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,pond_id INTEGER NOT NULL,pond_level INTEGER NOT NULL,
            sacks INTEGER NOT NULL,fish_count INTEGER NOT NULL,fish_key TEXT NOT NULL,started_at TEXT NOT NULL,
            ready_at TEXT NOT NULL,harvested_at TEXT,status TEXT NOT NULL DEFAULT 'growing')""")
        db.execute("CREATE INDEX IF NOT EXISTS pond_cycles_user_pond ON pond_cycles(user_id,pond_id,started_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS pond_cycles_status_ready ON pond_cycles(status,ready_at)")
        db.execute("""CREATE TABLE IF NOT EXISTS pond_upgrade_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,pond_id INTEGER NOT NULL,from_level INTEGER,
            to_level INTEGER NOT NULL,cost INTEGER NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE IF NOT EXISTS pond_limits(
            player_level INTEGER PRIMARY KEY,max_ponds INTEGER NOT NULL CHECK(max_ponds>=0),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.executemany("INSERT OR IGNORE INTO pond_limits(player_level,max_ponds) VALUES (?,?)",[(1,0),(2,1),(3,2)])
        db.execute("""INSERT OR IGNORE INTO fish_species VALUES
            ('carp','Carp','🐟','carp_fish','Carp fish','🐟',1,10,1)""")
        db.execute("""INSERT OR IGNORE INTO fish_seeds VALUES
            ('carp_seed','carp','Carp seed sack','🫘',0.5,100,100,1)""")
        db.executemany("INSERT OR IGNORE INTO pond_catalog VALUES (?,?,?,?,?,?,?,?,?,?,1)", [
            (1,'Starter Pond','💧',2,2000,20,1,100,86400,'carp'),
            (2,'Growing Pond','🌊',3,5000,40,2,100,86400,'carp')])
        for user in db.execute("SELECT id FROM users").fetchall():
            db.execute("INSERT OR IGNORE INTO xp_wallets(user_id) VALUES (?)", (user['id'],))
        backfill_xp(db)


def setting(db: sqlite3.Connection, key: str, cast=int):
    return cast(db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()["value"])


def ensure_farm(db: sqlite3.Connection, user_id: int) -> None:
    db.execute("""INSERT OR IGNORE INTO farms(user_id,total_blocks,fixed_blocks,inventory_blocks,inventory_capacity)
        VALUES (?,?,?,?,?)""", (user_id, setting(db,'initial_land_blocks'), setting(db,'fixed_land_blocks'), setting(db,'inventory_blocks'), setting(db,'inventory_capacity',float)))
    starting = setting(db, 'starting_farmies')
    db.execute("INSERT OR IGNORE INTO farmies_ledger(user_id,amount,event_key,reason) VALUES (?,?, 'opening','Starting Farmies')", (user_id, starting))


def transact(db: sqlite3.Connection, user_id: int, amount: int, event_key: str, reason: str, metadata: dict | None = None) -> None:
    balance = db.execute("SELECT farmies FROM users WHERE id=?", (user_id,)).fetchone()["farmies"]
    if amount < 0 and balance + amount < 0:
        raise HTTPException(400, "Not enough Farmies.")
    inserted = db.execute("INSERT OR IGNORE INTO farmies_ledger(user_id,amount,event_key,reason,metadata) VALUES (?,?,?,?,?)", (user_id, amount, event_key, reason, json.dumps(metadata or {})))
    if inserted.rowcount:
        db.execute("UPDATE users SET farmies=farmies+? WHERE id=?", (amount, user_id))


def ensure_xp_wallet(db: sqlite3.Connection, user_id: int) -> None:
    db.execute("INSERT OR IGNORE INTO xp_wallets(user_id) VALUES (?)", (user_id,))


def refresh_level(db: sqlite3.Connection, user_id: int) -> None:
    ensure_xp_wallet(db, user_id)
    wallet = db.execute("SELECT total_xp,highest_level FROM xp_wallets WHERE user_id=?", (user_id,)).fetchone()
    reached = db.execute("SELECT COALESCE(MAX(level),1) FROM levels WHERE enabled=1 AND xp_required<=?", (wallet['total_xp'],)).fetchone()[0]
    if reached > wallet['highest_level']:
        db.execute("UPDATE xp_wallets SET highest_level=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (reached,user_id))


def grant_xp_for_farmies(db: sqlite3.Connection, user_id: int, source_key: str, category: str, farmies: int, reason: str) -> int:
    if category not in ('sales','development') or farmies <= 0: return 0
    ensure_xp_wallet(db, user_id)
    inserted = db.execute("INSERT OR IGNORE INTO xp_sources(user_id,source_key,category,farmies) VALUES (?,?,?,?)", (user_id,source_key,category,farmies))
    if not inserted.rowcount: return 0
    column = 'sales_remainder' if category == 'sales' else 'development_remainder'
    rate = max(1, setting(db, 'xp_sales_rate' if category == 'sales' else 'xp_development_rate'))
    remainder = db.execute(f"SELECT {column} FROM xp_wallets WHERE user_id=?", (user_id,)).fetchone()[0] + farmies
    xp, remainder = divmod(remainder, rate)
    db.execute(f"UPDATE xp_wallets SET {column}=?,total_xp=total_xp+?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (remainder,xp,user_id))
    if xp:
        db.execute("INSERT INTO xp_ledger(user_id,amount,event_key,category,reason,metadata) VALUES (?,?,?,?,?,?)",
            (user_id,xp,f"source:{source_key}",category,reason,json.dumps({'farmies':farmies,'rate':rate})))
        refresh_level(db,user_id)
    return xp


def adjust_xp(db: sqlite3.Connection, user_id: int, amount: int, event_key: str, reason: str) -> None:
    ensure_xp_wallet(db,user_id)
    total = db.execute("SELECT total_xp FROM xp_wallets WHERE user_id=?", (user_id,)).fetchone()[0]
    if total + amount < 0: raise HTTPException(400,"XP cannot fall below zero.")
    inserted = db.execute("INSERT OR IGNORE INTO xp_ledger(user_id,amount,event_key,category,reason) VALUES (?,?,?,?,?)", (user_id,amount,event_key,'manual',reason))
    if inserted.rowcount:
        db.execute("UPDATE xp_wallets SET total_xp=total_xp+?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (amount,user_id))
        refresh_level(db,user_id)


def backfill_xp(db: sqlite3.Connection) -> None:
    for row in db.execute("SELECT * FROM farmies_ledger ORDER BY id").fetchall():
        key, amount = row['event_key'], row['amount']
        if key.startswith('delivery:') and amount > 0:
            grant_xp_for_farmies(db,row['user_id'],key,'sales',amount,row['reason'])
        elif (key == 'farm:purchase' or key.startswith('animals:') or key.startswith('land:')) and amount < 0:
            grant_xp_for_farmies(db,row['user_id'],key,'development',abs(amount),row['reason'])


def sync_world(db: sqlite3.Connection, user_id: int) -> None:
    current = now()
    batches = db.execute("""SELECT b.*,s.production_seconds FROM animal_batches b JOIN species s USING(species_key)
        WHERE b.user_id=? AND b.quantity>0""", (user_id,)).fetchall()
    for batch in batches:
        if not batch["fed_until"]:
            continue
        start = dt(batch["last_production_at"])
        productive_until = min(current, dt(batch["fed_until"]))
        cycles = int((productive_until - start).total_seconds() // batch["production_seconds"])
        if cycles > 0:
            produced = cycles * batch["quantity"]
            advanced = start + timedelta(seconds=cycles * batch["production_seconds"])
            db.execute("UPDATE animal_batches SET pending_units=pending_units+?,last_production_at=? WHERE id=? AND user_id=?", (produced, advanced.isoformat(), batch["id"], user_id))
    ready = db.execute("SELECT * FROM deliveries WHERE user_id=? AND status='travelling' AND arrives_at<=?", (user_id, current.isoformat())).fetchall()
    for delivery in ready:
        transact(db, user_id, delivery["revenue"], f"delivery:{delivery['id']}", f"Market sale: {delivery['quantity']} {delivery['product_key']}", {"delivery_id": delivery["id"]})
        is_fish = db.execute("SELECT 1 FROM fish_species WHERE product_key=?",(delivery['product_key'],)).fetchone()
        if not is_fish or setting(db,'fishery_sales_xp_enabled'):
            grant_xp_for_farmies(db,user_id,f"delivery:{delivery['id']}",'sales',delivery['revenue'],f"Sold {delivery['quantity']} {delivery['product_key']}")
        db.execute("UPDATE deliveries SET status='sold',settled_at=? WHERE id=?", (current.isoformat(), delivery["id"]))
    db.execute("""UPDATE user_ponds SET status='ready',ready_fish=(
            SELECT c.fish_count FROM pond_cycles c WHERE c.id=(
                SELECT id FROM pond_cycles WHERE pond_id=user_ponds.id AND user_id=? AND status='growing' ORDER BY started_at DESC LIMIT 1))
        WHERE user_id=? AND status='growing' AND ready_at<=?""", (user_id, user_id, current.isoformat()))
    db.execute("UPDATE pond_cycles SET status='ready' WHERE user_id=? AND status='growing' AND ready_at<=?", (user_id,current.isoformat()))


def snapshot(db: sqlite3.Connection, user_id: int) -> dict:
    sync_world(db, user_id)
    farm = db.execute("SELECT * FROM farms WHERE user_id=?", (user_id,)).fetchone()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    species = [dict(row) for row in db.execute("SELECT * FROM species ORDER BY land_blocks")]
    current = now()
    for item in species:
        batches = db.execute("SELECT * FROM animal_batches WHERE user_id=? AND species_key=? ORDER BY id", (user_id, item["species_key"])).fetchall()
        active = [batch for batch in batches if batch["fed_until"] and dt(batch["fed_until"]) > current]
        hungry = [batch for batch in batches if not batch["fed_until"] or dt(batch["fed_until"]) <= current]
        item["quantity"] = sum(batch["quantity"] for batch in batches)
        item["pending_units"] = sum(batch["pending_units"] for batch in batches)
        item["fed_quantity"] = sum(batch["quantity"] for batch in active)
        item["hungry_quantity"] = sum(batch["quantity"] for batch in hungry)
        item["is_fed"] = bool(item["quantity"] and not item["hungry_quantity"])
        earliest_feed_expiry = min((dt(batch["fed_until"]) for batch in active), default=None)
        item["fed_until"] = earliest_feed_expiry.isoformat() if earliest_feed_expiry else None
        item["last_production_at"] = min((dt(batch["last_production_at"]) for batch in active), default=None)
        item["next_production_at"] = ""
        if active:
            item["next_production_at"] = min(dt(batch["last_production_at"]) + timedelta(seconds=item["production_seconds"]) for batch in active).isoformat()
    inventory = [dict(row) for row in db.execute("""SELECT s.product_key,s.product_name,s.product_icon,s.product_size,s.product_price,COALESCE(i.quantity,0) quantity
        FROM species s LEFT JOIN inventory i ON i.product_key=s.product_key AND i.user_id=? GROUP BY s.product_key ORDER BY s.product_name""", (user_id,))]
    feeds = [dict(row) for row in db.execute("""SELECT f.*,COALESCE(i.quantity,0) quantity FROM feeds f
        LEFT JOIN inventory i ON i.product_key=f.feed_key AND i.user_id=? ORDER BY f.name""", (user_id,))]
    feed_by_key = {feed["feed_key"]: feed for feed in feeds}
    for item in species:
        item["feed"] = feed_by_key.get(item["feed_key"], {"name": "No feed assigned", "quantity": 0})
    for feed in feeds:
        inventory.append({"product_key": feed["feed_key"], "product_name": feed["name"], "product_icon": feed["icon"],
            "product_size": feed["pack_size"], "product_price": None, "quantity": feed["quantity"], "is_feed": True})
    fish_species = [dict(row) for row in db.execute("SELECT * FROM fish_species WHERE enabled=1 ORDER BY name")]
    fish_seeds = [dict(row) for row in db.execute("SELECT * FROM fish_seeds WHERE enabled=1 ORDER BY name")]
    for fish in fish_species:
        fish["quantity"] = (db.execute("SELECT quantity FROM inventory WHERE user_id=? AND product_key=?",(user_id,fish["product_key"])).fetchone() or {"quantity":0})["quantity"]
        inventory.append({"product_key":fish["product_key"],"product_name":fish["product_name"],"product_icon":fish["product_icon"],
            "product_size":fish["product_size"],"product_price":fish["sale_price"],"quantity":fish["quantity"],"is_feed":False})
    for seed in fish_seeds:
        seed["quantity"] = (db.execute("SELECT quantity FROM inventory WHERE user_id=? AND product_key=?",(user_id,seed["seed_key"])).fetchone() or {"quantity":0})["quantity"]
        inventory.append({"product_key":seed["seed_key"],"product_name":seed["name"],"product_icon":seed["icon"],
            "product_size":seed["pack_size"],"product_price":None,"quantity":seed["quantity"],"is_feed":True})
    animal_land = sum(item["quantity"] * item["land_blocks"] for item in species)
    ponds = [dict(row) for row in db.execute("""SELECT p.*,c.name level_name,c.icon,c.land_blocks,c.sack_capacity,c.fish_per_sack,c.growth_seconds,
        c.fish_key,f.name fish_name,f.product_icon,s.seed_key,s.name seed_name,COALESCE(i.quantity,0) seed_quantity
        FROM user_ponds p JOIN pond_catalog c ON c.pond_level=p.pond_level JOIN fish_species f ON f.fish_key=c.fish_key
        LEFT JOIN fish_seeds s ON s.fish_key=c.fish_key AND s.enabled=1 LEFT JOIN inventory i ON i.user_id=p.user_id AND i.product_key=s.seed_key
        WHERE p.user_id=? ORDER BY p.id""",(user_id,))]
    pond_land = sum(pond["land_blocks"] for pond in ponds)
    inventory_used = sum(item["quantity"] * item["product_size"] for item in inventory)
    inventory_items = [item for item in inventory if item["quantity"] > 0]
    owned_species = [item for item in species if item["quantity"] > 0]
    deliveries = [dict(row) for row in db.execute("SELECT * FROM deliveries WHERE user_id=? ORDER BY started_at DESC LIMIT 10", (user_id,))]
    transport_busy = any(delivery["status"] == "travelling" for delivery in deliveries)
    cargo = [dict(row) for row in db.execute("""WITH products AS (
        SELECT product_key,product_name,product_icon,product_size,product_price FROM species
        UNION ALL SELECT product_key,product_name,product_icon,product_size,sale_price FROM fish_species)
        SELECT c.product_key,c.quantity,c.loaded_at,p.product_name,p.product_icon,p.product_size,p.product_price,
        c.quantity*p.product_size capacity_used,c.quantity*p.product_price revenue
        FROM transport_cargo c JOIN products p ON p.product_key=c.product_key WHERE c.user_id=? ORDER BY c.loaded_at,c.product_key""", (user_id,))]
    cargo_capacity = sum(item["capacity_used"] for item in cargo)
    cargo_revenue = sum(item["revenue"] for item in cargo)
    ledger = [dict(row) for row in db.execute("SELECT * FROM farmies_ledger WHERE user_id=? ORDER BY id DESC LIMIT 20", (user_id,))]
    expansions = [dict(row) for row in db.execute("SELECT * FROM expansion_prices ORDER BY blocks")]
    game_settings = {row["key"]: row["value"] for row in db.execute("SELECT key,value FROM settings")}
    ensure_xp_wallet(db,user_id)
    wallet = dict(db.execute("SELECT * FROM xp_wallets WHERE user_id=?",(user_id,)).fetchone())
    current_level = db.execute("SELECT * FROM levels WHERE level=?",(wallet['highest_level'],)).fetchone()
    next_level = db.execute("SELECT * FROM levels WHERE enabled=1 AND level>? ORDER BY level LIMIT 1",(wallet['highest_level'],)).fetchone()
    wallet['current_name'] = current_level['name'] if current_level else f"Level {wallet['highest_level']}"
    wallet['next_level'] = dict(next_level) if next_level else None
    wallet['progress_percent'] = 100 if not next_level else max(0,min(100,round((wallet['total_xp']-(current_level['xp_required'] if current_level else 0))*100/max(1,next_level['xp_required']-(current_level['xp_required'] if current_level else 0)))))
    wallet['next_unlocks'] = [] if not next_level else [row[0] for row in db.execute("""SELECT name FROM species WHERE required_level=? UNION ALL
        SELECT name FROM upgrade_catalog WHERE required_player_level=? AND enabled=1 ORDER BY name""",(next_level['level'],next_level['level'])).fetchall()]
    pond_limit_row = db.execute("SELECT max_ponds FROM pond_limits WHERE player_level<=? ORDER BY player_level DESC LIMIT 1",(wallet['highest_level'],)).fetchone()
    pond_limit = pond_limit_row['max_ponds'] if pond_limit_row else 0
    upgrades = [dict(row) for row in db.execute("""SELECT c.*,CASE WHEN u.upgrade_key IS NULL THEN 0 ELSE 1 END purchased
        FROM upgrade_catalog c LEFT JOIN user_upgrades u ON u.upgrade_key=c.upgrade_key AND u.user_id=? WHERE c.enabled=1 ORDER BY c.upgrade_type,c.upgrade_level""",(user_id,))]
    current_transport = db.execute("SELECT name FROM upgrade_catalog WHERE upgrade_type='transport' AND upgrade_level=?",(farm['transport_level'],)).fetchone()
    transport_name = current_transport['name'] if current_transport else 'Bicycle'
    transport_icon = '🚲' if farm['transport_level']==1 else ('🏍️' if 'bike' in transport_name.lower() else '🚚')
    game_settings['bicycle_capacity'] = farm['transport_capacity']; game_settings['bicycle_seconds'] = farm['transport_seconds']
    return {"farm": dict(farm), "user": dict(user), "species": species, "owned_species": owned_species, "inventory": inventory,
            "inventory_items": inventory_items, "animal_land": animal_land,
            "land_available": farm["total_blocks"] - farm["fixed_blocks"] - farm["inventory_blocks"] - animal_land - pond_land,
            "inventory_used": inventory_used, "deliveries": deliveries, "transport_busy": transport_busy,
            "cargo": cargo, "cargo_capacity": cargo_capacity, "cargo_revenue": cargo_revenue,
            "ledger": ledger, "expansions": expansions,
            "feeds": feeds, "fish_species":fish_species,"fish_seeds":fish_seeds,"ponds":ponds,"pond_land":pond_land,"pond_limit":pond_limit,
            "pond_catalog":[dict(row) for row in db.execute("SELECT * FROM pond_catalog WHERE enabled=1 ORDER BY pond_level")],
            "settings": game_settings, "xp": wallet, "upgrades": upgrades, "transport_name":transport_name,"transport_icon":transport_icon,"now_iso": current.isoformat()}


@app.middleware("http")
async def request_log(request: Request, call_next):
    started = time.perf_counter(); response = await call_next(request)
    logger.info("%s %s %s %.1fms", request.method, request.url.path, response.status_code, (time.perf_counter()-started)*1000)
    return response


@app.on_event("startup")
def startup():
    initialize_database(); logger.info("Animal Farm ready on port 8002")


@app.get("/login")
def login_page(request: Request, error: str = ""):
    if request.state.identity: return RedirectResponse("/", 303)
    return templates.TemplateResponse(request, "login.html", {"error": error})


@app.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...), name: str = Form(""), create: bool = Form(False)):
    email = email.strip().lower()
    with connection() as db:
        user = db.execute("SELECT * FROM users WHERE email=? AND auth_source='animal_farm'", (email,)).fetchone()
        if create:
            if user: return RedirectResponse("/login?error=Account+already+exists", 303)
            if len(password) < 8: return RedirectResponse("/login?error=Password+must+have+8+characters", 303)
            starting = setting(db, 'starting_farmies')
            next_id = max(1_000_000, db.execute("SELECT COALESCE(MAX(id),999999)+1 FROM users").fetchone()[0])
            result = db.execute("INSERT INTO users(id,email,name,password_hash,farmies) VALUES (?,?,?,?,?)", (next_id, email, name.strip() or email.split('@')[0], password_hash(password), starting))
            user_id = result.lastrowid; ensure_farm(db, user_id)
        else:
            if not user or not password_ok(password, user["password_hash"]): return RedirectResponse("/login?error=Invalid+email+or+password", 303)
            user_id = user["id"]
    response = RedirectResponse("/", 303); response.set_cookie("animal_farm_session", encode_session(user_id, load_secret(FARM_SECRET)), max_age=3600, httponly=True, samesite="lax")
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse("/login", 303); response.delete_cookie("animal_farm_session"); response.delete_cookie("daily_tracker_session"); return response


def user_id(request: Request) -> int:
    return request.state.identity["id"]


@app.get("/")
def dashboard(request: Request, error: str = ""):
    with connection() as db:
        state = snapshot(db, user_id(request))
        state["identity"] = request.state.identity
        state["error"] = error
    return templates.TemplateResponse(request, "dashboard.html", state)


@app.get("/state")
def state(request: Request):
    with connection() as db:
        data = snapshot(db, user_id(request))
    return data


@app.post("/farm/buy")
def buy_farm(request: Request):
    uid = user_id(request)
    with connection() as db:
        farm = db.execute("SELECT name,owned FROM farms WHERE user_id=?", (uid,)).fetchone()
        if not farm["name"].strip(): raise HTTPException(400, "Name your farm before purchasing it.")
        if farm["owned"]: raise HTTPException(409, "Farm already owned.")
        transact(db, uid, -setting(db,'farm_price'), "farm:purchase", "Purchased initial farm")
        grant_xp_for_farmies(db,uid,'farm:purchase','development',setting(db,'farm_price'),'Purchased initial farm')
        db.execute("UPDATE farms SET owned=1,updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (uid,))
    return RedirectResponse("/", 303)


@app.post("/farm/name")
def name_farm(request: Request, farm_name: str = Form(...)):
    uid = user_id(request); clean_name = " ".join(farm_name.split())
    if len(clean_name) < 2 or len(clean_name) > 60:
        raise HTTPException(400, "Farm name must contain between 2 and 60 characters.")
    with connection() as db:
        farm = db.execute("SELECT name FROM farms WHERE user_id=?", (uid,)).fetchone()
        if not farm: raise HTTPException(404, "Farm profile not found.")
        db.execute("UPDATE farms SET name=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (clean_name, uid))
        if farm["name"] and farm["name"] != clean_name:
            db.execute("INSERT INTO farmies_ledger(user_id,amount,event_key,reason,metadata) VALUES (?,?,?,?,?)", (uid, 0, f"farm-name:{uuid.uuid4().hex}", "Farm renamed", json.dumps({"from": farm["name"], "to": clean_name})))
    return RedirectResponse("/", 303)


@app.post("/farm/expand")
def expand_farm(request: Request, blocks: int = Form(...)):
    uid = user_id(request)
    with connection() as db:
        row = db.execute("SELECT price,required_level FROM expansion_prices WHERE blocks=?", (blocks,)).fetchone()
        if not row: raise HTTPException(400, "Invalid expansion.")
        ensure_xp_wallet(db,uid); level=db.execute('SELECT highest_level FROM xp_wallets WHERE user_id=?',(uid,)).fetchone()[0]
        if row['required_level'] is None: raise HTTPException(403,'This land expansion does not have an unlock level yet.')
        if level<row['required_level']: raise HTTPException(403,f"Reach Level {row['required_level']} to buy this land expansion.")
        event = f"land:{uuid.uuid4().hex}"
        transact(db, uid, -row["price"], event, f"Purchased {blocks} land blocks")
        grant_xp_for_farmies(db,uid,event,'development',row['price'],f"Purchased {blocks} land blocks")
        db.execute("UPDATE farms SET total_blocks=total_blocks+?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (blocks, uid))
    return RedirectResponse("/", 303)


@app.post("/animals/buy")
def buy_animals(request: Request, species_key: str = Form(...), quantity: int = Form(...)):
    uid = user_id(request)
    if quantity < 1 or quantity > 1000: raise HTTPException(400, "Invalid quantity.")
    with connection() as db:
        state = snapshot(db, uid); species = db.execute("SELECT * FROM species WHERE species_key=?", (species_key,)).fetchone()
        if not state["farm"]["owned"] or not species: raise HTTPException(400, "Buy the farm first.")
        if species['required_level'] is None: raise HTTPException(403,"This animal does not have an unlock level yet.")
        if state['xp']['highest_level'] < species['required_level']: raise HTTPException(403,f"Reach Level {species['required_level']} to buy {species['name']}.")
        needed = species["land_blocks"] * quantity
        if needed > state["land_available"]: raise HTTPException(400, "Not enough free land blocks.")
        event=f"animals:{uuid.uuid4().hex}"; cost=species['buy_price']*quantity
        transact(db, uid, -cost, event, f"Purchased {quantity} {species['name']}")
        grant_xp_for_farmies(db,uid,event,'development',cost,f"Purchased {quantity} {species['name']}")
        timestamp = now().isoformat()
        db.execute("INSERT INTO animal_batches(user_id,species_key,quantity,last_production_at,purchased_at) VALUES (?,?,?,?,?)", (uid, species_key, quantity, timestamp, timestamp))
    return RedirectResponse("/", 303)


@app.post("/animals/feed")
def feed_animals(request: Request, species_key: str = Form(...)):
    uid = user_id(request)
    with connection() as db:
        sync_world(db, uid)
        row = db.execute("""SELECT s.name,s.feed_hours,f.feed_key,f.name feed_name FROM species s
            JOIN feeds f ON f.feed_key=s.feed_key WHERE s.species_key=?""", (species_key,)).fetchone()
        if not row: raise HTTPException(404, "Animal feed not found.")
        current = now()
        hungry_batches = db.execute("""SELECT * FROM animal_batches WHERE user_id=? AND species_key=?
            AND (fed_until IS NULL OR fed_until<=?) ORDER BY id""", (uid, species_key, current.isoformat())).fetchall()
        needed = sum(batch["quantity"] for batch in hungry_batches)
        if needed < 1:
            owned = db.execute("SELECT COUNT(*) FROM animal_batches WHERE user_id=? AND species_key=?", (uid, species_key)).fetchone()[0]
            if not owned: raise HTTPException(404, "No animals to feed.")
            raise HTTPException(409, f"{row['name']} are already fed. Wait for the current feed cycle to finish.")
        stock = db.execute("SELECT quantity FROM inventory WHERE user_id=? AND product_key=?", (uid, row["feed_key"])).fetchone()
        if not stock or stock["quantity"] < needed:
            pack_word = "pack" if needed == 1 else "packs"
            raise HTTPException(400, f"You need {needed} {row['feed_name']} {pack_word} in inventory.")
        db.execute("UPDATE inventory SET quantity=quantity-? WHERE user_id=? AND product_key=?", (needed, uid, row["feed_key"]))
        batch_ids = [batch["id"] for batch in hungry_batches]
        placeholders = ",".join("?" for _ in batch_ids)
        db.execute(f"UPDATE animal_batches SET fed_until=?,last_production_at=? WHERE user_id=? AND id IN ({placeholders})", ((current + timedelta(hours=row["feed_hours"])).isoformat(), current.isoformat(), uid, *batch_ids))
    return RedirectResponse("/", 303)


@app.post("/animals/sell")
def sell_animals(request: Request, species_key: str = Form(...), quantity: int = Form(...)):
    """Sell owned livestock at the admin-configured price without awarding XP."""
    uid = user_id(request)
    if quantity < 1 or quantity > 1000:
        raise HTTPException(400, "Choose a valid number of animals to sell.")
    with connection() as db:
        sync_world(db, uid)
        species = db.execute(
            "SELECT name,sell_price FROM species WHERE species_key=?", (species_key,)
        ).fetchone()
        if not species:
            raise HTTPException(404, "Animal species not found.")
        if species["sell_price"] < 0:
            raise HTTPException(400, "This animal does not have a valid selling price.")
        batches = db.execute(
            """SELECT id,quantity,pending_units FROM animal_batches
               WHERE user_id=? AND species_key=? AND quantity>0 ORDER BY id DESC""",
            (uid, species_key),
        ).fetchall()
        owned = sum(batch["quantity"] for batch in batches)
        if quantity > owned:
            raise HTTPException(400, f"You only own {owned} {species['name']}.")
        if any(batch["pending_units"] > 0 for batch in batches):
            raise HTTPException(400, "Collect this animal's ready products before selling it.")
        remaining = quantity
        for batch in batches:
            sold = min(remaining, batch["quantity"])
            new_quantity = batch["quantity"] - sold
            if new_quantity:
                db.execute(
                    "UPDATE animal_batches SET quantity=? WHERE id=? AND user_id=?",
                    (new_quantity, batch["id"], uid),
                )
            else:
                db.execute("DELETE FROM animal_batches WHERE id=? AND user_id=?", (batch["id"], uid))
            remaining -= sold
            if not remaining:
                break
        revenue = species["sell_price"] * quantity
        transact(
            db,
            uid,
            revenue,
            f"animal-sale:{uuid.uuid4().hex}",
            f"Sold {quantity} {species['name']}",
            {"species_key": species_key, "quantity": quantity, "unit_price": species["sell_price"]},
        )
    return RedirectResponse("/?open=my-animals-screen", 303)


@app.post("/market/feed/buy")
def buy_feed(request: Request, feed_key: str = Form(...), quantity: int = Form(...)):
    uid = user_id(request)
    if quantity < 1 or quantity > 10000: raise HTTPException(400, "Invalid feed quantity.")
    with connection() as db:
        state = snapshot(db, uid)
        feed = db.execute("SELECT * FROM feeds WHERE feed_key=?", (feed_key,)).fetchone()
        if not feed: raise HTTPException(404, "Feed not found.")
        needed_capacity = feed["pack_size"] * quantity
        free_capacity = state["farm"]["inventory_capacity"] - state["inventory_used"]
        if needed_capacity > free_capacity + 1e-9: raise HTTPException(400, "Not enough inventory capacity.")
        transact(db, uid, -(feed["pack_price"] * quantity), f"feed-purchase:{uuid.uuid4().hex}", f"Purchased {quantity} {feed['name']} packs")
        db.execute("""INSERT INTO inventory(user_id,product_key,quantity) VALUES (?,?,?)
            ON CONFLICT(user_id,product_key) DO UPDATE SET quantity=quantity+excluded.quantity""", (uid, feed_key, quantity))
    return RedirectResponse("/", 303)


@app.post("/animals/collect")
def collect_product(request: Request, species_key: str = Form(...)):
    uid = user_id(request)
    with connection() as db:
        state = snapshot(db, uid); row = db.execute("SELECT product_key,product_name,product_size FROM species WHERE species_key=?", (species_key,)).fetchone()
        batches = db.execute("SELECT id,pending_units FROM animal_batches WHERE user_id=? AND species_key=? AND pending_units>0 ORDER BY id", (uid, species_key)).fetchall()
        pending_total = sum(batch["pending_units"] for batch in batches)
        if not row or pending_total < 1: raise HTTPException(400, "Nothing is ready.")
        free = state["farm"]["inventory_capacity"] - state["inventory_used"]
        collectable = min(pending_total, int(free // row["product_size"]))
        if collectable < 1: raise HTTPException(400, "Inventory is full.")
        remaining = collectable
        for batch in batches:
            taken = min(remaining, batch["pending_units"])
            db.execute("UPDATE animal_batches SET pending_units=pending_units-? WHERE id=? AND user_id=?", (taken, batch["id"], uid))
            remaining -= taken
            if not remaining: break
        db.execute("""INSERT INTO inventory(user_id,product_key,quantity) VALUES (?,?,?)
            ON CONFLICT(user_id,product_key) DO UPDATE SET quantity=quantity+excluded.quantity""", (uid, row["product_key"], collectable))
    return RedirectResponse("/", 303)


@app.post("/market/fish-seed/buy")
def buy_fish_seed(request: Request, seed_key: str = Form(...), quantity: int = Form(...)):
    uid=user_id(request)
    if quantity<1 or quantity>1000: raise HTTPException(400,"Choose a valid sack quantity.")
    with connection() as db:
        state=snapshot(db,uid); seed=db.execute("SELECT * FROM fish_seeds WHERE seed_key=? AND enabled=1",(seed_key,)).fetchone()
        if not seed: raise HTTPException(404,"Fish seed not found.")
        if seed['pack_size']*quantity > state['farm']['inventory_capacity']-state['inventory_used']+1e-9: raise HTTPException(400,"Not enough inventory capacity.")
        transact(db,uid,-seed['pack_price']*quantity,f"fish-seed:{uuid.uuid4().hex}",f"Purchased {quantity} {seed['name']} sacks")
        db.execute("""INSERT INTO inventory(user_id,product_key,quantity) VALUES (?,?,?)
            ON CONFLICT(user_id,product_key) DO UPDATE SET quantity=quantity+excluded.quantity""",(uid,seed_key,quantity))
    return RedirectResponse("/?open=market-dialog&market=fishery",303)


@app.post("/ponds/buy")
def buy_pond(request: Request, pond_level: int=Form(...), pond_name: str=Form(...)):
    uid=user_id(request); clean_name=" ".join(pond_name.split())[:60]
    if len(clean_name)<2: raise HTTPException(400,"Give the pond a name.")
    with connection() as db:
        state=snapshot(db,uid); catalog=db.execute("SELECT * FROM pond_catalog WHERE pond_level=? AND enabled=1",(pond_level,)).fetchone()
        first=db.execute("SELECT MIN(pond_level) FROM pond_catalog WHERE enabled=1").fetchone()[0]
        if not catalog or pond_level!=first: raise HTTPException(400,"New ponds must start at the first enabled pond level.")
        if state['xp']['highest_level']<catalog['required_player_level']: raise HTTPException(403,f"Reach Level {catalog['required_player_level']} to build this pond.")
        if len(state['ponds'])>=state['pond_limit']: raise HTTPException(403,f"Your current player level allows {state['pond_limit']} pond{'s' if state['pond_limit'] != 1 else ''}.")
        if catalog['land_blocks']>state['land_available']: raise HTTPException(400,f"You need {catalog['land_blocks']} free land blocks.")
        event=f"pond:{uuid.uuid4().hex}"; transact(db,uid,-catalog['cost'],event,f"Built {clean_name}")
        if setting(db,'fishery_development_xp_enabled'):
            grant_xp_for_farmies(db,uid,event,'development',catalog['cost'],f"Built {clean_name}")
        pond_id=db.execute("INSERT INTO user_ponds(user_id,name,pond_level) VALUES (?,?,?)",(uid,clean_name,pond_level)).lastrowid
        db.execute("INSERT INTO pond_upgrade_history(user_id,pond_id,from_level,to_level,cost) VALUES (?,?,NULL,?,?)",(uid,pond_id,pond_level,catalog['cost']))
    return RedirectResponse("/?open=fishery-screen",303)


@app.post("/ponds/{pond_id}/stock")
def stock_pond(request: Request, pond_id: int, sacks: int=Form(...)):
    uid=user_id(request)
    with connection() as db:
        sync_world(db,uid); pond=db.execute("""SELECT p.*,c.sack_capacity,c.fish_per_sack,c.growth_seconds,c.fish_key,s.seed_key
            FROM user_ponds p JOIN pond_catalog c ON c.pond_level=p.pond_level JOIN fish_seeds s ON s.fish_key=c.fish_key AND s.enabled=1
            WHERE p.id=? AND p.user_id=?""",(pond_id,uid)).fetchone()
        if not pond: raise HTTPException(404,"Pond not found.")
        if pond['status']!='idle': raise HTTPException(409,"Harvest the current pond cycle before stocking again.")
        if sacks<1 or sacks>pond['sack_capacity']: raise HTTPException(400,f"This pond accepts 1 to {pond['sack_capacity']} sacks.")
        stock=db.execute("SELECT quantity FROM inventory WHERE user_id=? AND product_key=?",(uid,pond['seed_key'])).fetchone()
        if not stock or stock['quantity']<sacks: raise HTTPException(400,"Not enough fish-seed sacks in inventory.")
        started=now(); ready=started+timedelta(seconds=pond['growth_seconds']); fish_count=sacks*pond['fish_per_sack']; cycle_id=uuid.uuid4().hex
        db.execute("UPDATE inventory SET quantity=quantity-? WHERE user_id=? AND product_key=?",(sacks,uid,pond['seed_key']))
        db.execute("UPDATE user_ponds SET status='growing',stocked_sacks=?,cycle_started_at=?,ready_at=?,ready_fish=0 WHERE id=? AND user_id=?",(sacks,started.isoformat(),ready.isoformat(),pond_id,uid))
        db.execute("INSERT INTO pond_cycles VALUES (?,?,?,?,?,?,?,?,?,NULL,'growing')",(cycle_id,uid,pond_id,pond['pond_level'],sacks,fish_count,pond['fish_key'],started.isoformat(),ready.isoformat()))
    return RedirectResponse("/?open=fishery-screen",303)


@app.post("/ponds/{pond_id}/harvest")
def harvest_pond(request: Request, pond_id: int):
    uid=user_id(request)
    with connection() as db:
        state=snapshot(db,uid); pond=db.execute("""SELECT p.*,cyc.id AS cycle_id,cyc.fish_count AS cycle_fish_count,
            f.product_key,f.product_name,f.product_size FROM user_ponds p
            JOIN pond_cycles cyc ON cyc.pond_id=p.id AND cyc.user_id=p.user_id AND cyc.status='ready'
            JOIN fish_species f ON f.fish_key=cyc.fish_key
            WHERE p.id=? AND p.user_id=? ORDER BY cyc.started_at DESC LIMIT 1""",(pond_id,uid)).fetchone()
        if not pond or pond['status']!='ready' or pond['ready_fish']<1: raise HTTPException(400,"Fish are not ready to harvest.")
        harvested=pond['cycle_fish_count']
        if harvested*pond['product_size']>state['farm']['inventory_capacity']-state['inventory_used']+1e-9: raise HTTPException(400,"Inventory does not have enough room for this harvest.")
        db.execute("""INSERT INTO inventory(user_id,product_key,quantity) VALUES (?,?,?)
            ON CONFLICT(user_id,product_key) DO UPDATE SET quantity=quantity+excluded.quantity""",(uid,pond['product_key'],harvested))
        stamp=now().isoformat()
        db.execute("UPDATE user_ponds SET status='idle',stocked_sacks=0,cycle_started_at=NULL,ready_at=NULL,ready_fish=0,lifetime_harvest=lifetime_harvest+? WHERE id=? AND user_id=?",(harvested,pond_id,uid))
        db.execute("UPDATE pond_cycles SET status='harvested',harvested_at=? WHERE id=? AND user_id=?",(stamp,pond['cycle_id'],uid))
    return RedirectResponse("/?open=fishery-screen",303)


@app.post("/ponds/{pond_id}/upgrade")
def upgrade_pond(request: Request, pond_id: int):
    uid=user_id(request)
    with connection() as db:
        state=snapshot(db,uid); pond=db.execute("SELECT * FROM user_ponds WHERE id=? AND user_id=?",(pond_id,uid)).fetchone()
        if not pond: raise HTTPException(404,"Pond not found.")
        if pond['status']!='idle': raise HTTPException(409,"Finish and harvest the active cycle before upgrading.")
        current=db.execute("SELECT * FROM pond_catalog WHERE pond_level=?",(pond['pond_level'],)).fetchone()
        target=db.execute("SELECT * FROM pond_catalog WHERE enabled=1 AND pond_level>? ORDER BY pond_level LIMIT 1",(pond['pond_level'],)).fetchone()
        if not target: raise HTTPException(400,"No higher pond level is available.")
        if state['xp']['highest_level']<target['required_player_level']: raise HTTPException(403,f"Reach Level {target['required_player_level']} first.")
        extra=max(0,target['land_blocks']-current['land_blocks'])
        if extra>state['land_available']: raise HTTPException(400,f"You need {extra} additional free land blocks.")
        event=f"pond-upgrade:{pond_id}:{target['pond_level']}"; transact(db,uid,-target['cost'],event,f"Upgraded {pond['name']} to {target['name']}")
        if setting(db,'fishery_development_xp_enabled'):
            grant_xp_for_farmies(db,uid,event,'development',target['cost'],f"Upgraded {pond['name']}")
        db.execute("UPDATE user_ponds SET pond_level=? WHERE id=? AND user_id=?",(target['pond_level'],pond_id,uid))
        db.execute("INSERT INTO pond_upgrade_history(user_id,pond_id,from_level,to_level,cost) VALUES (?,?,?,?,?)",(uid,pond_id,pond['pond_level'],target['pond_level'],target['cost']))
    return RedirectResponse("/?open=fishery-screen",303)


@app.post("/transport/load")
def load_transport(request: Request, product_key: str = Form(...), quantity: int = Form(...)):
    uid = user_id(request)
    if quantity < 1: raise HTTPException(400, "Invalid quantity.")
    with connection() as db:
        sync_world(db, uid)
        if db.execute("SELECT 1 FROM deliveries WHERE user_id=? AND status='travelling' LIMIT 1", (uid,)).fetchone():
            raise HTTPException(409, "The bicycle is currently delivering goods.")
        product = db.execute("""SELECT product_key,product_name,product_size,product_price FROM species WHERE product_key=?
            UNION ALL SELECT product_key,product_name,product_size,sale_price FROM fish_species WHERE product_key=? LIMIT 1""", (product_key,product_key)).fetchone()
        stock = db.execute("SELECT quantity FROM inventory WHERE user_id=? AND product_key=?", (uid, product_key)).fetchone()
        if not product or not stock or stock["quantity"] < quantity: raise HTTPException(400, "Not enough inventory.")
        loaded_capacity = db.execute("""WITH products AS (SELECT product_key,product_size FROM species UNION ALL SELECT product_key,product_size FROM fish_species)
            SELECT COALESCE(SUM(c.quantity*p.product_size),0) total FROM transport_cargo c JOIN products p ON p.product_key=c.product_key WHERE c.user_id=?""", (uid,)).fetchone()["total"]
        capacity = product["product_size"] * quantity
        max_capacity = db.execute("SELECT transport_capacity FROM farms WHERE user_id=?",(uid,)).fetchone()[0]
        if loaded_capacity + capacity > max_capacity + 1e-9: raise HTTPException(400, f"Only {max_capacity - loaded_capacity:g} bicycle-capacity blocks remain.")
        db.execute("UPDATE inventory SET quantity=quantity-? WHERE user_id=? AND product_key=?", (quantity, uid, product_key))
        db.execute("""INSERT INTO transport_cargo(user_id,product_key,quantity) VALUES (?,?,?)
            ON CONFLICT(user_id,product_key) DO UPDATE SET quantity=quantity+excluded.quantity""", (uid, product_key, quantity))
    return RedirectResponse("/", 303)


@app.post("/inventory/discard")
def discard_inventory(request: Request, product_key: str = Form(...), quantity: int = Form(...)):
    """Permanently discard a quantity of the signed-in user's stored item."""
    uid = user_id(request)
    if quantity < 1:
        raise HTTPException(400, "Choose a valid quantity to discard.")
    with connection() as db:
        stock = db.execute(
            "SELECT quantity FROM inventory WHERE user_id=? AND product_key=?",
            (uid, product_key),
        ).fetchone()
        if not stock or stock["quantity"] < quantity:
            raise HTTPException(400, "You do not have that quantity in inventory.")
        item = db.execute(
            """SELECT product_name AS name FROM species WHERE product_key=?
               UNION ALL
               SELECT name FROM feeds WHERE feed_key=?
               UNION ALL
               SELECT product_name FROM fish_species WHERE product_key=?
               UNION ALL
               SELECT name FROM fish_seeds WHERE seed_key=?
               LIMIT 1""",
            (product_key, product_key, product_key, product_key),
        ).fetchone()
        if not item:
            raise HTTPException(404, "Inventory item not found.")
        db.execute(
            "UPDATE inventory SET quantity=quantity-? WHERE user_id=? AND product_key=?",
            (quantity, uid, product_key),
        )
        db.execute(
            """INSERT INTO farmies_ledger(user_id,amount,event_key,reason,metadata)
               VALUES (?,?,?,?,?)""",
            (
                uid,
                0,
                f"inventory-discard:{uuid.uuid4().hex}",
                f"Discarded {quantity} {item['name']}",
                json.dumps({"product_key": product_key, "quantity": quantity}),
            ),
        )
    return RedirectResponse("/?open=inventory-screen", 303)


@app.post("/transport/cargo/{product_key}/remove")
def remove_transport_cargo(request: Request, product_key: str):
    uid = user_id(request)
    with connection() as db:
        sync_world(db, uid)
        if db.execute("SELECT 1 FROM deliveries WHERE user_id=? AND status='travelling' LIMIT 1", (uid,)).fetchone():
            raise HTTPException(409, "The bicycle is currently delivering goods.")
        cargo = db.execute("SELECT quantity FROM transport_cargo WHERE user_id=? AND product_key=?", (uid, product_key)).fetchone()
        if not cargo: raise HTTPException(404, "That cargo is not loaded.")
        db.execute("""INSERT INTO inventory(user_id,product_key,quantity) VALUES (?,?,?)
            ON CONFLICT(user_id,product_key) DO UPDATE SET quantity=quantity+excluded.quantity""", (uid, product_key, cargo["quantity"]))
        db.execute("DELETE FROM transport_cargo WHERE user_id=? AND product_key=?", (uid, product_key))
    return RedirectResponse("/", 303)


@app.post("/transport/send")
def send_transport(request: Request):
    uid = user_id(request)
    with connection() as db:
        sync_world(db, uid)
        if db.execute("SELECT 1 FROM deliveries WHERE user_id=? AND status='travelling' LIMIT 1", (uid,)).fetchone():
            raise HTTPException(409, "The bicycle is currently delivering goods.")
        cargo = db.execute("""WITH products AS (SELECT product_key,product_size,product_price FROM species
            UNION ALL SELECT product_key,product_size,sale_price FROM fish_species)
            SELECT c.product_key,c.quantity,p.product_size,p.product_price
            FROM transport_cargo c JOIN products p ON p.product_key=c.product_key WHERE c.user_id=?""", (uid,)).fetchall()
        if not cargo: raise HTTPException(400, "Load goods before sending the bicycle.")
        capacity = sum(item["quantity"] * item["product_size"] for item in cargo)
        farm_transport = db.execute("SELECT transport_capacity,transport_seconds FROM farms WHERE user_id=?",(uid,)).fetchone()
        max_capacity = farm_transport['transport_capacity']
        if capacity > max_capacity + 1e-9: raise HTTPException(400, f"Bicycle capacity is {max_capacity:g} blocks.")
        started = now(); arrives = started + timedelta(seconds=farm_transport['transport_seconds'])
        for item in cargo:
            item_capacity = item["quantity"] * item["product_size"]
            db.execute("INSERT INTO deliveries VALUES (?,?,?,?,?,?,?,?,?,NULL)",
                (uuid.uuid4().hex, uid, item["product_key"], item["quantity"], item_capacity,
                 item["product_price"] * item["quantity"], started.isoformat(), arrives.isoformat(), "travelling"))
        db.execute("DELETE FROM transport_cargo WHERE user_id=?", (uid,))
    return RedirectResponse("/", 303)


@app.post("/upgrades/{upgrade_key}/buy")
def buy_upgrade(request: Request, upgrade_key: str):
    uid=user_id(request)
    with connection() as db:
        state=snapshot(db,uid); upgrade=db.execute("SELECT * FROM upgrade_catalog WHERE upgrade_key=? AND enabled=1",(upgrade_key,)).fetchone()
        if not upgrade: raise HTTPException(404,"Upgrade not found.")
        if state['xp']['highest_level'] < upgrade['required_player_level']: raise HTTPException(403,f"Reach Level {upgrade['required_player_level']} first.")
        if db.execute("SELECT 1 FROM user_upgrades WHERE user_id=? AND upgrade_key=?",(uid,upgrade_key)).fetchone(): raise HTTPException(409,"Upgrade already purchased.")
        farm=db.execute("SELECT * FROM farms WHERE user_id=?",(uid,)).fetchone()
        current_upgrade_level = farm['inventory_level'] if upgrade['upgrade_type']=='inventory' else farm['transport_level']
        if upgrade['upgrade_level'] != current_upgrade_level + 1: raise HTTPException(400,f"Purchase Level {current_upgrade_level + 1} first.")
        if upgrade['upgrade_type']=='inventory':
            land_needed=max(0,int((upgrade['capacity']-farm['inventory_capacity'] + setting(db,'capacity_per_land',float)-1)//setting(db,'capacity_per_land',float)))
            if land_needed>state['land_available']: raise HTTPException(400,f"You need {land_needed} free land blocks.")
        event=f"upgrade:{upgrade_key}:{uid}"; transact(db,uid,-upgrade['cost'],event,f"Purchased {upgrade['name']}")
        grant_xp_for_farmies(db,uid,event,'development',upgrade['cost'],f"Purchased {upgrade['name']}")
        db.execute("INSERT INTO user_upgrades(user_id,upgrade_key) VALUES (?,?)",(uid,upgrade_key))
        if upgrade['upgrade_type']=='inventory':
            db.execute("UPDATE farms SET inventory_level=?,inventory_capacity=?,inventory_blocks=inventory_blocks+?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?",(upgrade['upgrade_level'],upgrade['capacity'],land_needed,uid))
        else:
            db.execute("UPDATE farms SET transport_level=?,transport_capacity=?,transport_seconds=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?",(upgrade['upgrade_level'],upgrade['capacity'],upgrade['seconds'],uid))
    return RedirectResponse('/',303)


def require_admin(request: Request) -> None:
    if request.state.identity["role"] != "admin": raise HTTPException(403, "Admin access required.")


def catalog_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if not key: raise HTTPException(400, "Enter a name containing letters or numbers.")
    return key[:48]


@app.get("/admin")
def admin_page(request: Request, error: str = ""):
    require_admin(request)
    with connection() as db:
        settings = [dict(row) for row in db.execute("SELECT * FROM settings ORDER BY key")]
        species = [dict(row) for row in db.execute("SELECT * FROM species ORDER BY name")]
        feeds = [dict(row) for row in db.execute("""SELECT f.*,COALESCE(GROUP_CONCAT(s.name, ', '),'Not assigned') species_name
            FROM feeds f LEFT JOIN species s ON s.feed_key=f.feed_key GROUP BY f.feed_key ORDER BY f.name""")]
        expansions = [dict(row) for row in db.execute("SELECT * FROM expansion_prices ORDER BY blocks")]
        levels = [dict(row) for row in db.execute("SELECT * FROM levels ORDER BY level")]
        upgrades = [dict(row) for row in db.execute("SELECT * FROM upgrade_catalog ORDER BY upgrade_type,upgrade_level")]
        users = [dict(row) for row in db.execute("""SELECT u.id,u.email,u.name,u.role,u.auth_source,u.farmies,COALESCE(x.total_xp,0) total_xp,COALESCE(x.highest_level,1) highest_level
            FROM users u LEFT JOIN xp_wallets x ON x.user_id=u.id ORDER BY u.id""")]
        xp_history=[dict(row) for row in db.execute("""SELECT x.*,u.name FROM xp_ledger x JOIN users u ON u.id=x.user_id ORDER BY x.id DESC LIMIT 100""")]
        fish_species=[dict(row) for row in db.execute("SELECT * FROM fish_species ORDER BY name")]
        fish_seeds=[dict(row) for row in db.execute("SELECT * FROM fish_seeds ORDER BY name")]
        pond_catalog=[dict(row) for row in db.execute("SELECT * FROM pond_catalog ORDER BY pond_level")]
        pond_limits=[dict(row) for row in db.execute("""SELECT l.level,l.name,COALESCE(p.max_ponds,0) max_ponds
            FROM levels l LEFT JOIN pond_limits p ON p.player_level=l.level ORDER BY l.level""")]
        user_ponds=[dict(row) for row in db.execute("""SELECT p.id,p.name pond_name,p.status,p.pond_level,p.stocked_sacks,p.ready_fish,
            p.lifetime_harvest,p.created_at,u.name farmer_name,u.email,c.name level_name
            FROM user_ponds p JOIN users u ON u.id=p.user_id JOIN pond_catalog c ON c.pond_level=p.pond_level
            ORDER BY p.id DESC LIMIT 200""")]
        pond_cycles=[dict(row) for row in db.execute("""SELECT x.id,x.status,x.sacks,x.fish_count,x.started_at,x.ready_at,x.harvested_at,
            p.name pond_name,u.name farmer_name,f.name fish_name
            FROM pond_cycles x JOIN user_ponds p ON p.id=x.pond_id JOIN users u ON u.id=x.user_id
            JOIN fish_species f ON f.fish_key=x.fish_key ORDER BY x.started_at DESC LIMIT 200""")]
    return templates.TemplateResponse(request, "admin.html", {"settings": settings, "species": species, "feeds": feeds, "expansions": expansions, "users": users, "levels":levels,"upgrades":upgrades,"xp_history":xp_history,"fish_species":fish_species,"fish_seeds":fish_seeds,"pond_catalog":pond_catalog,"pond_limits":pond_limits,"user_ponds":user_ponds,"pond_cycles":pond_cycles,"identity": request.state.identity, "error": error})


@app.post("/admin/settings")
def admin_setting(request: Request, key: str = Form(...), value: str = Form(...)):
    require_admin(request)
    allowed = {'starting_farmies','farm_price','initial_land_blocks','fixed_land_blocks','inventory_blocks','inventory_capacity','bicycle_capacity','bicycle_seconds','xp_sales_rate','xp_development_rate','fishery_sales_xp_enabled','fishery_development_xp_enabled','capacity_per_land'}
    if key not in allowed or float(value) < 0 or (key in {'xp_sales_rate','xp_development_rate','capacity_per_land'} and float(value)<=0): raise HTTPException(400, "Invalid setting.")
    with connection() as db: db.execute("UPDATE settings SET value=?,updated_at=CURRENT_TIMESTAMP WHERE key=?", (value, key))
    return RedirectResponse("/admin", 303)


@app.post("/admin/fish/pond-limits/{player_level}")
def admin_pond_limit(request: Request, player_level: int, max_ponds: int=Form(...)):
    require_admin(request)
    if max_ponds<0: raise HTTPException(400,"Pond limit cannot be negative.")
    with connection() as db:
        if not db.execute("SELECT 1 FROM levels WHERE level=?",(player_level,)).fetchone(): raise HTTPException(404,"Player level not found.")
        db.execute("""INSERT INTO pond_limits(player_level,max_ponds) VALUES (?,?)
            ON CONFLICT(player_level) DO UPDATE SET max_ponds=excluded.max_ponds,updated_at=CURRENT_TIMESTAMP""",(player_level,max_ponds))
    return RedirectResponse('/admin#fishery',303)


@app.post("/admin/levels/save")
def admin_level(request: Request, level: int=Form(...), name: str=Form(...), xp_required: int=Form(...), enabled: bool=Form(False)):
    require_admin(request)
    if level<1 or xp_required<0 or not name.strip(): raise HTTPException(400,"Invalid level values.")
    with connection() as db:
        lower=db.execute("SELECT MAX(xp_required) FROM levels WHERE level<?",(level,)).fetchone()[0]
        upper=db.execute("SELECT MIN(xp_required) FROM levels WHERE level>?",(level,)).fetchone()[0]
        if (lower is not None and xp_required<=lower) or (upper is not None and xp_required>=upper): raise HTTPException(400,"XP thresholds must increase with each level.")
        db.execute("""INSERT INTO levels(level,name,xp_required,enabled) VALUES (?,?,?,?) ON CONFLICT(level) DO UPDATE SET name=excluded.name,xp_required=excluded.xp_required,enabled=excluded.enabled""",(level,name.strip()[:60],xp_required,1 if enabled or level==1 else 0))
        for user in db.execute("SELECT user_id FROM xp_wallets").fetchall(): refresh_level(db,user['user_id'])
    return RedirectResponse('/admin',303)


@app.post("/admin/upgrades/{upgrade_key}")
def admin_upgrade(request: Request, upgrade_key: str, name: str=Form(...), required_player_level: int=Form(...), cost: int=Form(...), capacity: float=Form(...), journey_minutes: str=Form(""), enabled: bool=Form(False)):
    require_admin(request)
    try: journey_seconds = int(journey_minutes) * 60 if journey_minutes.strip() else None
    except ValueError: raise HTTPException(400,"Journey time must be a whole number of minutes.")
    if cost<0 or capacity<=0: raise HTTPException(400,"Invalid upgrade values.")
    with connection() as db:
        if not db.execute("SELECT 1 FROM levels WHERE level=? AND enabled=1",(required_player_level,)).fetchone(): raise HTTPException(400,"Choose an enabled player level.")
        upgrade=db.execute("SELECT upgrade_type FROM upgrade_catalog WHERE upgrade_key=?",(upgrade_key,)).fetchone()
        if not upgrade: raise HTTPException(404,"Upgrade not found.")
        if upgrade['upgrade_type']=='transport' and not journey_seconds: raise HTTPException(400,"Transport journey time is required.")
        db.execute("UPDATE upgrade_catalog SET name=?,required_player_level=?,cost=?,capacity=?,seconds=?,enabled=? WHERE upgrade_key=?",(name.strip()[:80],required_player_level,cost,capacity,journey_seconds,1 if enabled else 0,upgrade_key))
    return RedirectResponse('/admin',303)


@app.post("/admin/catalog/upgrades/create")
def admin_upgrade_create(request: Request, upgrade_type: str=Form(...), upgrade_level: int=Form(...), name: str=Form(...), required_player_level: int=Form(...), cost: int=Form(...), capacity: float=Form(...), journey_minutes: str=Form("")):
    require_admin(request)
    try: journey_seconds = int(journey_minutes) * 60 if journey_minutes.strip() else None
    except ValueError: raise HTTPException(400,"Journey time must be a whole number of minutes.")
    if upgrade_type not in ('inventory','transport') or upgrade_level<2 or cost<0 or capacity<=0 or (upgrade_type=='transport' and (not journey_seconds or journey_seconds<1)):
        raise HTTPException(400,"Invalid upgrade values.")
    key=f"{upgrade_type}_{upgrade_level}"
    with connection() as db:
        if not db.execute("SELECT 1 FROM levels WHERE level=? AND enabled=1",(required_player_level,)).fetchone(): raise HTTPException(400,"Choose an enabled player level.")
        try: db.execute("INSERT INTO upgrade_catalog VALUES (?,?,?,?,?,?,?,?,1)",(key,upgrade_type,upgrade_level,name.strip()[:80],required_player_level,cost,capacity,journey_seconds))
        except sqlite3.IntegrityError: raise HTTPException(409,"That upgrade level already exists.")
    return RedirectResponse('/admin',303)


@app.post("/admin/xp/adjust")
def admin_xp_adjust(request: Request, target_user_id: int=Form(...), amount: int=Form(...), reason: str=Form(...)):
    require_admin(request)
    if amount==0 or len(reason.strip())<3: raise HTTPException(400,"Enter a non-zero XP amount and a reason.")
    with connection() as db:
        if not db.execute("SELECT 1 FROM users WHERE id=?",(target_user_id,)).fetchone(): raise HTTPException(404,"User not found.")
        adjust_xp(db,target_user_id,amount,f"manual:{uuid.uuid4().hex}",reason.strip()[:200])
    return RedirectResponse('/admin',303)


@app.post("/admin/species/{species_key}")
def admin_species(request: Request, species_key: str, buy_price: int = Form(...), sell_price: int = Form(...), product_price: int = Form(...), production_minutes: int = Form(...), feed_hours: int = Form(...), land_blocks: int = Form(...), product_size: float = Form(...), feed_key: str = Form(...), required_level: int | None = Form(None)):
    require_admin(request)
    if min(buy_price,product_price,production_minutes,feed_hours,land_blocks) < 1 or sell_price < 0 or product_size <= 0: raise HTTPException(400, "Values must be positive, and the animal sell price cannot be negative.")
    with connection() as db:
        if not db.execute("SELECT 1 FROM feeds WHERE feed_key=?", (feed_key,)).fetchone(): raise HTTPException(400, "Selected feed does not exist.")
        if required_level and not db.execute("SELECT 1 FROM levels WHERE level=? AND enabled=1",(required_level,)).fetchone(): raise HTTPException(400,"Choose an enabled level.")
        result = db.execute("""UPDATE species SET buy_price=?,sell_price=?,product_price=?,production_seconds=?,feed_hours=?,land_blocks=?,product_size=?,feed_key=?,required_level=? WHERE species_key=?""", (buy_price,sell_price,product_price,production_minutes*60,feed_hours,land_blocks,product_size,feed_key,required_level,species_key))
        if not result.rowcount: raise HTTPException(404, "Species not found.")
    return RedirectResponse("/admin", 303)


@app.post("/admin/expansion/{blocks}")
def admin_expansion(request: Request, blocks: int, price: int = Form(...), required_level: int|None=Form(None)):
    require_admin(request)
    if price < 0: raise HTTPException(400, "Invalid price.")
    with connection() as db:
        if required_level and not db.execute('SELECT 1 FROM levels WHERE level=? AND enabled=1',(required_level,)).fetchone(): raise HTTPException(400,'Choose an enabled level.')
        db.execute("UPDATE expansion_prices SET price=?,required_level=? WHERE blocks=?", (price,required_level,blocks))
    return RedirectResponse("/admin", 303)


@app.post("/admin/feed/{feed_key}")
def admin_feed(request: Request, feed_key: str, pack_price: int = Form(...), pack_size: float = Form(...), icon: str = Form("🌾")):
    require_admin(request)
    if pack_price < 0 or pack_size <= 0: raise HTTPException(400, "Invalid feed values.")
    with connection() as db:
        result = db.execute("UPDATE feeds SET pack_price=?,pack_size=?,icon=? WHERE feed_key=?", (pack_price, pack_size, icon.strip()[:12] or "🌾", feed_key))
        if not result.rowcount: raise HTTPException(404, "Feed not found.")
    return RedirectResponse("/admin", 303)


@app.post("/admin/feeds/create")
def create_feed(request: Request, name: str = Form(...), icon: str = Form("🌾"), pack_price: int = Form(...), pack_size: float = Form(...), description: str = Form("")):
    require_admin(request)
    clean_name = " ".join(name.split())
    if len(clean_name) < 2 or len(clean_name) > 60 or pack_price < 0 or pack_size <= 0:
        raise HTTPException(400, "Enter a valid feed name, price, and positive pack size.")
    feed_key = catalog_key(clean_name)
    with connection() as db:
        if db.execute("SELECT 1 FROM feeds WHERE feed_key=? OR lower(name)=lower(?)", (feed_key, clean_name)).fetchone():
            raise HTTPException(409, "A feed with this name already exists.")
        db.execute("INSERT INTO feeds(feed_key,species_key,name,icon,pack_size,pack_price,description) VALUES (?,?,?,?,?,?,?)",
            (feed_key, f"catalog_{feed_key}", clean_name, icon.strip()[:12] or "🌾", pack_size, pack_price, description.strip()[:240]))
    return RedirectResponse("/admin", 303)


@app.post("/admin/catalog/species/create")
def create_species(request: Request, name: str = Form(...), icon: str = Form("🐾"), land_blocks: int = Form(...), buy_price: int = Form(...),
    sell_price: int = Form(...), product_name: str = Form(...), product_icon: str = Form("📦"), product_size: float = Form(...), product_price: int = Form(...),
    production_minutes: int = Form(...), feed_hours: int = Form(...), feed_key: str = Form(...), required_level: int | None = Form(None)):
    require_admin(request)
    clean_name = " ".join(name.split()); clean_product = " ".join(product_name.split())
    if min(land_blocks,buy_price,product_price,production_minutes,feed_hours) < 1 or sell_price < 0 or product_size <= 0 or len(clean_name) < 2 or len(clean_product) < 2:
        raise HTTPException(400, "Complete every animal and product field with positive values.")
    species_key = catalog_key(clean_name); product_key = catalog_key(clean_product)
    with connection() as db:
        if not db.execute("SELECT 1 FROM feeds WHERE feed_key=?", (feed_key,)).fetchone(): raise HTTPException(400, "Selected feed does not exist.")
        if required_level and not db.execute("SELECT 1 FROM levels WHERE level=? AND enabled=1",(required_level,)).fetchone(): raise HTTPException(400,"Choose an enabled level.")
        if db.execute("SELECT 1 FROM species WHERE species_key=? OR lower(name)=lower(?)", (species_key, clean_name)).fetchone(): raise HTTPException(409, "An animal with this name already exists.")
        if db.execute("SELECT 1 FROM species WHERE product_key=?", (product_key,)).fetchone(): raise HTTPException(409, "That product name is already used by another animal.")
        db.execute("""INSERT INTO species(species_key,name,icon,land_blocks,buy_price,sell_price,product_key,product_name,product_icon,product_size,
            product_price,production_seconds,feed_price,feed_hours,feed_key,required_level) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (species_key,clean_name,icon.strip()[:12] or "🐾",land_blocks,buy_price,sell_price,product_key,clean_product,product_icon.strip()[:12] or "📦",
             product_size,product_price,production_minutes*60,1,feed_hours,feed_key,required_level))
    return RedirectResponse("/admin", 303)


@app.post("/admin/fish/species/create")
def create_fish_species(request: Request, name: str=Form(...), icon: str=Form("🐟"), product_name: str=Form(...),
    product_icon: str=Form("🐟"), product_size: float=Form(...), sale_price: int=Form(...)):
    require_admin(request); clean=" ".join(name.split()); product=" ".join(product_name.split())
    if len(clean)<2 or len(product)<2 or product_size<=0 or sale_price<1: raise HTTPException(400,"Enter valid fish details.")
    fish_key=catalog_key(clean); product_key=catalog_key(product)
    with connection() as db:
        try: db.execute("INSERT INTO fish_species VALUES (?,?,?,?,?,?,?,?,1)",(fish_key,clean,icon.strip()[:12] or '🐟',product_key,product,product_icon.strip()[:12] or '🐟',product_size,sale_price))
        except sqlite3.IntegrityError: raise HTTPException(409,"That fish or product already exists.")
    return RedirectResponse('/admin#fishery',303)


@app.post("/admin/fish/seeds/create")
def create_fish_seed(request: Request, fish_key: str=Form(...), name: str=Form(...), icon: str=Form("🫘"),
    pack_size: float=Form(...), pack_price: int=Form(...), seeds_per_sack: int=Form(...)):
    require_admin(request); clean=" ".join(name.split())
    if len(clean)<2 or pack_size<=0 or pack_price<0 or seeds_per_sack<1: raise HTTPException(400,"Enter valid seed-sack details.")
    seed_key=catalog_key(clean)
    with connection() as db:
        if not db.execute("SELECT 1 FROM fish_species WHERE fish_key=?",(fish_key,)).fetchone(): raise HTTPException(400,"Fish species not found.")
        try: db.execute("INSERT INTO fish_seeds VALUES (?,?,?,?,?,?,?,1)",(seed_key,fish_key,clean,icon.strip()[:12] or '🫘',pack_size,pack_price,seeds_per_sack))
        except sqlite3.IntegrityError: raise HTTPException(409,"That seed product already exists.")
    return RedirectResponse('/admin#fishery',303)


@app.post("/admin/fish/ponds/create")
def create_pond_level(request: Request, pond_level: int=Form(...), name: str=Form(...), icon: str=Form("💧"),
    required_player_level: int=Form(...), cost: int=Form(...), land_blocks: int=Form(...), sack_capacity: int=Form(...),
    fish_per_sack: int=Form(...), growth_hours: int=Form(...), fish_key: str=Form(...)):
    require_admin(request); clean=" ".join(name.split())
    if pond_level<1 or len(clean)<2 or min(cost,land_blocks,sack_capacity,fish_per_sack,growth_hours)<1: raise HTTPException(400,"Enter valid pond-level details.")
    with connection() as db:
        if not db.execute("SELECT 1 FROM levels WHERE level=? AND enabled=1",(required_player_level,)).fetchone(): raise HTTPException(400,"Choose an enabled player level.")
        if not db.execute("SELECT 1 FROM fish_species WHERE fish_key=? AND enabled=1",(fish_key,)).fetchone(): raise HTTPException(400,"Choose an enabled fish species.")
        try: db.execute("INSERT INTO pond_catalog VALUES (?,?,?,?,?,?,?,?,?,?,1)",(pond_level,clean,icon.strip()[:12] or '💧',required_player_level,cost,land_blocks,sack_capacity,fish_per_sack,growth_hours*3600,fish_key))
        except sqlite3.IntegrityError: raise HTTPException(409,"That pond level already exists.")
    return RedirectResponse('/admin#fishery',303)


@app.post("/admin/fish/species/{fish_key}")
def edit_fish_species(request: Request, fish_key: str, name: str=Form(...), icon: str=Form("🐟"),
    product_name: str=Form(...), product_icon: str=Form("🐟"), product_size: float=Form(...),
    sale_price: int=Form(...), enabled: bool=Form(False)):
    require_admin(request); clean=" ".join(name.split()); product=" ".join(product_name.split())
    if len(clean)<2 or len(product)<2 or product_size<=0 or sale_price<1: raise HTTPException(400,"Enter valid fish details.")
    with connection() as db:
        result=db.execute("""UPDATE fish_species SET name=?,icon=?,product_name=?,product_icon=?,product_size=?,sale_price=?,enabled=?
            WHERE fish_key=?""",(clean,icon.strip()[:12] or '🐟',product,product_icon.strip()[:12] or '🐟',product_size,sale_price,1 if enabled else 0,fish_key))
        if not result.rowcount: raise HTTPException(404,"Fish species not found.")
    return RedirectResponse('/admin#fishery',303)


@app.post("/admin/fish/seeds/{seed_key}")
def edit_fish_seed(request: Request, seed_key: str, fish_key: str=Form(...), name: str=Form(...), icon: str=Form("🫘"),
    pack_size: float=Form(...), pack_price: int=Form(...), seeds_per_sack: int=Form(...), enabled: bool=Form(False)):
    require_admin(request); clean=" ".join(name.split())
    if len(clean)<2 or pack_size<=0 or pack_price<0 or seeds_per_sack<1: raise HTTPException(400,"Enter valid seed-sack details.")
    with connection() as db:
        if not db.execute("SELECT 1 FROM fish_species WHERE fish_key=?",(fish_key,)).fetchone(): raise HTTPException(400,"Fish species not found.")
        result=db.execute("""UPDATE fish_seeds SET fish_key=?,name=?,icon=?,pack_size=?,pack_price=?,seeds_per_sack=?,enabled=?
            WHERE seed_key=?""",(fish_key,clean,icon.strip()[:12] or '🫘',pack_size,pack_price,seeds_per_sack,1 if enabled else 0,seed_key))
        if not result.rowcount: raise HTTPException(404,"Fish-seed product not found.")
    return RedirectResponse('/admin#fishery',303)


@app.post("/admin/fish/ponds/{pond_level}")
def edit_pond_level(request: Request, pond_level: int, name: str=Form(...), icon: str=Form("💧"),
    required_player_level: int=Form(...), cost: int=Form(...), land_blocks: int=Form(...), sack_capacity: int=Form(...),
    fish_per_sack: int=Form(...), growth_hours: int=Form(...), fish_key: str=Form(...), enabled: bool=Form(False)):
    require_admin(request); clean=" ".join(name.split())
    if len(clean)<2 or cost<0 or min(land_blocks,sack_capacity,fish_per_sack,growth_hours)<1: raise HTTPException(400,"Enter valid pond-level details.")
    with connection() as db:
        if not db.execute("SELECT 1 FROM levels WHERE level=? AND enabled=1",(required_player_level,)).fetchone(): raise HTTPException(400,"Choose an enabled player level.")
        if not db.execute("SELECT 1 FROM fish_species WHERE fish_key=?",(fish_key,)).fetchone(): raise HTTPException(400,"Fish species not found.")
        result=db.execute("""UPDATE pond_catalog SET name=?,icon=?,required_player_level=?,cost=?,land_blocks=?,sack_capacity=?,
            fish_per_sack=?,growth_seconds=?,fish_key=?,enabled=? WHERE pond_level=?""",
            (clean,icon.strip()[:12] or '💧',required_player_level,cost,land_blocks,sack_capacity,fish_per_sack,growth_hours*3600,fish_key,1 if enabled else 0,pond_level))
        if not result.rowcount: raise HTTPException(404,"Pond level not found.")
    return RedirectResponse('/admin#fishery',303)
