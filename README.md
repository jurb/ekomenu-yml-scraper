# ekomenu-yml-scraper

Convert **Ekomenu** recipes into clean YAML from logged-in recipe URLs on www.ekomenu.nl (and most likely on www.ekomenu.be). Those files can be imported into Paprika, a ios and macos recipe app.

## Features
- **No venvs required**: Scripts use `uv` in the shebang for dependency isolation.
- **Recipe ID Discovery** (`extract_recipe_ids.py`): Efficiently extract all recipe IDs from your subscription using API interception
- **Login + Fetch URL(s) → YAML** (`ekomenu2yml.py`)
- **Rating-based filename sorting**: Individual recipe files prefixed with rating for easy sorting (e.g., `4.5_123_recipe-name.yml`)
- **Multi-recipe support**: Process multiple URLs in one call, outputs single YAML with all recipes
- **Recipe combination tool** (`combine_recipes.py`): Merge individual YAML files into combined format with optional rating sorting
- Auto-detects servings (`X pers.` → `X servings`), with override option.
- **Complete extraction**: Ingredients (tags *Zelf toevoegen*), directions, tags, nutritional info, tips, and photos
- **Detailed nutrition**: Extracts comprehensive nutritional data (koolhydraten, eiwitten, vet, vezels, zout, etc.)
- **Smart photo matching**: Each recipe gets its correctly matched photo based on recipe name
- **Session management**: Save/reuse browser sessions to avoid repeated logins
- **Incremental updates**: Only collect new recipes on subsequent runs for efficiency

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

## Recipe Discovery & Conversion

### Step 1: Extract All Recipe IDs (Recommended)

Use the efficient API-based recipe ID extraction that navigates through all historical dates:

```bash
# Extract all recipe IDs from your subscription using API interception
UV_ENV_FILE=.env ./extract_recipe_ids.py --use-state out/state.json --output all_recipe_ids.txt

# Or with specific date range
UV_ENV_FILE=.env ./extract_recipe_ids.py --use-state out/state.json \
  --start-date 2024-01-01 --end-date 2024-12-31 --output 2024_recipes.txt
```

This creates two files:
- `all_recipe_ids.txt`: List of recipe IDs (4000, 4816, etc.)
- `all_recipe_ids.urls.txt`: Clean recipe URLs without date dependencies

### Step 2: Convert to Individual YAML Files with Rating Prefixes

Process each recipe URL individually to create separate files sorted by rating:

```bash
# Convert all URLs to individual YAML files with rating prefixes
while read url; do
  UV_ENV_FILE=.env ./ekomenu2yml.py --use-state out/state.json "$url" -o out/
done < all_recipe_ids.urls.txt
```

This creates files like:
- `4.7_5731_flammkuchen-met-rode-kool-brie-peer.yml`
- `4.5_3643_citroenrisotto-met-krokante-pancetta.yml`
- `4.0_640_bulgur-met-gegrilde-groenten.yml`

### Step 3: Combine Selected Recipes (Optional)

Use the combination tool to merge individual YAML files:

```bash
# Combine specific recipes into one file
./combine_recipes.py recipe1.yml recipe2.yml --output combined.yml

# Combine all recipes sorted by rating (highest first)
./combine_recipes.py out/*.yml --output all_recipes_by_rating.yml --sort-by-rating

# Combine selected recipes from a folder
./combine_recipes.py out/selectie/*.yml --output out/selectie/combined_selectie.yml --sort-by-rating
```

### Options for Recipe ID Extraction

- `--start-date YYYY-MM-DD`: Start date (default: 2023-10-02)
- `--end-date YYYY-MM-DD`: End date (default: current date) 
- `--incremental`: Only collect new IDs, skip existing ones
- `--headful`: Run browser in visible mode for debugging
- `--output FILE`: Output file for recipe IDs (default: recipe_ids.txt)

## Individual Recipe Conversion

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

### Individual Recipe Files (with rating prefixes)
- Format: `RATING_RECIPEID_slug.yml`
- Examples: 
  - `4.7_5731_flammkuchen-met-rode-kool-brie-peer.yml`
  - `4.5_3643_citroenrisotto-met-krokante-pancetta.yml`
  - `0.0_730_pad-thai-met-noodles-en-pinda-s.yml` (no rating)

### Combined Recipe Files
- Multiple recipes: `recipes_ID1_ID2_etc.yml` (when using multiple URLs)
- Combined selection: User-defined combined files with rating sorting
- Each recipe includes: name, ingredients, directions, nutritional_info, photo (base64), cook_time, servings, notes with ratings

### Sample Workflow Output
1. **Recipe ID extraction**: `all_recipe_ids.txt` (211 unique IDs) + `all_recipe_ids.urls.txt`
2. **Individual conversion**: 211 YAML files with rating prefixes in `out/`
3. **Selection**: Manually selected high-rated recipes in `out/selectie/`
4. **Final combination**: `out/selectie/combined_selectie.yml` sorted by rating

## Repository Contents

- **extract_recipe_ids.py**: Efficiently extract all recipe IDs using API interception
- **ekomenu2yml.py**: Convert recipe URLs to YAML format with rating prefixes
- **combine_recipes.py**: Merge individual YAML files with optional rating sorting
- **scrape_recipe_urls.py**: Legacy recipe URL discovery (deprecated in favor of extract_recipe_ids.py)
- examples/: Example YAML files
- README.md, LICENSE: Project docs and MIT license

## Notes

- If Ekomenu’s HTML structure changes, you’ll need to update the selectors in the scripts.

## License

MIT