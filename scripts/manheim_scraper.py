# dependencies: pip install playwright && playwright install chromium
# Run: python scripts/manheim_scraper.py
# Flow: Post-Sale Results → Manheim California → SHOW ALL VEHICLES → paginate CSV

from playwright.sync_api import sync_playwright
import csv
import time

CSV_FILE = 'scripts/manheim_postsale_export.csv'
URL_POSTSALE = 'https://www.manheim.com/postsale'


def safe_text(el):
    try:
        return el.inner_text().strip()
    except:
        return ''


def scrape_table(page, writer, total_rows):
    """Scrape current table page. Returns updated total_rows count."""
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
                writer.writerow(data[:14])
                total_rows += 1
                if total_rows % 500 == 0:
                    print(f'  → {total_rows} rows collected...')
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

        # Step 1: Click "Manheim California" from the location list
        print('Selecting Manheim California...')
        try:
            ca_link = page.locator('a:has-text("Manheim California")').first
            ca_link.click()
            page.wait_for_load_state('networkidle')
            time.sleep(2)
            print('✅ Manheim California selected')
        except Exception as e:
            print(f'Could not click Manheim California: {e}')
            print('Please click "Manheim California" manually, then press Enter.')
            input()

        page.screenshot(path='scripts/manheim_debug2.png')

        # Step 2: Keep all filters as-is (Make=All, Model=All, Year=All)
        # and click the SHOW X VEHICLES button
        print('\nLooking for SHOW VEHICLES button...')
        try:
            # Find the orange SHOW button
            show_btn = page.locator('button:has-text("SHOW"), a:has-text("SHOW"), input[value*="SHOW"]').first
            if not show_btn:
                show_btn = page.locator('button:has-text("Show"), button:has-text("vehicles")').first

            btn_text = show_btn.inner_text()
            print(f'Found: "{btn_text}" — clicking...')
            show_btn.click()
            page.wait_for_load_state('networkidle')
            time.sleep(3)
            print('✅ Results loading...')
        except Exception as e:
            print(f'Could not find SHOW button: {e}')
            print('Please click the orange SHOW VEHICLES button manually, then press Enter.')
            input()

        page.screenshot(path='scripts/manheim_debug3.png')

        # Step 3: Scrape all results with full pagination
        print('\nStarting full scrape (all makes, all models, all dates)...')

        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)

            # Write headers based on what we know from screenshots
            writer.writerow([
                'year', 'make', 'model', 'color', 'doors', 'cyl', 'fuel',
                'trans', '4x4', 'radio', 'interior', 'odometer', 'price', 'col14'
            ])

            total_rows = 0
            page_num = 0
            start_time = time.time()

            while True:
                page_num += 1
                page.screenshot(path=f'scripts/manheim_page{page_num}.png') if page_num <= 3 else None

                total_rows = scrape_table(page, writer, total_rows)
                print(f'  Page {page_num}: {total_rows} total rows')
                csvfile.flush()

                # Try to go to next page
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
                        print('  No more pages.')
                        break
                except Exception as e:
                    print(f'  Pagination ended: {e}')
                    break

        elapsed = int((time.time() - start_time) / 60)
        browser.close()
        print(f'\n========================================')
        print(f'COMPLETE in {elapsed} minutes.')
        print(f'Total rows: {total_rows}')
        print(f'Saved to: {CSV_FILE}')
        print(f'========================================')


if __name__ == '__main__':
    run()
