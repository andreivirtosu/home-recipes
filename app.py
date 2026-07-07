#!/usr/bin/env python3
"""Tiny SQLite-backed Home Recipes MVP.

No framework yet: this keeps deployment simple on the existing VPS while proving
browse + add + persistence. Later we can replace it with FastAPI/Next.js without
changing the product model.
"""

from __future__ import annotations

import html
import os
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("HOME_RECIPES_DB", ROOT / "data" / "home_recipes.sqlite3"))
PORT = int(os.environ.get("PORT", "8000"))

SEED_RECIPES = [
    ("Rich chocolate ice cream", "Ice cream", "Dense, premium chocolate direction for CubeItaly experiments.", "CubeItaly,chocolate,adult", "Experiment", "chocolate", ""),
    ("Kid-friendly chocolate gelato", "Gelato", "A softer, family-friendly chocolate profile to compare against richer adult batches.", "CubeItaly,chocolate,kids", "Experiment", "chocolate", ""),
    ("Pistachio Sicilian-style gelato", "Gelato", "The flagship iteration target: clean formula, batch notes, and next tweaks.", "CubeItaly,pistachio,best-version", "Best version", "pistachio", "8.5"),
    ("Adult Greek frozen yogurt", "Frozen yogurt", "Tangy adult profile with texture and sweetness notes to dial in.", "CubeItaly,yogurt,adult", "Experiment", "yogurt", ""),
    ("Banana milk gelato", "Gelato", "Fresh banana process and formulation target for small-machine batches.", "CubeItaly,banana,fruit", "Experiment", "banana", ""),
]

