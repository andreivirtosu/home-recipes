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
import os
import sqlite3
import time
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("HOME_RECIPES_DB", ROOT / "data" / "home_recipes.sqlite3"))
PORT = int(os.environ.get("PORT", "8000"))
SESSION_SECRET = os.environ.get("HOME_RECIPES_SESSION_SECRET", "dev-home-recipes-session-secret-change-me")
SESSION_MAX_AGE = 60 * 60 * 24 * 30
ACCOUNTS = {
    "andrei": "andrei",
}

SEED_RECIPES = [
    ("Rich chocolate ice cream", "Ice cream", "Dense, premium chocolate direction for CubeItaly experiments.", "CubeItaly,chocolate,adult", "Experiment", "chocolate", ""),
    ("Kid-friendly chocolate gelato", "Gelato", "A softer, family-friendly chocolate profile to compare against richer adult batches.", "CubeItaly,chocolate,kids", "Experiment", "chocolate", ""),
    ("Pistachio Sicilian-style gelato", "Gelato", "The flagship iteration target: clean formula, batch notes, and next tweaks.", "CubeItaly,pistachio,best-version", "Best version", "pistachio", "8.5"),
    ("Adult Greek frozen yogurt", "Frozen yogurt", "Tangy adult profile with texture and sweetness notes to dial in.", "CubeItaly,yogurt,adult", "Experiment", "yogurt", ""),
    ("Banana milk gelato", "Gelato", "Fresh banana process and formulation target for small-machine batches.", "CubeItaly,banana,fruit", "Experiment", "banana", ""),
]

