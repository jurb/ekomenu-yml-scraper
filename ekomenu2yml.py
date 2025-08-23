#!/usr/bin/env -S uv run --script --with playwright --with beautifulsoup4 --with lxml
"""
ekomenu2yml — Login to Ekomenu, open recipe URLs, and export YAML.

Usage:
  ./ekomenu2yml.py [--email you@example.com] [--password SECRET]
                   [--use-state state.json] [--save-state state.json]
                   [--servings N] [--headful] [-o OUTDIR]
                   URL [URL ...]
"""

import argparse
import base64
import os
import re
import sys
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import requests

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# --- In-file defaults (optional) ---
EMAIL = ""       # e.g. "you@example.com"
PASSWORD = ""    # e.g. "super-secret"

def dismiss_cookiebot(page):
    # Handles Cookiebot overlay that intercepts clicks.
    selectors = [
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowallSelection",
        "#CybotCookiebotDialogBodyLevelButtonAccept",
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinDeclineAll",
        "button:has-text('Alles accepteren')",
        "button:has-text('Accepteer')",
        "button:has-text('Akkoord')",
        "button:has-text('Accept')",
        "button:has-text('Selectie toestaan')",
    ]
    try:
        dialog = page.locator("#CybotCookiebotDialog")
        if dialog.is_visible(timeout=1500):
            for sel in selectors:
                loc = page.locator(sel)
                if loc.count() and loc.first.is_visible():
                    loc.first.click(timeout=1500)
                    break
            dialog.wait_for(state="hidden", timeout=5000)
    except Exception:
        # last resort: remove it
        try:
            el = page.query_selector("#CybotCookiebotDialog")
            page.evaluate("d => d && d.remove()", el)
        except Exception:
            pass

def text(el):
    return (el.get_text(" ", strip=True) if el else "").strip()

def get_recipe_image_base64(soup, recipe_name="") -> str | None:
    """Extract the main recipe image and convert to base64, matching recipe name if possible."""
    # Look for all recipe images
    all_imgs = soup.find_all("img")
    
    # Create searchable terms from recipe name for matching
    recipe_terms = []
    if recipe_name:
        # Extract key words from recipe name
        name_lower = recipe_name.lower()
        terms = re.findall(r'\b\w{3,}\b', name_lower)  # Words with 3+ characters
        recipe_terms = [term for term in terms if term not in ['met', 'van', 'en', 'de', 'het', 'een']]
    
    img_url = None
    best_match = None
    best_score = 0
    
    for img in all_imgs:
        src = img.get("src") or img.get("data-src")
        alt = img.get("alt", "").lower()
        
        if src and "static.ekomenu.nl" in src and "recipe" in src:
            # Calculate match score based on recipe name
            score = 0
            if recipe_terms:
                for term in recipe_terms:
                    if term in src.lower():
                        score += 2
                    if term in alt:
                        score += 3
            
            # If this image has the best match score so far, use it
            if score > best_score:
                best_score = score
                best_match = src
            # If no match yet and this is a valid recipe image, keep it as fallback
            elif not best_match:
                best_match = src
    
    if best_match:
        img_url = best_match
        # Prefer larger images if available
        if "thumb-" in img_url:
            img_url = img_url.replace("thumb-", "large-")
        elif "medium-" in img_url:
            img_url = img_url.replace("medium-", "large-")
    
    if not img_url:
        return None
        
    # Make sure it's an absolute URL
    if img_url.startswith("./"):
        return None
    elif img_url.startswith("//"):
        img_url = "https:" + img_url
    elif not img_url.startswith("http"):
        img_url = "https://static.ekomenu.nl" + img_url
    
    try:
        response = requests.get(img_url, timeout=10)
        if response.status_code == 200:
            # Encode to base64
            img_base64 = base64.b64encode(response.content).decode('utf-8')
            return img_base64
    except Exception:
        pass
    
    return None

