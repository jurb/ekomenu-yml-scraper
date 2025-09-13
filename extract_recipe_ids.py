#!/usr/bin/env -S uv run --script --with playwright
"""
Extract recipe IDs from Ekomenu API calls by intercepting network requests.
Much more efficient than clicking buttons - just captures the 'list' API response.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

def dismiss_cookiebot(page):
    """Handles Cookiebot overlay that intercepts clicks."""
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
        try:
            el = page.query_selector("#CybotCookiebotDialog")
            page.evaluate("d => d && d.remove()", el)
        except Exception:
            pass

def generate_date_range(start_date, end_date=None):
    """Generate weekly dates from start_date to end_date (or current date)."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    if end_date is None:
        end = datetime.now()
    else:
        end = datetime.strptime(end_date, "%Y-%m-%d")
    
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(weeks=1)
    
    return dates

def extract_all_recipe_ids(page):
    """Extract recipe IDs by clicking through all available dates in the navigation."""
    print(f"Extracting recipe IDs from all available dates...")
    
    all_recipe_ids = []
    captured_responses = []
    
    def handle_response(response):
        """Capture API responses that might contain recipe data."""
        if ("recipebff/v1/recipe/list" in response.url):
            # Extract recipe IDs directly from the URL parameters
            import re
            from urllib.parse import urlparse, parse_qs
            
            parsed_url = urlparse(response.url)
            query_params = parse_qs(parsed_url.query)
            
            if 'ids' in query_params:
                ids_param = query_params['ids'][0]
                # Split by comma and URL decode
                from urllib.parse import unquote
                ids_param = unquote(ids_param)
                recipe_ids_from_url = [id.strip() for id in ids_param.split(',') if id.strip().isdigit()]
                
                if recipe_ids_from_url:
                    all_recipe_ids.extend(recipe_ids_from_url)
                    print(f"  Found recipe IDs in URL: {recipe_ids_from_url} from {response.url}")
            
            captured_responses.append({"url": response.url})
        elif ("list" in response.url.lower() and "recipe" in response.url.lower()):
            print(f"  Captured other API: {response.url}")
    
    # Set up response interceptor
    page.on("response", handle_response)
    
    try:
        # Navigate to user page
        page.goto("https://www.ekomenu.nl/user", wait_until="domcontentloaded")
        dismiss_cookiebot(page)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except:
            pass  # Don't wait too long
        page.wait_for_timeout(1000)
        
        # Dismiss any modal that might be blocking clicks
        try:
            # Try pressing Escape first
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            
            # Try clicking specific close buttons
            close_selectors = [
                "a:has-text('Laat deze popup niet meer zien op dit apparaat')",
                "button:has-text('×')",
                "button[aria-label='Close']",
                ".modal .close",
                "ngb-modal-window button"
            ]
            
            for selector in close_selectors:
                try:
                    if page.locator(selector).count():
                        page.locator(selector).first.click(timeout=1000)
                        page.wait_for_timeout(500)
                        break
                except:
                    continue
                    
        except:
            pass
        
        # Navigate to the oldest dates using the previous button
        print("  Navigating to oldest available dates...")
        prev_button = page.locator(".swiper-button-prev")
        
        # Keep clicking the previous button until we reach the beginning
        prev_clicks = 0
        while prev_clicks < 200:  # Prevent infinite loop
            try:
                if prev_button.is_visible() and prev_button.is_enabled():
                    prev_button.click(timeout=2000)
                    page.wait_for_timeout(500)  # Wait for navigation
                    prev_clicks += 1
                else:
                    print(f"    Reached oldest dates after {prev_clicks} previous clicks")
                    break
            except Exception as e:
                print(f"    Reached beginning or error: {e}")
                break
        
        # Now navigate forward through all dates and collect recipe IDs
        print("  Collecting recipe IDs from all dates...")
        processed_dates = set()
        next_button = page.locator(".swiper-button-next")
        
        # Process dates in chunks as we navigate forward
        navigation_round = 0
        while navigation_round < 500:  # Allow for many navigation rounds
            try:
                # Get currently visible date buttons
                date_buttons = page.locator('#deliveryboxes > div[id^="deliverybox-"]')
                button_count = date_buttons.count()
                
                if button_count == 0:
                    print("    No date buttons found")
                    break
                
                # Click through visible date buttons
                new_dates_found = False
                for i in range(button_count):
                    try:
                        button = date_buttons.nth(i)
                        if not button.is_visible():
                            continue
                            
                        # Get the date text for logging and deduplication
                        date_text = button.text_content() or f"button-{i}"
                        
                        # Skip if we've already processed this date
                        if date_text in processed_dates:
                            continue
                            
                        processed_dates.add(date_text)
                        new_dates_found = True
                        print(f"  Clicking date: {date_text} (total processed: {len(processed_dates)})")
                        
                        # Clear previous responses for this date
                        responses_before = len(captured_responses)
                        
                        # Click the date button
                        button.click(timeout=3000)
                        page.wait_for_timeout(800)  # Wait for API calls
                        
                        # Check if we got new responses
                        new_responses = len(captured_responses) - responses_before
                        print(f"    Got {new_responses} new API responses")
                        
                    except Exception as e:
                        print(f"    Error clicking date button {i}: {e}")
                        continue
                
                # Navigate to next set of dates
                try:
                    if next_button.is_visible() and next_button.is_enabled():
                        next_button.click(timeout=2000)
                        page.wait_for_timeout(500)  # Wait for navigation
                        navigation_round += 1
                    else:
                        print(f"    Reached end of dates after {navigation_round} navigation rounds")
                        break
                except Exception as e:
                    print(f"    Navigation completed or error: {e}")
                    break
                    
            except Exception as e:
                print(f"    Error in date collection loop: {e}")
                break
        
        print(f"  Processed {len(processed_dates)} unique dates total")
        
        # Remove duplicates while preserving order
        unique_ids = list(dict.fromkeys(all_recipe_ids))
        print(f"  Found {len(unique_ids)} unique recipe IDs total: {unique_ids}")
        return unique_ids
        
    except Exception as e:
        print(f"  Error extracting recipe IDs: {e}")
        return []

