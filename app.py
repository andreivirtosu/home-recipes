#!/usr/bin/env python3
"""Tiny SQLite-backed Home Recipes MVP.

No framework yet: this keeps deployment simple on the existing VPS while proving
browse + add + persistence. Later we can replace it with FastAPI/Next.js without
changing the product model.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import mimetypes
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("HOME_RECIPES_DB", ROOT / "data" / "home_recipes.sqlite3"))
UPLOAD_DIR = Path(os.environ.get("HOME_RECIPES_UPLOAD_DIR", DB_PATH.parent / "uploads"))
PORT = int(os.environ.get("PORT", "8000"))
SESSION_SECRET = os.environ.get("HOME_RECIPES_SESSION_SECRET", "dev-home-recipes-session-secret-change-me")
SESSION_MAX_AGE = 60 * 60 * 24 * 30
ACCOUNTS = {
    "andrei": "andrei",
}

RICH_CHOCOLATE_DESCRIPTION = """Rich Häagen-Dazs-style chocolate ice cream adapted for the CubeItaly 750 ml machine. Make one 1200 g aged base, then churn as two separate 600 g batches so the machine is not overloaded.

Target: premium, dense, adult chocolate; high chocolate intensity but less pasty than the original high-SMP version. Total base is about 1200 g: 2 x 600 g churns.

Steps:
1. Dry-mix cocoa powder, sugar, dextrose, skimmed milk powder, salt, and optional guar gum very thoroughly.
2. Warm the milk to 40-50°C.
3. Whisk or stick-blend the dry mix into the warm milk gradually so there are no cocoa/SMP lumps.
4. Heat to 82-85°C while stirring. Hold briefly only long enough to hydrate the powders/stabilizer.
5. Remove from heat. Add the chopped Callebaut 70.5% chocolate and blend until smooth, glossy, and fully emulsified.
6. Add the 35% cream while the base is still warm; blend briefly again.
7. Chill quickly in an ice bath, then refrigerate 8-12 hours.
8. Before churning, inspect the cold base. Chocolate bases often thicken/gel after aging, so stick-blend cold until smooth.
9. Weigh 600 g into the CubeItaly and churn. Keep the remaining 600 g fridge-cold while the first batch churns.
10. Extract to a pre-chilled container, harden in the freezer, then churn the second 600 g portion.

Notes: salt is important for chocolate depth. Keep guar low: chocolate and cocoa already provide body. If the base looks separated or grainy after aging, re-blend; gently rewarm/reblend only if cold blending does not fix it."""

SOURDOUGH_DESCRIPTION = """Family sourdough bread formula from the handwritten notes, kept as the current normal recipe. Inspired by The Perfect Loaf simple weekday method, but using the handwritten 40g fridge-starter routine and 70% hydration bake formula.

Baker percentages:
- Total flour: 900g = 100%
- Total water: 630g = 70%
- Salt: 16g = 1.8%
- Starter inoculation: 16g = 1.8%
- Levain: 180g total = 20% of flour weight
- Prefermented flour: 82g = 9.1% of total flour
- Total dough: about 1560g, close to the handwritten ~1554g note depending on starter rounding

Starter maintenance for 2 bakes/week:
1. Keep 40g starter in the fridge.
2. For each bake, take 20g out to build the levain.
3. Refresh the remaining starter: 20g starter + 20g flour + 20g water = 60g.
4. Let refreshed starter rest at room temperature for 30-60 min.
5. Put 40g back in the fridge for the next bake. Use/discard the extra 20g as needed.

Method:
1. Build levain: mix 82g flour + 82g water + 16g starter = 180g levain. Let rise until active, bubbly, and domed.
2. Autolyse: mix 818g flour + 490g water until no dry flour remains. Rest 30-60 min.
3. Final mix: add all 180g levain, 50g additional water, and 16g salt. Mix until incorporated and moderately strengthened.
4. Bulk ferment until airy and expanded, with stretch-and-folds during the first half of bulk. Use the dough condition rather than the clock.
5. Divide and preshape if making two smaller loaves, or keep as one large loaf if your basket/oven can handle it. Rest 20-30 min.
6. Shape, place in banneton, then cold proof overnight.
7. Bake from cold in a hot covered pot or with steam: about 230°C, 20 min covered/with steam, then 25-35 min uncovered until deep brown and about 95°C internal.
8. Cool at least 2 hours before slicing.