def parse_html_to_data(html: str, url: str = None, override_servings: int | None = None) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    title_h1 = soup.find("h1", attrs={"itemprop": "name"}) or soup.find("h1")
    name_main = ""
    if title_h1:
        span = title_h1.find("span")
        if span:
            sub = text(span)
            name_main = title_h1.get_text(" ", strip=True)
            if sub and sub in name_main:
                name_main = name_main.split(sub)[0].strip()
        else:
            name_main = text(title_h1)
    name = name_main or text(title_h1) or ""

    chips = [text(x) for x in soup.select(".chip .text-sm, .chip time")]
    cook_time, kcal, veg = "", "", ""
    for c in chips:
        if re.search(r"\bmin\b", c):
            cook_time = c
        elif "kcal" in c.lower():
            kcal = c
        elif re.search(r"\b\d+\s*g\s*groente\b", c.lower()):
            veg = c

    servings_raw = ""
    for sc in soup.select(".chip"):
        cls = " ".join(sc.get("class", []))
        if ("bg-e-dark-green" in cls and "text-white" in cls) and ("persons-" in (sc.get("id") or "")):
            servings_raw = text(sc)
            break
    if not servings_raw:
        pers = [text(sc) for sc in soup.select(".chip") if "pers." in text(sc)]
        servings_raw = pers[0] if pers else ""
    servings_n = None
    m = re.search(r"(\d+)\s*pers?\.", servings_raw.lower())
    if m:
        servings_n = int(m.group(1))
    if override_servings is not None:
        servings_n = override_servings

    def parse_ingredients_ul(ul):
        items = []
        for li in ul.find_all("li"):
            t = text(li)
            if not t:
                continue
            t = re.sub(r"\s+", " ", t)
            t = re.sub(r"Herkomst:.*", "", t).strip()
            t = re.sub(r"\s+(st|g|el|tl|ml|kg)\b", r" \1", t)
            items.append(t)
        return items

    ingredients, zelf_toevoegen = [], []
    for h2 in soup.find_all("h2"):
        if "Biologische ingrediënten" in text(h2):
            container = h2.parent
            uls = container.find_all("ul")
            if uls:
                ingredients = parse_ingredients_ul(uls[0])
            for st in container.find_all("strong"):
                if "Zelf toevoegen" in text(st):
                    nxt = st.find_next("ul")
                    if nxt:
                        zelf_toevoegen = parse_ingredients_ul(nxt)
            if ingredients:
                break
    if not zelf_toevoegen:
        st = soup.find("strong", string=lambda s: s and "Zelf toevoegen" in s)
        if st:
            nxt = st.find_next("ul")
            if nxt:
                zelf_toevoegen = parse_ingredients_ul(nxt)
    if zelf_toevoegen:
        ingredients += [f"{it} (zelf toevoegen)" for it in zelf_toevoegen]

    directions = []
    directions_ol = soup.find("ol", class_=re.compile(r"\bcounter\b"))
    if directions_ol:
        for i, li in enumerate(directions_ol.find_all("li"), 1):
            s = text(li)
            if s:
                directions.append(f"{i}. {s}")

    tip_text = ""
    for badge in soup.find_all(string=re.compile(r"\bTIP\b")):
        parent = badge.parent
        if parent and parent.name in {"div", "span"}:
            sib_span = parent.find_next("span")
            if sib_span:
                tip_text = text(sib_span)
                break

    # Extract detailed nutritional information
    nutri = {}
    allergenen = []
    
    # Search for nutritional span pairs globally in the HTML
    # The pattern we found is: <span>NutrientName</span><span>Value</span>
    nutritional_terms = ["koolhydraten", "eiwit", "vet", "vezels", "suikers", "zout", "energie", "natrium", "calcium", "vitaminen"]
    all_spans = soup.find_all("span")
    
    for i, span in enumerate(all_spans):
        key = text(span).strip()
        
        # Check if this span contains a nutritional term
        if (key and len(key) > 2 and 
            any(nutrient in key.lower() for nutrient in nutritional_terms)):
            
            # Look for the next span that contains the value (check immediate next span first)
            for j in range(i + 1, min(i + 3, len(all_spans))):  # Check up to 2 spans ahead
                val_span = all_spans[j]
                val = text(val_span).strip()
                
                # Check if this looks like a nutritional value
                if (val and re.search(r'\d+[.,]?\d*\s*[gmkl]', val) and 
                    len(val) < 20):  # Reasonable value length with units
                    nutri[key] = val
                    break
    
    # Look for voedingswaarden section for allergen information
    voeding_section = None
    
    # Find h3 with "Voedingswaarden"
    for h3 in soup.find_all("h3"):
        if "Voedingswaarden" in text(h3):
            voeding_section = h3.find_parent()
            break
    
    if not voeding_section:
        for element in soup.find_all(string=re.compile(r"Voedingswaarden")):
            parent = element.parent
            while parent and parent.name not in ["div", "section"]:
                parent = parent.parent
            if parent:
                voeding_section = parent
                break
    
    if voeding_section:
        # Look for allergen information in chips
        for chip in voeding_section.select("app-chip .chip, .chip"):
            allergen_text = text(chip).strip()
            if allergen_text and allergen_text not in allergenen and "font-medium" in " ".join(chip.get("class", [])):
                allergenen.append(allergen_text)

    tags = []
    for div in soup.find_all("div"):
        cls = " ".join(div.get("class", []))
        if all(x in cls for x in ["flex", "bg-e-white", "rounded-lg", "flex-wrap"]):
            if div.find("span", string=re.compile(r"Seizoen|Vegetarisch|Variatie|Lekker snel")):
                tags = [t.strip().rstrip(",") for t in (sp.get_text() for sp in div.find_all("span")) if t.strip()]

    nutri_lines = []
    if kcal:
        nutri_lines.append(f"Energie: {kcal} per portie")
    for k, v in nutri.items():
        if k == "Energie":
            continue
        nutri_lines.append(f"{k}: {v}")
    if veg:
        nutri_lines.append(f"Groente: {veg}")
    
    # Add allergen information to nutritional_info
    if allergenen:
        nutri_lines.append("")
        nutri_lines.append("Allergenen informatie")
        for allergen in allergenen:
            nutri_lines.append(allergen)

    notes_lines = []
    if tags:
        notes_lines.append("Tags: " + ", ".join(tags))
    if tip_text:
        notes_lines.append(f"Tip: {tip_text}")

    # Extract recipe image
    photo_base64 = get_recipe_image_base64(soup, name)

    return {
        "name": name,
        "servings": f"{servings_n} servings" if servings_n is not None else "",
        "cook_time": cook_time,
        "source": "Ekomenu",
        "source_url": url,
        "photo": photo_base64,
        "nutritional_info": "\n".join(nutri_lines).strip() or None,
        "notes": "\n".join(notes_lines).strip() or None,
        "ingredients": "\n".join(ingredients).strip() if ingredients else None,
        "directions": "\n".join(directions).strip() if directions else None,
    }

