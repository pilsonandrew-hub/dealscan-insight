# dependencies: pip install playwright && playwright install chromium
# Run: python scripts/manheim_scraper.py
# Flow: Post-Sale Results → Manheim California → SHOW ALL VEHICLES → paginate CSV

from playwright.sync_api import sync_playwright
import csv
import time

CSV_FILE = 'scripts/manheim_postsale_export.csv'
URL_POSTSALE = 'https://www.manheim.com/postsale'

# All California Manheim auction locations
CA_LOCATIONS = [
    'Manheim California',
    'Manheim Los Angeles',
    'Manheim San Francisco Bay',
    'Manheim Fresno',
    'Manheim San Diego',
]


def safe_text(el):
    try:
        return el.inner_text().strip()
    except:
        return ''


def scrape_table_with_location(page, writer, total_rows, location=''):
    """Scrape current table page, appending location column. Returns updated total_rows count."""
    try:
        page.wait_for_selector('table tbody tr', timeout=10000)
    except Exception:
        return total_rows

    rows = page.query_selector_all('table tbody tr')
    for row in rows:
        try:
            cells = row.query_selector_all('td')
            data = [safe_text(c) for c in cells]
            while len(data) < 14:
                data.append('')
            if any(data[:3]):  # skip blank rows
                writer.writerow(data[:14] + [location])
                total_rows += 1
                if total_rows % 500 == 0:
                    print(f'  → {total_rows} total rows...')
        except Exception:
            continue
    return total_rows


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

        print('\nNavigating to Post-Sale Results...')
        page.goto(URL_POSTSALE)
        page.wait_for_load_state('networkidle')
        time.sleep(2)

        page.screenshot(path='scripts/manheim_debug.png')
        print('Debug screenshot saved.\n')

        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'year', 'make', 'model', 'color', 'doors', 'cyl', 'fuel',
                'trans', '4x4', 'radio', 'interior', 'odometer', 'price', 'col14',
                'auction_location'
            ])

            total_rows = 0
            start_time = time.time()

            for location in CA_LOCATIONS:
                print(f'\n{"="*40}')
                print(f'LOCATION: {location}')
                print(f'{"="*40}')

                # Go back to main postsale page
                page.goto(URL_POSTSALE)
                page.wait_for_load_state('networkidle')
                time.sleep(2)

                # Click the location
                try:
                    loc_link = page.locator(f'a:has-text("{location}")').first
                    loc_link.click()
                    page.wait_for_load_state('networkidle')
                    time.sleep(2)
                    print(f'✅ {location} selected')
                except Exception as e:
                    print(f'Could not find "{location}": {e} — skipping')
                    continue

                # Click SHOW ALL VEHICLES button (no filters)
                try:
                    show_btn = page.locator(
                        'button:has-text("SHOW"), a:has-text("SHOW"), '
                        'button:has-text("Show"), button:has-text("vehicles")'
                    ).first
                    btn_text = show_btn.inner_text()
                    print(f'Clicking: "{btn_text}"')
                    show_btn.click()
                    page.wait_for_load_state('networkidle')
                    time.sleep(3)
                except Exception as e:
                    print(f'No SHOW button found: {e}')
                    print(f'Click the SHOW button for {location} manually, then press Enter.')
                    input()

                # Paginate and scrape all results
                page_num = 0
                loc_rows = 0
                while True:
                    page_num += 1
                    before = total_rows
                    total_rows = scrape_table_with_location(page, writer, total_rows, location)
                    loc_rows += total_rows - before
                    print(f'  Page {page_num}: +{total_rows - before} rows (location total: {loc_rows})')
                    csvfile.flush()

                    try:
                        next_btn = page.query_selector(
                            'a:has-text("Next"), button:has-text("Next"), '
                            '[aria-label="Next page"], [aria-label="Next"], '
                            '.pagination .next a, li.next a'
                        )
                        if next_btn and not next_btn.is_disabled():
                            next_btn.click()
                            page.wait_for_load_state('networkidle')
                            time.sleep(1.5)
                        else:
                            print(f'  ✅ {location} complete: {loc_rows} vehicles')
                            break
                    except Exception as e:
                        print(f'  Pagination ended: {e}')
                        break

        elapsed = int((time.time() - start_time) / 60)
        browser.close()
        print(f'\n========================================')
        print(f'ALL 5 CA LOCATIONS COMPLETE in {elapsed} minutes.')
        print(f'Total rows: {total_rows}')
        print(f'Saved to: {CSV_FILE}')
        print(f'========================================')


if __name__ == '__main__':
    run()