CSS = r"""
:root{--bg:#faf7f1;--panel:#fffdf9;--ink:#211812;--muted:#796c60;--line:rgba(72,50,31,.13);--accent:#a4522d;--accent-dark:#76371f;--cream:#f2e5d2;--shadow:0 24px 80px rgba(64,42,24,.14);--radius:28px}*{box-sizing:border-box}body{margin:0;font-family:ui-sans-serif,-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;color:var(--ink);background:radial-gradient(circle at 10% -10%,rgba(255,207,143,.42),transparent 32rem),radial-gradient(circle at 90% 0%,rgba(176,107,68,.20),transparent 30rem),linear-gradient(180deg,#fff9ef 0%,var(--bg) 52%,#f6efe5 100%);min-height:100vh}a{color:inherit;text-decoration:none}.shell{width:min(1160px,calc(100% - 40px));margin:0 auto}header{padding:26px 0 16px;display:flex;align-items:center;justify-content:space-between;gap:24px}.brand{display:flex;align-items:center;gap:12px;font-weight:760;letter-spacing:-.03em}.mark{width:38px;height:38px;border-radius:13px;background:linear-gradient(135deg,#c06b3f,#7c3a21);box-shadow:0 10px 28px rgba(164,82,45,.28);display:grid;place-items:center;color:#fff7ed;font-size:20px}nav{display:flex;gap:10px;color:var(--muted);font-size:14px}nav a{padding:9px 12px;border-radius:999px}nav a:hover{background:rgba(255,255,255,.72);color:var(--ink)}.hero{display:grid;grid-template-columns:1.02fr .98fr;gap:34px;align-items:center;padding:48px 0 34px}.eyebrow{display:inline-flex;gap:8px;align-items:center;padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.62);color:var(--accent-dark);font-weight:680;font-size:13px;box-shadow:0 8px 26px rgba(64,42,24,.06)}h1{margin:22px 0 18px;font-size:clamp(48px,7vw,86px);line-height:.92;letter-spacing:-.075em;max-width:760px}.lead{margin:0;color:var(--muted);font-size:clamp(18px,2vw,22px);line-height:1.55;max-width:650px}.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:30px}.button,button{border:1px solid transparent;border-radius:999px;padding:13px 18px;font-weight:730;display:inline-flex;align-items:center;gap:10px;box-shadow:0 12px 30px rgba(64,42,24,.10);cursor:pointer}.primary{background:var(--ink);color:#fff7ed}.secondary{background:rgba(255,255,255,.72);border-color:var(--line);color:var(--ink)}.app-card{position:relative;border:1px solid rgba(72,50,31,.12);background:rgba(255,253,249,.78);backdrop-filter:blur(20px);border-radius:38px;padding:18px;box-shadow:var(--shadow);overflow:hidden}.toolbar{position:relative;display:flex;justify-content:space-between;align-items:center;padding:8px 8px 18px}.dots{display:flex;gap:7px}.dots span{width:11px;height:11px;border-radius:50%;background:#decfbe}.status{color:var(--muted);font-size:13px;font-weight:650}.section{padding:42px 0}.section-head{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:18px}.section h2{margin:0;font-size:clamp(32px,4vw,48px);letter-spacing:-.055em}.section .sub{color:var(--muted);max-width:560px;line-height:1.5}.library-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.recipe-card{overflow:hidden;border:1px solid var(--line);border-radius:28px;background:rgba(255,255,255,.68);box-shadow:0 14px 40px rgba(64,42,24,.07)}.thumb{height:154px;background:linear-gradient(135deg,#dcb88c,#f5e6c8);position:relative}.thumb:after{content:"";position:absolute;inset:26px 42px;border-radius:999px;background:radial-gradient(circle at 46% 42%,rgba(255,255,255,.68) 0 12%,transparent 12.5%),var(--cream);box-shadow:0 14px 30px rgba(64,42,24,.13)}.thumb.chocolate{background:linear-gradient(135deg,#3b241d,#9c5b3b 54%,#d7b085)}.thumb.pistachio{background:linear-gradient(135deg,#7f9764,#e3d4a2)}.thumb.banana{background:linear-gradient(135deg,#ead26b,#fff0b5)}.thumb.yogurt{background:linear-gradient(135deg,#cedce4,#fffaf0)}.recipe-card-body{padding:18px}.recipe-card h3{margin:0 0 8px;font-size:19px;letter-spacing:-.035em}.recipe-card p{margin:0 0 14px;color:var(--muted);line-height:1.42;font-size:14px}.card-meta{display:flex;flex-wrap:wrap;gap:8px}.mini-pill{padding:6px 9px;border-radius:999px;background:#f4eadc;color:#74412a;font-size:12px;font-weight:720}.form-card{border:1px solid var(--line);border-radius:32px;background:rgba(255,255,255,.72);box-shadow:var(--shadow);padding:22px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:grid;gap:7px;color:var(--muted);font-size:13px;font-weight:720}input,textarea,select{width:100%;border:1px solid var(--line);background:#fffdf9;border-radius:16px;padding:12px 13px;font:inherit;color:var(--ink)}textarea{min-height:94px;resize:vertical}.full{grid-column:1/-1}.notice{margin:14px 0 0;color:var(--accent-dark);font-weight:720}.feature-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.feature{border:1px solid var(--line);border-radius:26px;background:rgba(255,255,255,.58);padding:22px;min-height:176px;box-shadow:0 14px 40px rgba(64,42,24,.07)}.feature .icon{font-size:28px;margin-bottom:22px}.feature h3{margin:0 0 8px;font-size:20px;letter-spacing:-.035em}.feature p{margin:0;color:var(--muted);line-height:1.48}footer{padding:42px 0 34px;color:var(--muted);font-size:14px}@media(max-width:900px){nav{display:none}.hero,.form-grid{grid-template-columns:1fr}.library-grid,.feature-grid{grid-template-columns:1fr}.section-head{display:block}}
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS recipes (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              title TEXT NOT NULL UNIQUE,
              category TEXT NOT NULL DEFAULT '',
              summary TEXT NOT NULL DEFAULT '',
              tags TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'Experiment',
              color TEXT NOT NULL DEFAULT '',
              rating TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
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
                (title, category, summary, tags, status, color, rating, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (title, category, summary, tags, status, color, rating, now, now),
            )


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def get_recipes() -> list[sqlite3.Row]:
    with connect() as con:
        return list(con.execute("SELECT * FROM recipes ORDER BY updated_at DESC, title ASC"))


def create_recipe(fields: dict[str, str]) -> str | None:
    title = fields.get("title", "").strip()
    if not title:
        return "Title is required."
    category = fields.get("category", "").strip() or "Uncategorized"
    summary = fields.get("summary", "").strip()
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
                (title, category, summary, tags, status, color, rating, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (title, category, summary, tags, status, color, rating, now, now),
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
    color = esc(recipe["color"])
    return f"""
      <article class="recipe-card">
        <div class="thumb {color}"></div>
        <div class="recipe-card-body">
          <h3>{esc(recipe['title'])}</h3>
          <p>{esc(recipe['summary']) or 'No notes yet. Add the first batch result next.'}</p>
          <div class="card-meta">{pill_html}</div>
        </div>
      </article>
    """


def page(message: str = "") -> bytes:
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
    <nav><a href="#library">Library</a><a href="#add">Add recipe</a><a href="#features">Features</a></nav>
  </header>

  <main class="shell">
    <section class="hero">
      <div>
        <div class="eyebrow">SQLite-backed MVP · {len(recipes)} recipes</div>
        <h1>Recipes that remember what happened.</h1>
        <p class="lead">A polished personal recipe app for the current best version, every batch you made, photos, ratings, and the next tweak to try.</p>
        <div class="actions"><a class="button primary" href="#library">Browse recipes →</a><a class="button secondary" href="#add">Add a recipe</a></div>
      </div>
      <aside class="app-card">
        <div class="toolbar"><div class="dots"><span></span><span></span><span></span></div><div class="status">Persistent SQLite data</div></div>
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
      <div class="section-head"><h2>Recipe library.</h2><p class="sub">Seeded from your existing Obsidian ice-cream notes. New recipes added here are persisted in SQLite on the VPS.</p></div>
      <div class="library-grid">{recipe_cards}</div>
    </section>

    <section id="add" class="section">
      <div class="section-head"><h2>Add a recipe.</h2><p class="sub">Tiny first form: enough to prove persistence. Next we add full ingredient/step editing, batch logs, and photo uploads.</p></div>
      <form class="form-card" method="post" action="/recipes">
        <div class="form-grid">
          <label>Title<input name="title" required placeholder="e.g. Sourdough focaccia" /></label>
          <label>Category<input name="category" placeholder="Baking, Gelato, Mains..." /></label>
          <label class="full">Summary<textarea name="summary" placeholder="What is this recipe, and what matters about it?"></textarea></label>
          <label>Tags<input name="tags" placeholder="comma,separated,tags" /></label>
          <label>Status<select name="status"><option>Experiment</option><option>Best version</option><option>Needs tweak</option><option>Favorite</option></select></label>
          <label>Rating<input name="rating" placeholder="8.5" /></label>
          <label>Color<select name="color"><option value="">Neutral</option><option value="chocolate">Chocolate</option><option value="pistachio">Pistachio</option><option value="banana">Banana</option><option value="yogurt">Yogurt</option></select></label>
        </div>
        <div class="actions"><button class="primary" type="submit">Save recipe</button><a class="button secondary" href="#library">Cancel</a></div>
        {notice}
      </form>
    </section>

    <section id="features" class="section">
      <div class="section-head"><h2>Next product slices.</h2><p class="sub">The structure is intentionally simple, but the data model already has recipes and batches.</p></div>
      <div class="feature-grid">
        <article class="feature"><div class="icon">📖</div><h3>Recipe detail</h3><p>Ingredients, steps, equipment, source, and current best version.</p></article>
        <article class="feature"><div class="icon">🧪</div><h3>Batch log</h3><p>Record result, texture, sweetness, rating, and next tweak after each cook.</p></article>
        <article class="feature"><div class="icon">📷</div><h3>Photo uploads</h3><p>Attach cover photos, process photos, and before/after batch evidence.</p></article>
      </div>
    </section>
  </main>
  <footer class="shell">Home Recipes MVP · SQLite database: {esc(DB_PATH)}</footer>
</body>
</html>"""
    return html_doc.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/":
            self.send_error(404)
            return
        body = page()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/recipes":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        fields = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
        error = create_recipe(fields)
        if error:
            body = page(error)
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(303)
        self.send_header("Location", "/#library")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Home Recipes listening on http://0.0.0.0:{PORT} using {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