def render_yaml(data) -> str:
    if isinstance(data, list):
        # Multiple recipes
        lines = []
        for i, d in enumerate(data):
            if i > 0:
                lines.append("")
            lines.append("- name: " + (d.get("name") or ""))
            render_recipe_fields(d, lines, "  ")
        return "\n".join(lines) + "\n"
    else:
        # Single recipe
        lines = []
        lines.append("name: " + (data.get("name") or ""))
        render_recipe_fields(data, lines, "")
        return "\n".join(lines) + "\n"

def render_recipe_fields(d: dict, lines: list, indent: str):
    def push(k, v):
        if v in (None, "", []): return
        if isinstance(v, str) and ("\n" in v or k in {"notes", "ingredients", "directions", "nutritional_info", "photo"}):
            lines.append(f"{indent}{k}: |")
            lines.extend(f"{indent}  {ln}" for ln in v.split("\n"))
        else:
            lines.append(f"{indent}{k}: {v}")
    push("servings", d.get("servings"))
    push("cook_time", d.get("cook_time"))
    push("source", d.get("source"))
    push("source_url", d.get("source_url"))
    push("photo", d.get("photo"))
    push("nutritional_info", d.get("nutritional_info"))
    push("notes", d.get("notes"))
    push("ingredients", d.get("ingredients"))
    push("directions", d.get("directions"))

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "recipe"

def recipe_id_from_url(u: str) -> str:
    q = parse_qs(urlparse(u).query)
    rid = q.get("recipe", [None])[0]
    date = q.get("date", [None])[0]
    return f"{date}_{rid}" if (rid and date) else (rid or "recipe")

