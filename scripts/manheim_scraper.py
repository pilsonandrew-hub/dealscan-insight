# dependencies: pip install playwright && playwright install chromium
from playwright.sync_api import sync_playwright
import csv
import time

CSV_FILE = 'scripts/manheim_postsale_export.csv'
URL_MANHEIM = 'https://www.manheim.com'
URL_POSTSALE = 'https://www.manheim.com/postsale?auctionAccessNumber=5500030'


def safe_text(element):
    try:
        return element.inner_text().strip()
    except:
        return ''


def scrape_table_page(page):
    """Scrape all rows from a vehicle table, handling pagination within the page."""
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
                year         = safe_text(cells[0]) if len(cells) > 0 else ''
                make         = safe_text(cells[1]) if len(cells) > 1 else ''
                model        = safe_text(cells[2]) if len(cells) > 2 else ''
                subseries    = safe_text(cells[3]) if len(cells) > 3 else ''
                odo          = safe_text(cells[4]) if len(cells) > 4 else ''
                sale_price   = safe_text(cells[5]) if len(cells) > 5 else ''
                drivetrain   = safe_text(cells[6]) if len(cells) > 6 else ''
                transmission = safe_text(cells[7]) if len(cells) > 7 else ''
                sale_date    = safe_text(cells[8]) if len(cells) > 8 else ''
                vin          = safe_text(cells[9]) if len(cells) > 9 else ''
            except Exception:
                year = make = model = subseries = odo = sale_price = drivetrain = transmission = sale_date = vin = ''
            rows_data.append([year, make, model, subseries, odo, sale_price, drivetrain, transmission, sale_date, vin])

        # Check for "Next" pagination button within vehicle table
        try:
            next_btn = page.query_selector('button[aria-label="Next page"], a[aria-label="Next"], button:has-text("Next")')
            if next_btn and not next_btn.is_disabled():
                next_btn.click()
                time.sleep(2)
            else:
                break
        except Exception:
            break

    return rows_data


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # visible browser
        context = browser.new_context()
        page = context.new_page()

        page.goto(URL_MANHEIM)
        print('========================================')
        print('LOG IN to Manheim in the browser window.')
        print('When fully logged in, press Enter here.')
        print('========================================')
        input()

        print('Navigating to post-sale results page...')
        page.goto(URL_POSTSALE)
        page.wait_for_load_state('networkidle')
        time.sleep(2)

        # Collect all Enhanced links across ALL months by clicking "Previous Month" until none left
        all_enhanced_links = []
        months_visited = 0

        while True:
            try:
                links = page.eval_on_selector_all(
                    'a:has-text("View Post-Sale Results (Enhanced)")',
                    'els => els.map(el => el.href)'
                )
                new_links = [l for l in links if l not in all_enhanced_links]
                all_enhanced_links.extend(new_links)
                print(f'Month {months_visited + 1}: found {len(new_links)} new date links (total: {len(all_enhanced_links)})')
                months_visited += 1

                # Try clicking "Previous Month" or back arrow to get older data
                prev = page.query_selector('button:has-text("Previous"), a:has-text("Previous"), button[aria-label="Previous month"]')
                if prev and months_visited < 13:  # max 13 months back
                    prev.click()
                    page.wait_for_load_state('networkidle')
                    time.sleep(2)
                else:
                    break
            except Exception as e:
                print(f'Month navigation ended: {e}')
                break

        if not all_enhanced_links:
            print('ERROR: No "View Post-Sale Results (Enhanced)" links found.')
            print('Make sure you are logged in and on the right page.')
            browser.close()
            return

        print(f'\nTotal date links to process: {len(all_enhanced_links)}')
        print('Starting full scrape — runs automatically from here.\n')

        # Prepare CSV
        csvfile = open(CSV_FILE, mode='w', newline='', encoding='utf-8')
        csvwriter = csv.writer(csvfile)
        headers = ['year', 'make', 'model', 'subseries', 'odo', 'sale_price',
                   'drivetrain', 'transmission', 'sale_date', 'vin']
        csvwriter.writerow(headers)

        total_rows = 0

        for i, href in enumerate(all_enhanced_links):
            print(f'[{i + 1}/{len(all_enhanced_links)}] {href}')
            try:
                page.goto(href)
                page.wait_for_load_state('networkidle')
                time.sleep(1)

                rows_data = scrape_table_page(page)

                for row in rows_data:
                    csvwriter.writerow(row)
                    total_rows += 1
                    if total_rows % 100 == 0:
                        print(f'  → {total_rows} rows collected so far...')

                print(f'  → {len(rows_data)} rows from this date')
                csvfile.flush()  # save after each date page

            except Exception as e:
                print(f'  ERROR on {href}: {e} — skipping')
                continue

        csvfile.close()
        browser.close()

        print(f'\n========================================')
        print(f'DONE. Total rows collected: {total_rows}')
        print(f'File saved to: {CSV_FILE}')
        print(f'========================================')


if __name__ == '__main__':
    run()