CSS = r"""
:root{
  --bg:#fbf7ef;--paper:#fffdf8;--paper-2:#f6efe4;--ink:#201813;--text:#3f332b;--muted:#74675d;--soft:#9a8b7d;
  --line:rgba(54,38,25,.13);--accent:#9d4f2f;--accent-2:#496b4e;--cream:#efe1cc;
  --shadow:0 18px 54px rgba(54,38,25,.11);--shadow-soft:0 8px 26px rgba(54,38,25,.07);
  --radius:24px;--display:Georgia,"Iowan Old Style","New York",serif;
}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:ui-sans-serif,-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;color:var(--text);background:linear-gradient(180deg,#fffaf2 0%,var(--bg) 48%,#f4ecdf 100%);min-height:100vh;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}body:before{content:"";position:fixed;inset:0;pointer-events:none;background:radial-gradient(circle at 8% -8%,rgba(212,146,76,.20),transparent 30rem),radial-gradient(circle at 92% 2%,rgba(102,125,82,.13),transparent 28rem)}a{color:inherit;text-decoration:none}.shell{width:min(1120px,calc(100% - 40px));margin:0 auto}header{position:sticky;top:0;z-index:10;padding:18px 0 12px;backdrop-filter:blur(18px);display:flex;align-items:center;justify-content:space-between;gap:24px}.brand{display:flex;align-items:center;gap:11px;font-weight:760;letter-spacing:-.02em;color:var(--ink)}.mark{width:36px;height:36px;border-radius:12px;background:linear-gradient(135deg,#b96a3e,#763b25);box-shadow:0 10px 24px rgba(157,79,47,.24);display:grid;place-items:center;color:#fff8ef;font-size:18px}nav{display:flex;gap:6px;color:var(--muted);font-size:14px;font-weight:640}nav a{padding:10px 12px;border-radius:999px}nav a:hover{background:rgba(255,255,255,.72);color:var(--ink)}.nav-user{padding:10px 12px;border-radius:999px;background:rgba(255,255,255,.58);color:var(--accent-2);font-weight:760}.login-shell{min-height:100vh;display:grid;place-items:center;padding:28px}.login-card{width:min(460px,100%);border:1px solid var(--line);border-radius:34px;background:rgba(255,253,248,.86);box-shadow:var(--shadow);padding:28px}.login-card h1{font-size:clamp(42px,7vw,62px);margin:18px 0 12px}.login-card .lead{font-size:16px}.login-form{display:grid;gap:14px;margin-top:24px}.login-error{margin:14px 0 0;color:var(--accent);font-weight:720}.hero{display:grid;grid-template-columns:minmax(0,1fr) 430px;gap:44px;align-items:center;padding:54px 0 38px}.eyebrow{display:inline-flex;gap:8px;align-items:center;padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.68);color:var(--accent-2);font-weight:720;font-size:13px;box-shadow:var(--shadow-soft)}h1{margin:22px 0 18px;font-family:var(--display);font-weight:520;font-size:clamp(48px,6.6vw,82px);line-height:1.02;letter-spacing:-.048em;color:var(--ink);max-width:760px;text-wrap:balance}.lead{margin:0;color:var(--muted);font-size:clamp(17px,1.7vw,21px);line-height:1.62;max-width:640px;text-wrap:pretty}.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:28px}.button,button{border:1px solid transparent;border-radius:999px;min-height:46px;padding:12px 17px;font-weight:720;display:inline-flex;align-items:center;justify-content:center;gap:10px;box-shadow:var(--shadow-soft);cursor:pointer;font:inherit}.primary{background:var(--ink);color:#fff8ef}.secondary{background:rgba(255,255,255,.78);border-color:var(--line);color:var(--ink)}.app-card{border:1px solid var(--line);background:rgba(255,253,248,.82);backdrop-filter:blur(18px);border-radius:32px;padding:16px;box-shadow:var(--shadow);overflow:hidden}.toolbar{display:flex;justify-content:space-between;align-items:center;padding:8px 6px 16px}.dots{display:flex;gap:7px}.dots span{width:10px;height:10px;border-radius:50%;background:#dfd0bf}.status{color:var(--soft);font-size:13px;font-weight:680}.section{padding:34px 0}.section-head{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:18px}.section h2{margin:0;font-family:var(--display);font-weight:520;font-size:clamp(31px,3.6vw,46px);line-height:1.08;letter-spacing:-.035em;color:var(--ink);text-wrap:balance}.section .sub{color:var(--muted);max-width:570px;line-height:1.58;text-wrap:pretty}.library-tools{display:grid;grid-template-columns:1fr auto;gap:12px;margin:0 0 18px}.search{border:1px solid var(--line);background:rgba(255,255,255,.82);border-radius:18px;padding:14px 16px;font:inherit;color:var(--ink);box-shadow:var(--shadow-soft)}.search::placeholder,input::placeholder,textarea::placeholder{color:#b1a397;font-weight:430}.filter-note{align-self:center;color:var(--muted);font-size:14px}.library-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.recipe-card{overflow:hidden;border:1px solid var(--line);border-radius:26px;background:rgba(255,255,255,.76);box-shadow:var(--shadow-soft);transition:transform .16s ease,box-shadow .16s ease,border-color .16s ease}.recipe-card:hover{transform:translateY(-2px);box-shadow:0 18px 44px rgba(54,38,25,.11);border-color:rgba(157,79,47,.22)}.recipe-card.add-card{display:grid;place-items:center;min-height:306px;border-style:dashed;background:rgba(255,253,248,.58)}.add-card-inner{text-align:center;padding:24px}.plus{width:48px;height:48px;border-radius:16px;background:var(--ink);color:#fff8ef;display:grid;place-items:center;margin:0 auto 14px;font-size:24px}.thumb{height:136px;background:linear-gradient(135deg,#dcb88c,#f5e6c8);position:relative}.thumb:after{content:"";position:absolute;inset:28px 54px;border-radius:999px;background:radial-gradient(circle at 46% 42%,rgba(255,255,255,.68) 0 12%,transparent 12.5%),var(--cream);box-shadow:0 12px 26px rgba(64,42,24,.12)}.thumb:before{content:"";position:absolute;left:22px;bottom:18px;width:58px;height:10px;border-radius:999px;background:rgba(255,255,255,.38)}.thumb.chocolate{background:linear-gradient(135deg,#332019,#8f5438 56%,#d3ad85)}.thumb.pistachio{background:linear-gradient(135deg,#6f8758,#e4d5a4)}.thumb.banana{background:linear-gradient(135deg,#e5c958,#fff0b5)}.thumb.yogurt{background:linear-gradient(135deg,#c9d8df,#fffaf0)}.recipe-card-body{padding:17px 18px 18px}.recipe-card h3{margin:0 0 8px;font-size:20px;line-height:1.22;letter-spacing:-.025em;color:var(--ink);text-wrap:balance}.recipe-card p{margin:0 0 14px;color:var(--muted);line-height:1.52;font-size:14.5px}.ingredient-list{list-style:none;margin:0 0 15px;padding:10px 0 0;border-top:1px solid rgba(54,38,25,.08);display:grid;gap:6px}.ingredient-list li{font-size:13px;line-height:1.35;color:#4b3d34;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ingredient-list .more{color:var(--soft);font-weight:680}.card-meta{display:flex;flex-wrap:wrap;gap:7px}.mini-pill{padding:5px 8px;border-radius:999px;background:#f1e6d7;color:#744632;font-size:11.5px;font-weight:680;letter-spacing:.005em}.ingredient-shelf{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.product-card{border:1px solid var(--line);border-radius:24px;background:rgba(255,255,255,.70);padding:18px;box-shadow:var(--shadow-soft)}.product-kind{display:inline-block;margin-bottom:18px;color:var(--accent-2);font-size:12px;font-weight:760;text-transform:uppercase;letter-spacing:.08em}.product-card h3{margin:0 0 8px;color:var(--ink);font-size:19px;line-height:1.22;letter-spacing:-.025em}.product-card p{margin:0 0 14px;color:var(--muted);font-size:14px;line-height:1.48}.form-card{border:1px solid var(--line);border-radius:30px;background:rgba(255,255,255,.78);box-shadow:var(--shadow);padding:22px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:grid;gap:7px;color:#5d5048;font-size:13px;font-weight:720}input,textarea,select{width:100%;border:1px solid var(--line);background:#fffdf9;border-radius:15px;padding:12px 13px;font:inherit;font-weight:480;color:var(--ink);outline:none}input:focus,textarea:focus,select:focus{border-color:rgba(157,79,47,.42);box-shadow:0 0 0 4px rgba(157,79,47,.10)}textarea{min-height:94px;resize:vertical}.full{grid-column:1/-1}.notice{margin:14px 0 0;color:var(--accent);font-weight:720}.feature-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.feature{border:1px solid var(--line);border-radius:24px;background:rgba(255,255,255,.62);padding:22px;min-height:164px;box-shadow:var(--shadow-soft)}.feature .icon{font-size:24px;margin-bottom:18px}.feature h3{margin:0 0 8px;font-size:20px;letter-spacing:-.025em;color:var(--ink)}.feature p{margin:0;color:var(--muted);line-height:1.52}footer{padding:34px 0;color:var(--soft);font-size:14px}@media(max-width:900px){header{position:relative}nav{display:none}.hero{grid-template-columns:1fr;padding-top:34px}.library-tools,.form-grid{grid-template-columns:1fr}.library-grid,.feature-grid,.ingredient-shelf{grid-template-columns:1fr}.section-head{display:block}.app-card{max-width:520px}.shell{width:min(100% - 28px,1120px)}}
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def seed_ingredients(title: str) -> str:
    seeds = {
        "Pistachio Sicilian-style gelato": "390g Migros Bio Vollmilch 3.5%\n72g sugar\n24g dextrose\n72g 100% pistachio paste\n0.6g fine sea salt",
        "Rich chocolate ice cream": "Migros/Coop whole milk\n35% cream\nCacao Barry Extra Brute cocoa\nCallebaut 70.5% chocolate\nDextrose",
        "Kid-friendly chocolate gelato": "Whole milk\nCream\nCocoa powder\nChocolate\nSugar + dextrose",
        "Adult Greek frozen yogurt": "Fage 5% Greek yogurt\nWhole milk\nCream\nSugar + dextrose\nLemon or salt if needed",
        "Banana milk gelato": "Very ripe banana\nWhole milk\nCream\nSugar + dextrose\nFine sea salt",
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
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        existing_cols = {row[1] for row in con.execute("PRAGMA table_info(recipes)")}
        if "ingredients" not in existing_cols:
            con.execute("ALTER TABLE recipes ADD COLUMN ingredients TEXT NOT NULL DEFAULT ''")

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


def create_recipe(fields: dict[str, str]) -> str | None:
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
    searchable = esc(" ".join([recipe["title"], recipe["category"], recipe["summary"], recipe["ingredients"], recipe["tags"], recipe["status"]]).lower())
    return f"""
      <article class="recipe-card" data-recipe-card data-search="{searchable}">
        <div class="thumb {color}"></div>
        <div class="recipe-card-body">
          <h3>{esc(recipe['title'])}</h3>
          <p>{esc(recipe['summary']) or 'No notes yet. Add the first result next.'}</p>
          {ingredient_html}
          <div class="card-meta">{pill_html}</div>
        </div>
      </article>
    """


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
        if parsed.path != "/":
            self.send_error(404)
            return
        username = current_user(self.headers)
        if not username:
            self.redirect("/login")
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
        if parsed.path != "/":
            self.send_error(404)
            return
        username = self.require_user()
        if not username:
            return
        self.send_html(page(username))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        fields = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

        if parsed.path == "/login":
            username = authenticate(fields)
            if not username:
                self.send_html(login_page("Invalid username or password."), status=401)
                return
            self.redirect("/", {"Set-Cookie": make_session_cookie(username)})
            return

        if parsed.path != "/recipes":
            self.send_error(404)
            return
        username = self.require_user()
        if not username:
            return
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