def ekomenu_login(page, email, password):
    page.goto("https://www.ekomenu.nl/login", wait_until="domcontentloaded")
    dismiss_cookiebot(page)

    for c in ["input[type='email']", "input[autocomplete='email']",
              "input[placeholder*='mail' i]", "input[name*='email' i]"]:
        if page.locator(c).count():
            page.fill(c, email); break
    for c in ["input[type='password']", "input[autocomplete='current-password']",
              "input[name*='pass' i]"]:
        if page.locator(c).count():
            page.fill(c, password); break

    for sel in ["button:has-text('Inloggen')", "button:has-text('Log in')",
                "button#login-button", "button:has-text('Login')"]:
        if page.locator(sel).count():
            try:
                page.locator(sel).click(timeout=30000)
            except Exception:
                dismiss_cookiebot(page)
                page.locator(sel).click(timeout=30000)
            break

    page.wait_for_load_state("networkidle")
    if "login" in page.url:
        raise RuntimeError("Login failed; still on login page")

def open_recipe(page, url):
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_selector("app-recipe h1[itemprop='name'], h1[itemprop='name']",
                               timeout=7000)
        return True
    except PWTimeout:
        pass
    for sel in ["button:has-text('Toon recept')", "img[alt='arrow down']"]:
        try:
            if page.locator(sel).count():
                page.locator(sel).first.click()
                page.wait_for_selector("app-recipe h1[itemprop='name'], h1[itemprop='name']",
                                       timeout=5000)
                return True
        except Exception:
            continue
    return False

def main():
    ap = argparse.ArgumentParser(description="Login to Ekomenu and export recipe URLs to YAML")
    ap.add_argument("urls", nargs="+", help="One or more Ekomenu recipe URLs (behind login)")
    ap.add_argument("--use-state", help="Path to a storage_state.json to preload")
    ap.add_argument("--save-state", help="Where to save storage_state after login")
    ap.add_argument("-o", "--outdir", default=".", help="Output directory for YAML files")
    ap.add_argument("--email", help="Ekomenu email")
    ap.add_argument("--password", help="Ekomenu password")
    ap.add_argument("--servings", type=int, help="Override servings count")
    ap.add_argument("--headful", action="store_true", help="Run non-headless for debugging")
    args = ap.parse_args()

    email = args.email or os.getenv("EKOMENU_EMAIL") or EMAIL
    password = args.password or os.getenv("EKOMENU_PASSWORD") or PASSWORD
    if not email or not password:
        print("Missing credentials. Provide --email/--password, or set EKOMENU_EMAIL/EKOMENU_PASSWORD, or fill EMAIL/PASSWORD in the file.", file=sys.stderr)
        sys.exit(2)

    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)

    # --- SINGLE sync_playwright block (no nesting) ---
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headful)

        ctx_kwargs = {}
        if args.use_state:
            ctx_kwargs["storage_state"] = args.use_state
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        if not args.use_state:
            ekomenu_login(page, email, password)
            if args.save_state:
                context.storage_state(path=args.save_state)
        else:
            dismiss_cookiebot(page)

        recipes = []
        for url in args.urls:
            if not open_recipe(page, url):
                print(f"[warn] Could not open recipe content for {url}", file=sys.stderr)
                continue
            html = page.content()
            data = parse_html_to_data(html, url, override_servings=args.servings)
            recipes.append(data)
            print(f"[ok] Scraped {url}")

        if recipes:
            if len(recipes) == 1:
                # Single recipe - use original naming
                rid = recipe_id_from_url(args.urls[0])
                slug = slugify(recipes[0].get("name") or rid)
                yml_path = outdir / f"{rid}_{slug}.yml"
                yml_path.write_text(render_yaml(recipes[0]), encoding="utf-8")
            else:
                # Multiple recipes - use combined naming
                rids = [recipe_id_from_url(url) for url in args.urls]
                yml_path = outdir / f"recipes_{'_'.join(rids)}.yml"
                yml_path.write_text(render_yaml(recipes), encoding="utf-8")
            print(f"[saved] {yml_path}")

        context.close()
        browser.close()

if __name__ == "__main__":
    main()