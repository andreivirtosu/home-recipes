# Home Recipes

A polished personal recipe lab for recipes, batches, photos, and results.

Current MVP:

- Python standard-library web app in `app.py`.
- SQLite persistence at `data/home_recipes.sqlite3` by default.
- Seeded recipe library from the existing Obsidian ice-cream notes.
- Add-recipe form that persists new recipes.
- Static `index.html` kept as the original visual prototype.

Run locally:

```bash
PORT=8000 python3 app.py
```

Open http://127.0.0.1:8000.

Planned next slices:

- Recipe detail pages with ingredients and steps.
- Batch/result logging per recipe.
- Photo uploads for recipes and batches.
- Promote a successful batch to the current best recipe.
- Import/sync from existing Obsidian notes.
