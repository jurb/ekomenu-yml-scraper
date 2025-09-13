#!/usr/bin/env -S uv run --script --with playwright
"""
Scrape all recipe URLs from Ekomenu weekly pages.
Generates a list of all recipe URLs from subscription start date to current week.
Supports incremental updates to only add new recipes.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

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
    # Parse start date
    start = datetime.strptime(start_date, "%Y-%m-%d")
    
    # Use current date if no end date specified
    if end_date is None:
        end = datetime.now()
    else:
        end = datetime.strptime(end_date, "%Y-%m-%d")
    
    # Generate weekly dates (every Monday)
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(weeks=1)
    
    return dates

def scrape_weekly_recipes(page, date):
    """Scrape all recipe URLs from a specific weekly page."""
    url = f"https://www.ekomenu.nl/user?date={date}"
    print(f"Scraping {date}...")
    
    try:
        page.goto(url, wait_until="domcontentloaded")
        dismiss_cookiebot(page)
        
        # Check if we got redirected (no delivery for this date)
        final_url = page.url
        if f"date={date}" not in final_url:
            print(f"  No delivery for {date} - redirected to {final_url}")
            return []
        
        # Wait for page to be fully loaded 
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PWTimeout:
            # If networkidle times out, just continue
            pass
        page.wait_for_timeout(3000)
        
        # Also try to dismiss specific popup links globally
        popup_dismiss_selectors = [
            "a:has-text('Laat deze popup niet meer zien op dit apparaat')",
            "button:has-text('Laat deze popup niet meer zien')",
            "a:has-text('Niet meer tonen')"
        ]
        
        for dismiss_sel in popup_dismiss_selectors:
            try:
                if page.locator(dismiss_sel).count():
                    page.locator(dismiss_sel).first.click(timeout=2000)
                    page.wait_for_timeout(1000)
                    print(f"  Dismissed popup using: {dismiss_sel}")
            except:
                continue
        
        # Check for and dismiss any modal popups
        modal_selectors = [
            "ngb-modal-window",
            ".modal.show",
            ".modal.fade.show",
            "[role='dialog']"
        ]
        
        for modal_sel in modal_selectors:
            try:
                modal = page.locator(modal_sel)
                if modal.count() and modal.first.is_visible():
                    print(f"  Dismissing modal: {modal_sel}")
                    # Try pressing Escape to close modal
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(1000)
                    
                    # If still visible, try clicking close buttons
                    close_buttons = [
                        f"{modal_sel} button:has-text('×')",
                        f"{modal_sel} .close", 
                        f"{modal_sel} [aria-label='Close']",
                        "a:has-text('Laat deze popup niet meer zien op dit apparaat')",
                        "button:has-text('Laat deze popup niet meer zien')"
                    ]
                    
                    for close_btn in close_buttons:
                        try:
                            if page.locator(close_btn).count():
                                page.locator(close_btn).first.click(timeout=2000)
                                page.wait_for_timeout(1000)
                                break
                        except:
                            continue
                    break
            except:
                continue
        
        # Find all "Toon recept" buttons
        recipe_buttons = page.locator('a:has-text("Toon recept")')
        button_count = recipe_buttons.count()
        
        if button_count == 0:
            print(f"  No recipes found for {date}")
            return []
        
        print(f"  Found {button_count} recipes")
        recipe_urls = []
        
        # Click each button and collect the resulting URLs
        for i in range(button_count):
            try:
                # Dismiss any potential modals first
                dismiss_cookiebot(page)
                
                # Try clicking modal close buttons if they exist
                modal_close_selectors = [
                    "button:has-text('×')",
                    "button[aria-label='Close']",
                    ".modal .close",
                    ".modal-close",
                    "ngb-modal-window button"
                ]
                
                for close_sel in modal_close_selectors:
                    try:
                        close_btn = page.locator(close_sel)
                        if close_btn.count() and close_btn.first.is_visible():
                            close_btn.first.click(timeout=1000)
                            page.wait_for_timeout(500)
                            break
                    except:
                        continue
                
                # Get button again (DOM might have changed) and ensure we click the right one
                buttons = page.locator('a:has-text("Toon recept")')
                if i < buttons.count():
                    # Try to scroll the specific button into view first
                    try:
                        buttons.nth(i).scroll_into_view_if_needed()
                        page.wait_for_timeout(500)
                    except:
                        pass
                        
                    # Try force clicking if normal click fails
                    try:
                        buttons.nth(i).click(timeout=3000)
                    except PWTimeout:
                        # Force click with JavaScript, being more specific about which button
                        page.evaluate(f"""
                            const buttons = Array.from(document.querySelectorAll('a')).filter(a => 
                                a.textContent && a.textContent.includes('Toon recept')
                            );
                            if (buttons[{i}]) {{
                                buttons[{i}].click();
                            }}
                        """)
                    
                    page.wait_for_timeout(1000)  # Wait for URL change
                    
                    # Check if URL changed to include recipe parameter
                    current_url = page.url
                    if "recipe=" in current_url:
                        # Extract recipe ID and construct proper URL with original date
                        import re
                        recipe_match = re.search(r'recipe=(\d+)', current_url)
                        if recipe_match:
                            recipe_id = recipe_match.group(1)
                            # Construct URL with original date
                            proper_url = f"https://www.ekomenu.nl/user?date={date}&recipe={recipe_id}"
                            recipe_urls.append(proper_url)
                            print(f"    Recipe {i+1}: {proper_url}")
                        else:
                            print(f"    Recipe {i+1}: Could not extract recipe ID from {current_url}")
                        
                        # Navigate back to the weekly page for next recipe
                        page.goto(url, wait_until="domcontentloaded")
                        dismiss_cookiebot(page)  # Dismiss any popups again
                        page.wait_for_timeout(2000)  # Wait longer for page to stabilize
                    else:
                        print(f"    Recipe {i+1}: No URL change detected")
                        
            except Exception as e:
                print(f"    Recipe {i+1}: Error - {e}")
                continue
        
        return recipe_urls
        
    except Exception as e:
        print(f"  Error scraping {date}: {e}")
        return []

def load_existing_urls(urls_file):
    """Load existing URLs from file if it exists."""
    if not urls_file.exists():
        return set()
    
    urls = set()
    with open(urls_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and line.startswith('https://'):
                urls.add(line)
    return urls

def save_urls(urls_file, urls):
    """Save URLs to file, sorted for consistent output."""
    urls_file.parent.mkdir(parents=True, exist_ok=True)
    with open(urls_file, 'w') as f:
        for url in sorted(urls):
            f.write(f"{url}\n")

def main():
    parser = argparse.ArgumentParser(description="Scrape Ekomenu recipe URLs from weekly pages")
    parser.add_argument("--start-date", default="2023-10-02", 
                       help="Start date (YYYY-MM-DD, default: 2023-10-02)")
    parser.add_argument("--end-date", default=None,
                       help="End date (YYYY-MM-DD, default: current date)")
    parser.add_argument("--output", "-o", default="recipe_urls.txt",
                       help="Output file for recipe URLs (default: recipe_urls.txt)")
    parser.add_argument("--use-state", 
                       help="Path to saved session state for login")
    parser.add_argument("--save-state",
                       help="Path to save session state after login")
    parser.add_argument("--email", help="Ekomenu email")
    parser.add_argument("--password", help="Ekomenu password")
    parser.add_argument("--headful", action="store_true", 
                       help="Run browser in non-headless mode")
    parser.add_argument("--incremental", action="store_true",
                       help="Only scrape new URLs (skip dates already processed)")
    
    args = parser.parse_args()
    
    # Get credentials
    email = args.email or os.getenv("EKOMENU_EMAIL")
    password = args.password or os.getenv("EKOMENU_PASSWORD")
    
    if not email or not password:
        print("Error: Missing credentials. Use --email/--password or set EKOMENU_EMAIL/EKOMENU_PASSWORD", 
              file=sys.stderr)
        sys.exit(1)
    
    urls_file = Path(args.output)
    existing_urls = load_existing_urls(urls_file) if args.incremental else set()
    all_urls = existing_urls.copy()
    
    # Generate date range
    dates = generate_date_range(args.start_date, args.end_date)
    print(f"Processing {len(dates)} weekly dates from {dates[0]} to {dates[-1]}")
    
    if args.incremental and existing_urls:
        print(f"Incremental mode: Starting with {len(existing_urls)} existing URLs")
    
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headful)
        
        # Set up browser context
        ctx_kwargs = {}
        if args.use_state:
            ctx_kwargs["storage_state"] = args.use_state
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()
        
        # Login if needed (reuse logic from main scraper)
        if not args.use_state:
            # Simple login - navigate to login page
            page.goto("https://www.ekomenu.nl/login", wait_until="domcontentloaded")
            dismiss_cookiebot(page)
            
            # Fill credentials
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
        
        # Process each weekly date
        new_urls_count = 0
        for date in dates:
            weekly_urls = scrape_weekly_recipes(page, date)
            
            # Add new URLs
            for url in weekly_urls:
                if url not in all_urls:
                    all_urls.add(url)
                    new_urls_count += 1
        
        context.close()
        browser.close()
    
    # Save results
    save_urls(urls_file, all_urls)
    
    print(f"\nCompleted!")
    print(f"Total URLs found: {len(all_urls)}")
    print(f"New URLs added: {new_urls_count}")
    print(f"URLs saved to: {urls_file}")

if __name__ == "__main__":
    main()