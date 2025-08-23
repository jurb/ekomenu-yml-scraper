# ekomenu-yml-scraper

Convert **Ekomenu** recipes into clean YAML from logged-in recipe URLs on www.ekomenu.nl (and most likely on www.ekomenu.be). Those files can be imported into Paprika, a ios and macos recipe app.

## Features
- **No venvs required**: Scripts use `uv` in the shebang for dependency isolation.
- **Login + Fetch URL(s) → YAML** (`ekomenu2yml.py`)
- **Multi-recipe support**: Process multiple URLs in one call, outputs single YAML with all recipes
- Auto-detects servings (`X pers.` → `X servings`), with override option.
- **Complete extraction**: Ingredients (tags *Zelf toevoegen*), directions, tags, nutritional info, tips, and photos
- **Detailed nutrition**: Extracts comprehensive nutritional data (koolhydraten, eiwitten, vet, vezels, zout, etc.)
- **Smart photo matching**: Each recipe gets its correctly matched photo based on recipe name
- **Session management**: Save/reuse browser sessions to avoid repeated logins

## Getting Started

### Prerequisites
Install `uv` (once):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Usage


Install Playwright browsers (once):

```bash
uvx --from playwright playwright install
```

### Use credentials securely:

**Option A: CLI flags**

```bash
chmod +x ekomenu2yml.py
./ekomenu2yml.py --email you@example.com --password 'secret' \
  'https://www.ekomenu.nl/user?date=2025-08-25&recipe=11565' -o out/
```

**Option B: Environment variables**

```bash
export EKOMENU_EMAIL='you@example.com'
export EKOMENU_PASSWORD='secret'
./ekomenu2yml.py 'https://www.ekomenu.nl/user?date=2025-08-25&recipe=11565' -o out/
```

**Option C (recommended): Use a .env file**

1. Create `.env` in project root:
```bash
EKOMENU_EMAIL="you@example.com"
EKOMENU_PASSWORD="secret-password"
```

2. Run the script using uv:
```bash
# either:
UV_ENV_FILE=.env ./ekomenu2yml.py 'URL' -o out/

# or:
uv run --env-file .env ./ekomenu2yml.py 'URL' -o out/
```

uv will load the variables from .env. If both shell and .env define the same variable, shell wins. CLI flags override both.

### Debug mode (show browser)

```bash
./ekomenu2yml.py --headful URL -o out/
```

### Save/reuse browser session (avoid re-login)

```bash
# First run: login and save session state
./ekomenu2yml.py --save-state out/state.json 'URL1' -o out/

# Subsequent runs: reuse saved session (no login required)
./ekomenu2yml.py --use-state out/state.json 'URL2' 'URL3' -o out/
```

### Multiple URLs in one call

```bash
# Process multiple recipes at once (saves to single YAML file)
./ekomenu2yml.py --use-state out/state.json \
  'https://www.ekomenu.nl/user?date=2025-08-25&recipe=11565' \
  'https://www.ekomenu.nl/user?date=2025-08-25&recipe=13816' \
  'https://www.ekomenu.nl/user?date=2025-07-21&recipe=4657' \
  -o out/
```

## Output & Examples

- Single recipe: YYYY-MM-DD_RECIPEID_slug.yml
- Multiple recipes: recipes_YYYY-MM-DD_ID1_YYYY-MM-DD_ID2_etc.yml
- Each recipe includes: name, ingredients, directions, nutritional_info, photo (base64), cook_time, servings, notes
- Sample output: examples/macadamia.yml

## Repository Contents

- ekomenu2yml.py: Logged-in URL fetcher + YAML converter
- examples/: Example YAML files
- README.md, LICENSE: Project docs and MIT license

## Notes

- If Ekomenu’s HTML structure changes, you’ll need to update the selectors in the scripts.

## License

MIT