Proofing note: if the cold loaf looks tight/dense, give it 30-60 min at room temperature while the oven preheats. If already puffy/jiggly, bake straight from the fridge."""

SEED_RECIPES = [
    ("Rich chocolate ice cream", "Ice cream", RICH_CHOCOLATE_DESCRIPTION, "CubeItaly,chocolate,adult,2 batches", "Experiment", "chocolate", ""),
    ("Kid-friendly chocolate gelato", "Gelato", "A softer, family-friendly chocolate profile to compare against richer adult batches.", "CubeItaly,chocolate,kids", "Experiment", "chocolate", ""),
    ("Pistachio Sicilian-style gelato", "Gelato", "The flagship iteration target: clean formula, batch notes, and next tweaks.", "CubeItaly,pistachio,best-version", "Best version", "pistachio", "8.5"),
    ("Adult Greek frozen yogurt", "Frozen yogurt", "Tangy adult profile with texture and sweetness notes to dial in.", "CubeItaly,yogurt,adult", "Experiment", "yogurt", ""),
    ("Banana milk gelato", "Gelato", "Fresh banana process and formulation target for small-machine batches.", "CubeItaly,banana,fruit", "Experiment", "banana", ""),
    ("Simple weekday sourdough bread", "Bread", SOURDOUGH_DESCRIPTION, "sourdough,bread,The Perfect Loaf,weekday", "Favorite", "", ""),
]

CSS = r"""
:root{
  --bg:#fffdf9;
  --paper:#ffffff;
  --paper-soft:#fbf7ef;
  --ink:#22352d;
  --text:#3f443f;
  --muted:#777b73;
  --soft:#a09d95;
  --line:#e9e2d8;
  --accent:#d66f55;
  --accent-dark:#bd5a42;
  --sage:#6f8b78;
  --sage-soft:#eef4ef;
  --cream:#f6efe4;
  --shadow:0 10px 28px rgba(37,48,42,.07);
  --radius:14px;
  --display:ui-rounded,"SF Pro Rounded","Avenir Next Rounded","Nunito",ui-sans-serif,system-ui,sans-serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;
  font-family:ui-sans-serif,-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;
  color:var(--text);
  background:var(--bg);
  min-height:100vh;
  -webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility;
}
a{color:inherit;text-decoration:none}
.shell{width:min(1080px,calc(100% - 40px));margin:0 auto}
header{
  position:sticky;top:0;z-index:10;
  padding:16px 0;
  background:rgba(255,253,249,.92);
  backdrop-filter:blur(14px);
  border-bottom:1px solid rgba(233,226,216,.7);
  display:flex;align-items:center;justify-content:space-between;gap:24px;
}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;color:var(--sage);font-family:var(--display);font-size:18px}
.mark{width:34px;height:34px;border-radius:10px;background:var(--accent);display:grid;place-items:center;color:white;font-size:17px}
nav{display:flex;gap:4px;color:var(--muted);font-size:14px;font-weight:650;align-items:center}
nav a,.nav-user{padding:9px 11px;border-radius:10px}
nav a:hover{background:var(--sage-soft);color:var(--ink)}
.nav-user{background:var(--sage-soft);color:var(--sage);font-weight:750}
.login-shell{min-height:100vh;display:grid;place-items:center;padding:28px;background:#fff}
.login-card{width:min(420px,100%);padding:8px;text-align:left;background:transparent;border:0;box-shadow:none}
.login-card .brand{justify-content:center;margin-bottom:24px}
.login-card h1{font-family:var(--display);font-size:38px;line-height:1.08;margin:0 0 10px;color:var(--sage);text-align:center;letter-spacing:-.03em}
.login-card .lead{font-size:15px;line-height:1.55;text-align:center;color:var(--muted);margin:0 auto 24px;max-width:320px}
.login-form{display:grid;gap:12px;margin-top:20px}
.login-error{margin:14px 0 0;color:var(--accent-dark);font-weight:700;text-align:center}
.hero{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:34px;align-items:center;padding:48px 0 32px}
.eyebrow{display:inline-flex;gap:8px;align-items:center;padding:7px 10px;border-radius:10px;background:var(--sage-soft);color:var(--sage);font-weight:750;font-size:13px}
h1{margin:18px 0 14px;font-family:var(--display);font-weight:800;font-size:clamp(38px,5vw,64px);line-height:1.04;letter-spacing:-.045em;color:var(--ink);max-width:720px;text-wrap:balance}
.lead{margin:0;color:var(--muted);font-size:clamp(16px,1.45vw,18px);line-height:1.65;max-width:600px;text-wrap:pretty}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:24px}.button,button{border:1px solid transparent;border-radius:10px;min-height:44px;padding:11px 15px;font-weight:750;display:inline-flex;align-items:center;justify-content:center;gap:8px;cursor:pointer;font:inherit;transition:background .15s,border-color .15s,transform .15s}.button:hover,button:hover{transform:translateY(-1px)}.primary{background:var(--accent);color:white}.primary:hover{background:var(--accent-dark)}.secondary{background:#fff;border-color:var(--line);color:var(--ink)}
.app-card{border:1px solid var(--line);background:#fff;border-radius:18px;padding:14px;box-shadow:var(--shadow);overflow:hidden}
.toolbar{display:flex;justify-content:space-between;align-items:center;padding:6px 4px 12px}.dots{display:flex;gap:6px}.dots span{width:9px;height:9px;border-radius:50%;background:#e2d8cc}.status{color:var(--soft);font-size:13px;font-weight:650}
.section{padding:30px 0}.section-head{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:16px}.section h2{margin:0;font-family:var(--display);font-weight:800;font-size:clamp(28px,3.2vw,40px);line-height:1.08;letter-spacing:-.035em;color:var(--ink);text-wrap:balance}.section .sub{color:var(--muted);max-width:570px;line-height:1.6;text-wrap:pretty}
.library-tools{display:grid;grid-template-columns:1fr auto;gap:12px;margin:0 0 18px}.search{border:1px solid var(--line);background:#fff;border-radius:12px;padding:13px 14px;font:inherit;color:var(--ink)}.search::placeholder,input::placeholder,textarea::placeholder{color:#aaa49b}.filter-note{align-self:center;color:var(--muted);font-size:14px}.library-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.recipe-card{overflow:hidden;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:none;transition:border-color .15s,transform .15s,box-shadow .15s}.recipe-card:hover{transform:translateY(-1px);box-shadow:var(--shadow);border-color:#ded4c7}.recipe-card.add-card{display:grid;place-items:center;min-height:286px;border-style:dashed;background:var(--paper-soft)}.add-card-inner{text-align:center;padding:24px}.plus{width:44px;height:44px;border-radius:12px;background:var(--accent);color:white;display:grid;place-items:center;margin:0 auto 14px;font-size:24px}
.thumb{height:118px;background:linear-gradient(135deg,#f5e9db,#fbf5e9);position:relative;border-bottom:1px solid var(--line)}.thumb:after{content:"";position:absolute;inset:26px 58px;border-radius:999px;background:#fff8eb;box-shadow:0 8px 18px rgba(64,42,24,.08)}.thumb:before{content:"";position:absolute;left:20px;bottom:16px;width:54px;height:8px;border-radius:999px;background:rgba(255,255,255,.55)}.thumb.chocolate{background:linear-gradient(135deg,#493229,#a96b50)}.thumb.pistachio{background:linear-gradient(135deg,#7d9a6d,#e8dfb7)}.thumb.banana{background:linear-gradient(135deg,#e3c95d,#fff0b5)}.thumb.yogurt{background:linear-gradient(135deg,#d5e2e4,#fffaf0)}.photo-thumb{padding:0;background:#f7f3ec}.photo-thumb img{display:block;width:100%;height:118px;object-fit:cover}.detail-photo.photo-thumb img{height:100%;min-height:220px}.photo-note{margin:4px 0 0;color:var(--soft);font-size:12px;line-height:1.4}
.recipe-card-body{padding:16px}.recipe-card h3{margin:0 0 8px;font-family:var(--display);font-size:20px;line-height:1.2;letter-spacing:-.025em;color:var(--ink);text-wrap:balance}.recipe-card p{margin:0 0 13px;color:var(--muted);line-height:1.5;font-size:14.5px}.ingredient-list{list-style:none;margin:0 0 14px;padding:10px 0 0;border-top:1px solid var(--line);display:grid;gap:6px}.ingredient-list li{font-size:13px;line-height:1.35;color:#4b514c;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ingredient-list .more{color:var(--soft);font-weight:700}.card-meta{display:flex;flex-wrap:wrap;gap:6px}.mini-pill{padding:5px 8px;border-radius:999px;background:var(--sage-soft);color:var(--sage);font-size:11.5px;font-weight:750;letter-spacing:.005em}
.ingredient-shelf{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.product-card{border:1px solid var(--line);border-radius:16px;background:#fff;padding:16px}.product-kind{display:inline-block;margin-bottom:16px;color:var(--accent-dark);font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}.product-card h3{margin:0 0 8px;color:var(--ink);font-family:var(--display);font-size:19px;line-height:1.22;letter-spacing:-.025em}.product-card p{margin:0 0 14px;color:var(--muted);font-size:14px;line-height:1.48}
.form-card{border:1px solid var(--line);border-radius:18px;background:#fff;box-shadow:none;padding:20px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:grid;gap:7px;color:#5f635e;font-size:13px;font-weight:750}input,textarea,select{width:100%;border:1px solid var(--line);background:#fff;border-radius:10px;padding:12px 13px;font:inherit;font-weight:480;color:var(--ink);outline:none}input:focus,textarea:focus,select:focus{border-color:#d7a18f;box-shadow:0 0 0 3px rgba(214,111,85,.13)}textarea{min-height:94px;resize:vertical}.full{grid-column:1/-1}.notice{margin:14px 0 0;color:var(--accent-dark);font-weight:720}
.feature-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.feature{border:1px solid var(--line);border-radius:16px;background:#fff;padding:20px;min-height:150px}.feature .icon{font-size:22px;margin-bottom:16px}.feature h3{margin:0 0 8px;font-family:var(--display);font-size:20px;letter-spacing:-.025em;color:var(--ink)}.feature p{margin:0;color:var(--muted);line-height:1.52}
.recipe-detail{padding:30px 0 56px}.back-link{display:inline-flex;margin:0 0 16px;color:var(--muted);font-weight:700}.detail-hero{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:24px;align-items:stretch;border:1px solid var(--line);border-radius:18px;background:#fff;padding:20px}.detail-hero h1{margin-top:16px}.detail-summary{font-size:17px;line-height:1.65;color:var(--muted);max-width:760px;text-wrap:pretty}.detail-photo{height:auto;min-height:220px;border-radius:14px;overflow:hidden;border:0}.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}.detail-grid.single{grid-template-columns:1fr}.detail-panel{border:1px solid var(--line);border-radius:16px;background:#fff;padding:20px}.detail-panel h2{margin:0 0 12px;font-family:var(--display);font-size:28px;font-weight:800;letter-spacing:-.03em;color:var(--ink)}.detail-panel p{margin:0;color:var(--text);font-size:16px;line-height:1.7;white-space:pre-wrap}.detail-ingredients{margin:0;padding-left:20px;display:grid;gap:10px;color:var(--text);line-height:1.5}footer{padding:34px 0;color:var(--soft);font-size:14px}
@media(max-width:900px){
  body{overflow-x:hidden}
  .shell{width:min(100% - 28px,1080px)}
  header{position:relative;align-items:flex-start;flex-direction:column;gap:10px;padding:14px 0}
  nav{display:flex;flex-wrap:wrap;gap:6px;width:100%;font-size:14px}
  nav a,.nav-user{min-height:44px;display:inline-flex;align-items:center;padding:10px 12px;background:#fff;border:1px solid var(--line)}
  .nav-user{background:var(--sage-soft);border-color:transparent}
  .hero,.detail-hero,.detail-grid{grid-template-columns:1fr}
  .hero{padding:26px 0 18px;gap:18px}
  h1{font-size:clamp(34px,10vw,46px);line-height:1.06;margin:14px 0 10px}
  .lead,.detail-summary{font-size:16px;line-height:1.55}
  .actions{gap:8px;margin-top:18px}.button,button{min-height:48px;padding:12px 14px;border-radius:12px;flex:1 1 140px}
  .app-card{display:none}
  .section{padding:22px 0}.section-head{display:block;margin-bottom:12px}.section h2{font-size:30px}.section .sub{font-size:15px;line-height:1.55}
  .library-tools,.form-grid{grid-template-columns:1fr;gap:10px}.search,input,textarea,select{font-size:16px;min-height:48px}.filter-note{font-size:13px}
  .library-grid,.feature-grid,.ingredient-shelf{grid-template-columns:1fr;gap:10px}
  .recipe-card:not(.add-card){display:grid;grid-template-columns:96px minmax(0,1fr);min-height:116px}
  .recipe-card:not(.add-card) .thumb{height:100%;min-height:116px;border-bottom:0;border-right:1px solid var(--line)}
  .recipe-card:not(.add-card) .photo-thumb img{height:100%;min-height:116px}
  .thumb:after{inset:30px 18px}.thumb:before{left:18px;bottom:18px;width:42px}
  .recipe-card-body{padding:12px;min-width:0}.recipe-card h3{font-size:17px;margin-bottom:6px}.recipe-card p{font-size:13.5px;line-height:1.38;margin-bottom:8px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.ingredient-list{display:none}.mini-pill{font-size:11px;padding:4px 7px}
  .recipe-card.add-card{min-height:116px}.add-card-inner{padding:18px}.plus{width:38px;height:38px;margin-bottom:10px}
  .product-card,.feature,.form-card,.detail-panel,.detail-hero{border-radius:14px;padding:14px}
  .product-card h3,.feature h3{font-size:18px}.product-card p,.feature p{font-size:14px}
  .recipe-detail{padding:20px 0 42px}.back-link{min-height:44px;align-items:center;margin-bottom:8px}.detail-hero{gap:14px}.detail-hero h1{font-size:34px}.detail-photo{min-height:180px}.detail-photo.photo-thumb img{min-height:180px}.detail-panel h2{font-size:24px}.detail-panel p,.detail-ingredients{font-size:15.5px;line-height:1.6}.detail-ingredients{padding-left:18px;overflow-wrap:anywhere}
  label{font-size:13px}textarea{min-height:120px}.full{grid-column:auto}.photo-note{font-size:12px}.login-shell{padding:22px}.login-card{width:min(100%,390px)}.login-card h1{font-size:34px}
}
@media(max-width:380px){
  .shell{width:min(100% - 20px,1080px)}
  nav a,.nav-user{font-size:13px;padding:9px 10px}
  .recipe-card:not(.add-card){grid-template-columns:82px minmax(0,1fr)}
  .recipe-card:not(.add-card) .thumb,.recipe-card:not(.add-card) .photo-thumb img{min-height:110px}
  .card-meta{gap:4px}.mini-pill{font-size:10.5px}
  .button,button{flex-basis:100%}
}
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def seed_ingredients(title: str) -> str:
    seeds = {
        "Pistachio Sicilian-style gelato": "390g Migros Bio Vollmilch 3.5%\n72g sugar\n24g dextrose\n72g 100% pistachio paste\n0.6g fine sea salt",
        "Rich chocolate ice cream": "For 2 x 600g CubeItaly batches / ~1200g total base:\n500g cream 35% → 250g per churn\n297g whole milk 3.5% → 148.5g per churn\n130g sugar → 65g per churn\n70g dextrose → 35g per churn\n55g → Cacao Barry Extra Brute cocoa powder → 27.5g per churn\n115g → Callebaut 70.5% dark chocolate → 57.5g per churn\n30g skimmed milk powder → 15g per churn\n1.5g fine sea salt → 0.75g per churn\nOptional: 0.6-0.8g guar gum total → 0.3-0.4g per churn",
        "Kid-friendly chocolate gelato": "Whole milk\nCream\nCocoa powder\nChocolate\nSugar + dextrose",
        "Adult Greek frozen yogurt": "Fage 5% Greek yogurt\nWhole milk\nCream\nSugar + dextrose\nLemon or salt if needed",
        "Banana milk gelato": "Very ripe banana\nWhole milk\nCream\nSugar + dextrose\nFine sea salt",
        "Simple weekday sourdough bread": "Starter maintenance: keep 40g starter in fridge; take 20g out for levain; refresh remaining 20g starter + 20g flour + 20g water = 60g; rest 30-60 min; return 40g to fridge\nLevain: 82g flour + 82g water + 16g starter = 180g\nAutolyse: 818g flour + 490g water\nFinal mix: all 180g levain + 50g water + 16g salt\nTotal formula: 900g flour, 630g water, 16g salt, 16g starter\nBaker percentages: 70% hydration, 1.8% salt, 9.1% prefermented flour\nYield: about 1560g total dough",
    }
    return seeds.get(title, "")


def init_db() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS recipes (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              title TEXT NOT NULL UNIQUE,
              category TEXT NOT NULL DEFAULT '',
              summary TEXT NOT NULL DEFAULT '',
              ingredients TEXT NOT NULL DEFAULT '',
              tags TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'Experiment',
              color TEXT NOT NULL DEFAULT '',
              rating TEXT NOT NULL DEFAULT '',
              cover_photo TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        existing_cols = {row[1] for row in con.execute("PRAGMA table_info(recipes)")}
        if "ingredients" not in existing_cols:
            con.execute("ALTER TABLE recipes ADD COLUMN ingredients TEXT NOT NULL DEFAULT ''")
        if "cover_photo" not in existing_cols:
            con.execute("ALTER TABLE recipes ADD COLUMN cover_photo TEXT NOT NULL DEFAULT ''")

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS batches (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
              made_on TEXT NOT NULL,
              rating TEXT NOT NULL DEFAULT '',
              result_notes TEXT NOT NULL DEFAULT '',
              next_tweak TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL
            )
            """
        )
        now = datetime.now(timezone.utc).isoformat()
        for title, category, summary, tags, status, color, rating in SEED_RECIPES:
            con.execute(
                """
                INSERT OR IGNORE INTO recipes
                (title, category, summary, ingredients, tags, status, color, rating, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (title, category, summary, seed_ingredients(title), tags, status, color, rating, now, now),
            )
            con.execute(
                "UPDATE recipes SET ingredients = ? WHERE title = ? AND ingredients = ''",
                (seed_ingredients(title), title),
            )


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def sign_session(username: str, issued_at: int) -> str:
    payload = f"{username}|{issued_at}"
    signature = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}|{signature}"


def verify_session(token: str) -> str | None:
    parts = token.split("|")
    if len(parts) != 3:
        return None
    username, issued_raw, signature = parts
    if username not in ACCOUNTS:
        return None
    try:
        issued_at = int(issued_raw)
    except ValueError:
        return None
    if time.time() - issued_at > SESSION_MAX_AGE:
        return None
    expected = hmac.new(SESSION_SECRET.encode(), f"{username}|{issued_at}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return username


def make_session_cookie(username: str) -> str:
    token = sign_session(username, int(time.time()))
    return f"home_recipes_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_MAX_AGE}"


def clear_session_cookie() -> str:
    return "home_recipes_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"


def current_user(headers) -> str | None:
    cookie_header = headers.get("Cookie", "")
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    morsel = cookie.get("home_recipes_session")
    if not morsel:
        return None
    return verify_session(morsel.value)


def authenticate(fields: dict[str, str]) -> str | None:
    username = fields.get("username", "").strip().lower()
    password = fields.get("password", "")
    if ACCOUNTS.get(username) == password:
        return username
    return None


def get_recipes() -> list[sqlite3.Row]:
    with connect() as con:
        return list(con.execute("SELECT * FROM recipes ORDER BY updated_at DESC, title ASC"))


def get_recipe(recipe_id: int) -> sqlite3.Row | None:
    with connect() as con:
        return con.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()


def recipe_fields(fields: dict[str, str]) -> tuple[str, str, str, str, str, str, str, str] | str:
    title = fields.get("title", "").strip()
    if not title:
        return "Title is required."
    category = fields.get("category", "").strip() or "Uncategorized"
    summary = fields.get("summary", "").strip()
    ingredients = fields.get("ingredients", "").strip()
    tags = fields.get("tags", "").strip()
    status = fields.get("status", "Experiment").strip() or "Experiment"
    color = fields.get("color", "").strip()
    rating = fields.get("rating", "").strip()
    return title, category, summary, ingredients, tags, status, color, rating


def create_recipe(fields: dict[str, str]) -> str | None:
    values = recipe_fields(fields)
    if isinstance(values, str):
        return values
    title, category, summary, ingredients, tags, status, color, rating = values
    now = datetime.now(timezone.utc).isoformat()
    try:
        with connect() as con:
            con.execute(
                """
                INSERT INTO recipes
                (title, category, summary, ingredients, tags, status, color, rating, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (title, category, summary, ingredients, tags, status, color, rating, now, now),
            )
    except sqlite3.IntegrityError:
        return "A recipe with that title already exists."
    return None


def update_recipe(recipe_id: int, fields: dict[str, str], cover_photo: str = "") -> str | None:
    values = recipe_fields(fields)
    if isinstance(values, str):
        return values
    title, category, summary, ingredients, tags, status, color, rating = values
    now = datetime.now(timezone.utc).isoformat()
    photo_sql = ", cover_photo = ?" if cover_photo else ""
    params = [title, category, summary, ingredients, tags, status, color, rating, now]
    if cover_photo:
        params.append(cover_photo)
    params.append(recipe_id)
    try:
        with connect() as con:
            cur = con.execute(
                f"""
                UPDATE recipes
                SET title = ?, category = ?, summary = ?, ingredients = ?, tags = ?, status = ?, color = ?, rating = ?, updated_at = ?{photo_sql}
                WHERE id = ?
                """,
                params,
            )
            if cur.rowcount == 0:
                return "Recipe not found."
    except sqlite3.IntegrityError:
        return "A recipe with that title already exists."
    return None


def save_recipe_photo(file_item) -> str:
    if not file_item or not getattr(file_item, "filename", ""):
        return ""
    content_type = (getattr(file_item, "type", "") or "").lower()
    allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
    suffix = allowed.get(content_type)
    if not suffix:
        original = Path(file_item.filename).suffix.lower()
        suffix = original if original in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else ".jpg"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"recipe-{uuid.uuid4().hex}{suffix}"
    target = UPLOAD_DIR / filename
    target.write_bytes(file_item.data)
    return f"/uploads/{filename}"


def preview_text(value: object, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def intro_text(value: object, limit: int = 260) -> str:
    raw = str(value or "").strip()
    first_paragraph = raw.split("\n\n", 1)[0].strip()
    return preview_text(first_paragraph, limit)


def normalized_text(value: object) -> str:
    return " ".join(str(value or "").split())


def render_recipe_card(recipe: sqlite3.Row) -> str:
    tags = [t.strip() for t in str(recipe["tags"] or "").split(",") if t.strip()]
    pills = [recipe["category"], recipe["status"]] + tags[:2]
    if recipe["rating"]:
        pills.insert(0, f"★ {recipe['rating']}")
    pill_html = "".join(f'<span class="mini-pill">{esc(p)}</span>' for p in pills if p)
    ingredient_lines = [line.strip() for line in str(recipe["ingredients"] or "").splitlines() if line.strip()]
    ingredient_html = ""
    if ingredient_lines:
        items = "".join(f"<li>{esc(line)}</li>" for line in ingredient_lines[:3])
        more = f"<li class='more'>+{len(ingredient_lines) - 3} more</li>" if len(ingredient_lines) > 3 else ""
        ingredient_html = f"<ul class='ingredient-list'>{items}{more}</ul>"
    color = esc(recipe["color"])
    photo = esc(recipe["cover_photo"] if "cover_photo" in recipe.keys() else "")
    thumb_html = f'<div class="thumb photo-thumb"><img src="{photo}" alt="{esc(recipe["title"])} photo" loading="lazy" /></div>' if photo else f'<div class="thumb {color}"></div>'
    searchable = esc(" ".join([recipe["title"], recipe["category"], recipe["summary"], recipe["ingredients"], recipe["tags"], recipe["status"]]).lower())
    return f"""
      <a class="recipe-card" href="/recipes/{recipe['id']}" data-recipe-card data-search="{searchable}">
        {thumb_html}
        <div class="recipe-card-body">
          <h3>{esc(recipe['title'])}</h3>
          <p>{esc(preview_text(recipe['summary'])) or 'No notes yet. Add the first result next.'}</p>
          {ingredient_html}
          <div class="card-meta">{pill_html}</div>
        </div>
      </a>
    """


def recipe_detail_page(username: str, recipe: sqlite3.Row) -> bytes:
    tags = [t.strip() for t in str(recipe["tags"] or "").split(",") if t.strip()]
    pills = [recipe["category"], recipe["status"]] + tags
    if recipe["rating"]:
        pills.insert(0, f"★ {recipe['rating']}")
    pill_html = "".join(f'<span class="mini-pill">{esc(p)}</span>' for p in pills if p)
    ingredient_lines = [line.strip() for line in str(recipe["ingredients"] or "").splitlines() if line.strip()]
    ingredient_html = "".join(f"<li>{esc(line)}</li>" for line in ingredient_lines) or "<li>No ingredients recorded yet.</li>"
    summary_plain = str(recipe["summary"] or "").strip()
    hero_summary_plain = intro_text(summary_plain, 260)
    hero_summary = esc(hero_summary_plain) or "No short description recorded yet."
    full_description = ""
    if summary_plain and normalized_text(summary_plain) != normalized_text(hero_summary_plain):
        full_description = f"""
        <article class="detail-panel">
          <h2>Full description</h2>
          <p>{esc(summary_plain)}</p>
        </article>"""
    grid_class = "" if full_description else " single"
    color = esc(recipe["color"])
    photo = esc(recipe["cover_photo"] if "cover_photo" in recipe.keys() else "")
    detail_photo = f'<div class="detail-photo thumb photo-thumb"><img src="{photo}" alt="{esc(recipe["title"])} photo" /></div>' if photo else f'<div class="detail-photo thumb {color}"></div>'
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(recipe['title'])} · Home Recipes</title>
  <style>{CSS}</style>
</head>
<body>
  <header class="shell">
    <a class="brand" href="/" aria-label="Home Recipes home"><span class="mark">✦</span><span>Home Recipes</span></a>
    <nav><a href="/#library">Library</a><a href="/#ingredients">Ingredients</a><a href="/#add">Add recipe</a><span class="nav-user">{esc(username)}</span><a href="/logout">Log out</a></nav>
  </header>
  <main class="shell">
    <section class="recipe-detail">
      <a class="back-link" href="/#library">← Back to recipes</a>
      <div class="detail-hero">
        <div>
          <div class="card-meta">{pill_html}</div>
          <h1>{esc(recipe['title'])}</h1>
          <p class="detail-summary">{hero_summary}</p>
          <div class="actions"><a class="button primary" href="/recipes/{recipe['id']}/edit">Edit recipe</a><a class="button secondary" href="/#library">Back to library</a></div>
        </div>
        {detail_photo}
      </div>
      <div class="detail-grid{grid_class}">
        {full_description}
        <article class="detail-panel">
          <h2>Ingredients / product references</h2>
          <ul class="detail-ingredients">{ingredient_html}</ul>
        </article>
      </div>
    </section>
  </main>
  <footer class="shell">Home Recipes · a private kitchen notebook for recipes, products, photos, and results.</footer>
</body>
</html>"""
    return html_doc.encode("utf-8")


def option(value: str, label: str, current: str) -> str:
    selected = " selected" if value == current else ""
    return f'<option value="{esc(value)}"{selected}>{esc(label)}</option>'


def edit_recipe_page(username: str, recipe: sqlite3.Row, message: str = "") -> bytes:
    notice = f'<p class="notice">{esc(message)}</p>' if message else ""
    status_options = "".join(option(v, v, recipe["status"]) for v in ["Experiment", "Best version", "Needs tweak", "Favorite"])
    color_options = "".join(option(v, label, recipe["color"]) for v, label in [("", "Neutral"), ("chocolate", "Chocolate"), ("pistachio", "Pistachio"), ("banana", "Banana"), ("yogurt", "Yogurt")])
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Edit {esc(recipe['title'])} · Home Recipes</title>
  <style>{CSS}</style>
</head>
<body>
  <header class="shell">
    <a class="brand" href="/" aria-label="Home Recipes home"><span class="mark">✦</span><span>Home Recipes</span></a>
    <nav><a href="/#library">Library</a><span class="nav-user">{esc(username)}</span><a href="/logout">Log out</a></nav>
  </header>
  <main class="shell">
    <section class="section">
      <a class="back-link" href="/recipes/{recipe['id']}">← Back to recipe</a>
      <div class="section-head"><h2>Edit recipe.</h2><p class="sub">Update the family recipe description, ingredients, rating, and status.</p></div>
      <form class="form-card" method="post" action="/recipes/{recipe['id']}/edit" enctype="multipart/form-data">
        <div class="form-grid">
          <label>Title<input name="title" required value="{esc(recipe['title'])}" /></label>
          <label>Category<input name="category" value="{esc(recipe['category'])}" /></label>
          <label class="full">Summary<textarea name="summary">{esc(recipe['summary'])}</textarea></label>
          <label class="full">Ingredient references / quantities<textarea name="ingredients">{esc(recipe['ingredients'])}</textarea></label>
          <label>Tags<input name="tags" value="{esc(recipe['tags'])}" /></label>
          <label>Status<select name="status">{status_options}</select></label>
          <label>Rating<input name="rating" value="{esc(recipe['rating'])}" /></label>
          <label>Color<select name="color">{color_options}</select></label>
          <label class="full">Recipe photo<input name="cover_photo" type="file" accept="image/*" /><span class="photo-note">Optional: upload or replace the recipe cover photo.</span></label>
        </div>
        <div class="actions"><button class="primary" type="submit">Save changes</button><a class="button secondary" href="/recipes/{recipe['id']}">Cancel</a></div>
        {notice}
      </form>
    </section>
  </main>
</body>
</html>"""
    return html_doc.encode("utf-8")


def page(username: str, message: str = "") -> bytes:
    recipes = get_recipes()
    recipe_cards = "\n".join(render_recipe_card(r) for r in recipes)
    notice = f'<p class="notice">{esc(message)}</p>' if message else ""
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Home Recipes</title>
  <meta name="description" content="A personal recipe lab for recipes, batches, photos, and results." />
  <style>{CSS}</style>
</head>
<body>
  <header class="shell">
    <a class="brand" href="/" aria-label="Home Recipes home"><span class="mark">✦</span><span>Home Recipes</span></a>
    <nav><a href="#library">Library</a><a href="#ingredients">Ingredients</a><a href="#add">Add recipe</a><a href="#features">Features</a><span class="nav-user">{esc(username)}</span><a href="/logout">Log out</a></nav>
  </header>

  <main class="shell">
    <section class="hero">
      <div>
        <div class="eyebrow">Personal recipe library · {len(recipes)} recipes</div>
        <h1>Browse, save, and improve your recipes.</h1>
        <p class="lead">Keep a clean recipe collection, add new ideas quickly, and build toward result logs, photos, and next-time tweaks.</p>
        <div class="actions"><a class="button primary" href="#library">Browse recipes →</a><a class="button secondary" href="#add">Add a recipe</a></div>
      </div>
      <aside class="app-card">
        <div class="toolbar"><div class="dots"><span></span><span></span><span></span></div><div class="status">Today’s pick</div></div>
        <div class="recipe-card">
          <div class="thumb pistachio"></div>
          <div class="recipe-card-body">
            <div class="card-meta"><span class="mini-pill">Gelato</span><span class="mini-pill">Best version</span><span class="mini-pill">★ 8.5</span></div>
            <h3>Pistachio Sicilian-style gelato</h3>
            <p>Smooth, strong pistachio, adult sweetness right. Next: more salt and compare next-day scoopability.</p>
          </div>
        </div>
      </aside>
    </section>

    <section id="library" class="section">
      <div class="section-head"><h2>Recipe library.</h2><p class="sub">Search by recipe, category, ingredient, or tag. The cards start from your existing ice-cream notes; next we turn each one into a full recipe page.</p></div>
      <div class="library-tools">
        <input id="recipeSearch" class="search" type="search" placeholder="Search recipes, ingredients, tags…" autocomplete="off" />
        <div id="recipeCount" class="filter-note">{len(recipes)} recipes</div>
      </div>
      <div class="library-grid">{recipe_cards}
        <a class="recipe-card add-card" href="#add" data-recipe-card data-search="add recipe new">
          <div class="add-card-inner"><div class="plus">+</div><h3>Add a new recipe</h3><p>Capture the idea, ingredients, exact products, and notes while it is fresh.</p></div>
        </a>
      </div>
    </section>

    <section id="ingredients" class="section">
      <div class="section-head"><h2>Ingredient shelf.</h2><p class="sub">A separate place for exact products, brands, fat percentages, and where they are used. Recipes can reference these instead of repeating product details every time.</p></div>
      <div class="ingredient-shelf">
        <article class="product-card"><span class="product-kind">Milk</span><h3>Migros Bio Vollmilch 3.5%</h3><p>Default whole milk reference for gelato formulas.</p><div class="card-meta"><span class="mini-pill">Used in pistachio</span><span class="mini-pill">Swiss grocery</span></div></article>
        <article class="product-card"><span class="product-kind">Cream</span><h3>Coop Vollrahm 35%</h3><p>Reference cream product for richer ice cream and gelato bases.</p><div class="card-meta"><span class="mini-pill">Chocolate</span><span class="mini-pill">Yogurt</span></div></article>
        <article class="product-card"><span class="product-kind">Yogurt</span><h3>Fage Total 5%</h3><p>Greek yogurt baseline for adult frozen yogurt.</p><div class="card-meta"><span class="mini-pill">Frozen yogurt</span></div></article>
        <article class="product-card"><span class="product-kind">Cocoa powder</span><h3>Cacao Barry Extra Brute</h3><p>High-fat Dutch-process cocoa powder for the rich chocolate ice cream. Recipe reference: 55g total base, 27.5g per CubeItaly churn.</p><div class="card-meta"><span class="mini-pill">Rich chocolate ice cream</span><span class="mini-pill">Chocolate depth</span></div></article>
        <article class="product-card"><span class="product-kind">Dark chocolate</span><h3>Callebaut 70.5%</h3><p>Couverture chocolate for body and flavour in the rich chocolate ice cream. Recipe reference: 115g total base, 57.5g per CubeItaly churn.</p><div class="card-meta"><span class="mini-pill">Rich chocolate ice cream</span><span class="mini-pill">Cocoa butter</span></div></article>
        <article class="product-card"><span class="product-kind">Flavor</span><h3>100% pistachio paste</h3><p>Unsweetened paste; keep separate from sweet pistachio cream.</p><div class="card-meta"><span class="mini-pill">Pistachio gelato</span></div></article>
      </div>
    </section>

    <section id="add" class="section">
      <div class="section-head"><h2>Add a recipe.</h2><p class="sub">Start with the essentials: what it is, the exact ingredients/products you used, and a few notes. We can expand it later with steps, photos, and results.</p></div>
      <form class="form-card" method="post" action="/recipes">
        <div class="form-grid">
          <label>Title<input name="title" required placeholder="e.g. Sourdough focaccia" /></label>
          <label>Category<input name="category" placeholder="Baking, Gelato, Mains..." /></label>
          <label class="full">Summary<textarea name="summary" placeholder="What is this recipe, and what matters about it?"></textarea></label>
          <label class="full">Ingredient references / quantities<textarea name="ingredients" placeholder="390g → Migros Bio Vollmilch 3.5%&#10;120g → Coop Vollrahm 35%&#10;72g → 100% pistachio paste"></textarea></label>
          <label>Tags<input name="tags" placeholder="gelato, pistachio, CubeItaly" /></label>
          <label>Status<select name="status"><option>Experiment</option><option>Best version</option><option>Needs tweak</option><option>Favorite</option></select></label>
          <label>Rating<input name="rating" placeholder="8.5" /></label>
          <label>Color<select name="color"><option value="">Neutral</option><option value="chocolate">Chocolate</option><option value="pistachio">Pistachio</option><option value="banana">Banana</option><option value="yogurt">Yogurt</option></select></label>
        </div>
        <div class="actions"><button class="primary" type="submit">Save recipe</button><a class="button secondary" href="#library">Cancel</a></div>
        {notice}
      </form>
    </section>

    <section id="features" class="section">
      <div class="section-head"><h2>What comes next.</h2><p class="sub">Make browsing feel complete first, then add deeper recipe and result pages.</p></div>
      <div class="feature-grid">
        <article class="feature"><div class="icon">📖</div><h3>Recipe detail</h3><p>Ingredients, steps, equipment, source, and current best version.</p></article>
        <article class="feature"><div class="icon">🧪</div><h3>Batch log</h3><p>Record result, texture, sweetness, rating, and next tweak after each cook.</p></article>
        <article class="feature"><div class="icon">📷</div><h3>Photo uploads</h3><p>Attach cover photos, process photos, and before/after batch evidence.</p></article>
      </div>
    </section>
  </main>
  <footer class="shell">Home Recipes · a private kitchen notebook for recipes, products, photos, and results.</footer>
  <script>
    const search = document.getElementById('recipeSearch');
    const count = document.getElementById('recipeCount');
    const cards = [...document.querySelectorAll('[data-recipe-card]')];
    const realCards = cards.filter(card => !card.classList.contains('add-card'));
    function applyFilter() {{
      const query = (search?.value || '').trim().toLowerCase();
      let visible = 0;
      for (const card of cards) {{
        const isAdd = card.classList.contains('add-card');
        const match = !query || card.dataset.search.includes(query) || isAdd;
        card.style.display = match ? '' : 'none';
        if (match && !isAdd) visible += 1;
      }}
      count.textContent = query ? `${{visible}} found` : `${{realCards.length}} recipes`;
    }}
    search?.addEventListener('input', applyFilter);
  </script>
</body>
</html>"""
    return html_doc.encode("utf-8")


def login_page(message: str = "") -> bytes:
    notice = f'<p class="login-error">{esc(message)}</p>' if message else ""
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Log in · Home Recipes</title>
  <style>{CSS}</style>
</head>
<body>
  <main class="login-shell">
    <section class="login-card">
      <a class="brand" href="/login" aria-label="Home Recipes login"><span class="mark">✦</span><span>Home Recipes</span></a>
      <h1>Welcome back.</h1>
      <p class="lead">Log in to open the family recipe notebook.</p>
      <form class="login-form" method="post" action="/login">
        <label>Username<input name="username" required autocomplete="username" autofocus /></label>
        <label>Password<input name="password" required type="password" autocomplete="current-password" /></label>
        <button class="primary" type="submit">Log in</button>
        {notice}
      </form>
    </section>
  </main>
</body>
</html>"""
    return html_doc.encode("utf-8")


def parse_recipe_path(path: str) -> tuple[int, str] | None:
    parts = path.strip("/").split("/")
    if len(parts) == 2 and parts[0] == "recipes":
        try:
            return int(parts[1]), "detail"
        except ValueError:
            return None
    if len(parts) == 3 and parts[0] == "recipes" and parts[2] == "edit":
        try:
            return int(parts[1]), "edit"
        except ValueError:
            return None
    return None


class UploadedFile:
    def __init__(self, filename: str, content_type: str, data: bytes) -> None:
        self.filename = filename
        self.type = content_type
        self.data = data


class Handler(BaseHTTPRequestHandler):
    def send_html(self, body: bytes, status: int = 200, extra_headers: dict[str, str] | None = None, include_body: bool = True) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def redirect(self, location: str, extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def require_user(self) -> str | None:
        username = current_user(self.headers)
        if username:
            return username
        self.redirect("/login")
        return None

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/login":
            self.send_html(login_page(), include_body=False)
            return
        username = current_user(self.headers)
        if not username:
            self.redirect("/login")
            return
        recipe_route = parse_recipe_path(parsed.path)
        if recipe_route:
            recipe_id, action = recipe_route
            recipe = get_recipe(recipe_id)
            if not recipe:
                self.send_error(404)
                return
            body = edit_recipe_page(username, recipe) if action == "edit" else recipe_detail_page(username, recipe)
            self.send_html(body, include_body=False)
            return
        if parsed.path != "/":
            self.send_error(404)
            return
        self.send_html(page(username), include_body=False)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/login":
            if current_user(self.headers):
                self.redirect("/")
                return
            self.send_html(login_page())
            return
        if parsed.path == "/logout":
            self.redirect("/login", {"Set-Cookie": clear_session_cookie()})
            return
        if parsed.path.startswith("/uploads/"):
            username = self.require_user()
            if not username:
                return
            name = Path(parsed.path).name
            target = UPLOAD_DIR / name
            if not target.exists() or not target.is_file():
                self.send_error(404)
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        username = self.require_user()
        if not username:
            return
        recipe_route = parse_recipe_path(parsed.path)
        if recipe_route:
            recipe_id, action = recipe_route
            recipe = get_recipe(recipe_id)
            if not recipe:
                self.send_error(404)
                return
            body = edit_recipe_page(username, recipe) if action == "edit" else recipe_detail_page(username, recipe)
            self.send_html(body)
            return
        if parsed.path != "/":
            self.send_error(404)
            return
        self.send_html(page(username))

    def read_urlencoded_fields(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    def read_multipart_fields(self):
        content_type = self.headers.get("Content-Type", "")
        marker = "boundary="
        if marker not in content_type:
            return {}, {}
        boundary = content_type.split(marker, 1)[1].strip().strip('"').encode()
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        fields: dict[str, str] = {}
        files = {}
        for part in raw.split(b"--" + boundary):
            part = part.strip(b"\r\n")
            if not part or part == b"--" or b"\r\n\r\n" not in part:
                continue
            header_raw, body = part.split(b"\r\n\r\n", 1)
            body = body.rstrip(b"\r\n")
            headers = header_raw.decode("utf-8", errors="replace").split("\r\n")
            disposition = next((h for h in headers if h.lower().startswith("content-disposition:")), "")
            content_type_header = next((h for h in headers if h.lower().startswith("content-type:")), "")
            attrs = {}
            for chunk in disposition.split(";"):
                if "=" in chunk:
                    key, value = chunk.strip().split("=", 1)
                    attrs[key.lower()] = value.strip().strip('"')
            name = attrs.get("name", "")
            filename = attrs.get("filename", "")
            if not name:
                continue
            if filename:
                file_type = content_type_header.split(":", 1)[1].strip() if ":" in content_type_header else "application/octet-stream"
                files[name] = UploadedFile(filename, file_type, body)
            else:
                fields[name] = body.decode("utf-8", errors="replace")
        return fields, files

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/login":
            fields = self.read_urlencoded_fields()
            username = authenticate(fields)
            if not username:
                self.send_html(login_page("Invalid username or password."), status=401)
                return
            self.redirect("/", {"Set-Cookie": make_session_cookie(username)})
            return

        username = self.require_user()
        if not username:
            return
        recipe_route = parse_recipe_path(parsed.path)
        if recipe_route and recipe_route[1] == "edit":
            recipe_id = recipe_route[0]
            content_type = self.headers.get("Content-Type", "")
            if content_type.startswith("multipart/form-data"):
                fields, files = self.read_multipart_fields()
                cover_photo = save_recipe_photo(files.get("cover_photo"))
            else:
                fields = self.read_urlencoded_fields()
                cover_photo = ""
            error = update_recipe(recipe_id, fields, cover_photo)
            if error:
                recipe = get_recipe(recipe_id)
                if not recipe:
                    self.send_error(404)
                    return
                self.send_html(edit_recipe_page(username, recipe, error), status=400)
                return
            self.redirect(f"/recipes/{recipe_id}")
            return
        if parsed.path != "/recipes":
            self.send_error(404)
            return
        fields = self.read_urlencoded_fields()
        error = create_recipe(fields)
        if error:
            self.send_html(page(username, error), status=400)
            return
        self.redirect("/#library")

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Home Recipes listening on http://0.0.0.0:{PORT} using {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
