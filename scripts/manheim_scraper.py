# dependencies: pip install playwright && playwright install chromium
# Run: python scripts/manheim_scraper.py
from playwright.sync_api import sync_playwright
import csv
import time

CSV_FILE = 'scripts/manheim_postsale_export.csv'
URL_POSTSALE = 'https://www.manheim.com/postsale?auctionAccessNumber=5500030'


def safe_text(el):
    try:
        return el.inner_text().strip()
    except:
        return ''


def scrape_current_table(page):
    """Scrape all rows from the current vehicle results table, handling Next page."""
    rows_data = []
    while True:
        try:
            page.wait_for_selector('table tbody tr', timeout=10000)
        except Exception:
            break

        rows = page.query_selector_all('table tbody tr')
        for row in rows:
            try:
                cells = row.query_selector_all('td')
                # Real Manheim columns: Year, Make, Model, Subseries, Color, Drs, Cyl, Fuel, Trans, 4x4, Radio, Int, Odometer, Price
                year         = safe_text(cells[0])  if len(cells) > 0  else ''
                make         = safe_text(cells[1])  if len(cells) > 1  else ''
                model        = safe_text(cells[2])  if len(cells) > 2  else ''
                subseries    = safe_text(cells[3])  if len(cells) > 3  else ''
                color        = safe_text(cells[4])  if len(cells) > 4  else ''
                doors        = safe_text(cells[5])  if len(cells) > 5  else ''
                cyl          = safe_text(cells[6])  if len(cells) > 6  else ''
                fuel         = safe_text(cells[7])  if len(cells) > 7  else ''
                transmission = safe_text(cells[8])  if len(cells) > 8  else ''
                drive_4x4    = safe_text(cells[9])  if len(cells) > 9  else ''
                radio        = safe_text(cells[10]) if len(cells) > 10 else ''
                interior     = safe_text(cells[11]) if len(cells) > 11 else ''
                odometer     = safe_text(cells[12]) if len(cells) > 12 else ''
                price        = safe_text(cells[13]) if len(cells) > 13 else ''
            except Exception:
                year = make = model = subseries = color = doors = cyl = fuel = ''
                transmission = drive_4x4 = radio = interior = odometer = price = ''

            rows_data.append([year, make, model, subseries, color, doors, cyl, fuel,
                               transmission, drive_4x4, radio, interior, odometer, price])

        # Handle Next page button
        try:
            next_btn = page.query_selector('a:has-text("Next"), button:has-text("Next"), [aria-label="Next"]')
            if next_btn and not next_btn.is_disabled():
                next_btn.click()
                time.sleep(2)
                page.wait_for_load_state('networkidle')
            else:
                break
        except Exception:
            break

    return rows_data


def set_view_all(page):
    """Try to set the View dropdown to show ALL makes instead of filtered by make."""
    try:
        # Find the View dropdown (shows "ACURA (11)" etc.)
        dropdown = page.query_selector('select, [role="combobox"]')
        if dropdown:
            # Try selecting the first/all option
            options = page.query_selector_all('option, [role="option"]')
            for opt in options:
                text = safe_text(opt)
                if 'all' in text.lower() or text == '' or 'show all' in text.lower():
                    opt.click()
                    time.sleep(1)
                    return True
            # If no "all" option, try selecting the dropdown and choosing first item
            page.select_option('select', index=0)
            time.sleep(1)
            return True
    except Exception:
        pass
    return False


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto('https://www.manheim.com')
        print('========================================')
        print('LOG IN to Manheim in the browser window.')
        print('When fully logged in, press Enter here.')
        print('========================================')
        input()

        print('Navigating to post-sale page...')
        page.goto(URL_POSTSALE)
        page.wait_for_load_state('networkidle')
        time.sleep(2)

        # Collect all date links from LEFT SIDEBAR
        print('Collecting date links from sidebar...')
        date_links = page.eval_on_selector_all(
            'a:has-text("View Post-Sale Results (Enhanced)"), aside a, nav a, .sidebar a, [class*="side"] a, [class*="date"] a',
            'els => els.map(el => ({text: el.innerText.trim(), href: el.href}))'
        )

        # Also try getting all links that look like date result links
        if not date_links:
            date_links = page.eval_on_selector_all(
                'a[href*="postsale"]',
                'els => els.map(el => ({text: el.innerText.trim(), href: el.href}))'
            )

        # Filter to unique hrefs only
        seen = set()
        unique_links = []
        for l in date_links:
            if l['href'] not in seen and l['href'] != URL_POSTSALE:
                seen.add(l['href'])
                unique_links.append(l)

        if not unique_links:
            print('No date links found. Taking screenshot for debugging...')
            page.screenshot(path='scripts/manheim_debug.png')
            print('Screenshot saved to scripts/manheim_debug.png')
            browser.close()
            return

        print(f'Found {len(unique_links)} date pages to scrape.')

        # Prepare CSV
        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['year', 'make', 'model', 'subseries', 'color', 'doors',
                             'cyl', 'fuel', 'transmission', 'drive_4x4', 'radio',
                             'interior', 'odometer', 'price', 'sale_date'])

            total_rows = 0

            for i, link in enumerate(unique_links):
                sale_date = link['text']
                href = link['href']
                print(f'\n[{i+1}/{len(unique_links)}] {sale_date}')

                try:
                    page.goto(href)
                    page.wait_for_load_state('networkidle')
                    time.sleep(1)

                    # Try to set View to ALL makes
                    set_view_all(page)

                    rows = scrape_current_table(page)
                    for row in rows:
                        writer.writerow(row + [sale_date])
                        total_rows += 1
                        if total_rows % 100 == 0:
                            print(f'  → {total_rows} total rows so far...')

                    print(f'  → {len(rows)} vehicles from {sale_date}')
                    csvfile.flush()

                except Exception as e:
                    print(f'  ERROR: {e} — skipping this date')
                    continue

        browser.close()
        print(f'\n========================================')
        print(f'COMPLETE. Total rows: {total_rows}')
        print(f'Saved to: {CSV_FILE}')
        print(f'========================================')


if __name__ == '__main__':
    run()