def extract_ids_from_response(data, url):
    """Extract recipe IDs from API response data."""
    ids = []
    
    def search_for_ids(obj, path=""):
        """Recursively search for recipe IDs in nested data structures."""
        if isinstance(obj, dict):
            # Look for 'id' field that looks like a recipe ID
            if 'id' in obj:
                id_value = obj['id']
                if isinstance(id_value, (int, str)) and str(id_value).isdigit():
                    # Additional context clues that this might be a recipe
                    if any(key in obj for key in ['name', 'title', 'recipe', 'ingredient', 'direction']):
                        ids.append(str(id_value))
            
            # Recursively search nested objects
            for key, value in obj.items():
                search_for_ids(value, f"{path}.{key}" if path else key)
                
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                search_for_ids(item, f"{path}[{i}]")
    
    search_for_ids(data)
    return ids

def load_existing_ids(ids_file):
    """Load existing recipe IDs from file if it exists."""
    if not ids_file.exists():
        return set()
    
    ids = set()
    with open(ids_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and line.isdigit():
                ids.add(line)
    return ids

def save_ids(ids_file, recipe_ids):
    """Save recipe IDs to file, sorted for consistent output."""
    ids_file.parent.mkdir(parents=True, exist_ok=True)
    with open(ids_file, 'w') as f:
        for recipe_id in sorted(recipe_ids, key=int):
            f.write(f"{recipe_id}\n")

def main():
    parser = argparse.ArgumentParser(description="Extract Ekomenu recipe IDs from API calls")
    parser.add_argument("--start-date", default="2023-10-02", 
                       help="Start date (YYYY-MM-DD, default: 2023-10-02)")
    parser.add_argument("--end-date", default=None,
                       help="End date (YYYY-MM-DD, default: current date)")
    parser.add_argument("--output", "-o", default="recipe_ids.txt",
                       help="Output file for recipe IDs (default: recipe_ids.txt)")
    parser.add_argument("--use-state", 
                       help="Path to saved session state for login")
    parser.add_argument("--save-state",
                       help="Path to save session state after login")
    parser.add_argument("--email", help="Ekomenu email")
    parser.add_argument("--password", help="Ekomenu password")
    parser.add_argument("--headful", action="store_true", 
                       help="Run browser in non-headless mode")
    parser.add_argument("--incremental", action="store_true",
                       help="Only collect new IDs (skip existing ones)")
    
    args = parser.parse_args()
    
    # Get credentials
    email = args.email or os.getenv("EKOMENU_EMAIL")
    password = args.password or os.getenv("EKOMENU_PASSWORD")
    
    if not email or not password:
        print("Error: Missing credentials. Use --email/--password or set EKOMENU_EMAIL/EKOMENU_PASSWORD", 
              file=sys.stderr)
        sys.exit(1)
    
    ids_file = Path(args.output)
    existing_ids = load_existing_ids(ids_file) if args.incremental else set()
    all_ids = existing_ids.copy()
    
    # Generate date range
    dates = generate_date_range(args.start_date, args.end_date)
    print(f"Processing {len(dates)} weekly dates from {dates[0]} to {dates[-1]}")
    
    if args.incremental and existing_ids:
        print(f"Incremental mode: Starting with {len(existing_ids)} existing IDs")
    
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headful)
        
        # Set up browser context
        ctx_kwargs = {}
        if args.use_state:
            ctx_kwargs["storage_state"] = args.use_state
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()
        
        # Login if needed
        if not args.use_state:
            page.goto("https://www.ekomenu.nl/login", wait_until="domcontentloaded")
            dismiss_cookiebot(page)
            
            page.fill("input[type='email']", email)
            page.fill("input[type='password']", password)
            page.click("button:has-text('Inloggen')")
            page.wait_for_load_state("networkidle", timeout=15000)
            
            if "login" in page.url:
                print("Login failed - still on login page")
                sys.exit(1)
                
            if args.save_state:
                context.storage_state(path=args.save_state)
                print(f"Session state saved to {args.save_state}")
        
        # Extract all recipe IDs by clicking through available dates
        new_ids_count = 0
        extracted_ids = extract_all_recipe_ids(page)
        
        # Add new IDs
        for recipe_id in extracted_ids:
            if recipe_id not in all_ids:
                all_ids.add(recipe_id)
                new_ids_count += 1
        
        context.close()
        browser.close()
    
    # Save results
    save_ids(ids_file, all_ids)
    
    print(f"\nCompleted!")
    print(f"Total recipe IDs found: {len(all_ids)}")
    print(f"New IDs added: {new_ids_count}")
    print(f"IDs saved to: {ids_file}")
    
    # Optionally convert to URLs
    if len(all_ids) > 0:
        urls_file = ids_file.with_suffix('.urls.txt')
        with open(urls_file, 'w') as f:
            for recipe_id in sorted(all_ids, key=int):
                f.write(f"https://www.ekomenu.nl/user?recipe={recipe_id}\n")
        print(f"URLs saved to: {urls_file}")

if __name__ == "__main__":
    main()