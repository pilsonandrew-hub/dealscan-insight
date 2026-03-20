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


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # visible browser
        context = browser.new_context()
        page = context.new_page()

        page.goto(URL_MANHEIM)
        print('LOG IN NOW then press Enter when done')
        input()

        print(f'Navigating to post-sale results page...')
        page.goto(URL_POSTSALE)
        page.wait_for_load_state('networkidle')

        # Collect ALL "View Post-Sale Results (Enhanced)" hrefs first
        print('Collecting Enhanced result links...')
        enhanced_links = page.eval_on_selector_all(
            'a:has-text("View Post-Sale Results (Enhanced)")',
            'els => els.map(el => el.href)'
        )

        if not enhanced_links:
            print('ERROR: No "View Post-Sale Results (Enhanced)" links found. Check that you are logged in and on the right page.')
            browser.close()
            return

        print(f'Found {len(enhanced_links)} date links to process.')

        # Prepare CSV
        csvfile = open(CSV_FILE, mode='w', newline='', encoding='utf-8')
        csvwriter = csv.writer(csvfile)
        headers = ['year', 'make', 'model', 'subseries', 'odo', 'sale_price', 'drivetrain', 'transmission', 'sale_date', 'vin']
        csvwriter.writerow(headers)

        total_rows = 0

        for i, href in enumerate(enhanced_links):
            print(f'Processing link {i + 1}/{len(enhanced_links)}: {href}')
            try:
                page.goto(href)
                page.wait_for_load_state('networkidle')

                # Wait for table to appear
                try:
                    page.wait_for_selector('table tbody tr', timeout=15000)
                except Exception:
                    print(f'  No table found at {href}, skipping.')
                    continue

                rows = page.query_selector_all('table tbody tr')
                link_rows = 0

                for row in rows:
                    try:
                        cells = row.query_selector_all('td')
                        year        = safe_text(cells[0]) if len(cells) > 0 else ''
                        make        = safe_text(cells[1]) if len(cells) > 1 else ''
                        model       = safe_text(cells[2]) if len(cells) > 2 else ''
                        subseries   = safe_text(cells[3]) if len(cells) > 3 else ''
                        odo         = safe_text(cells[4]) if len(cells) > 4 else ''
                        sale_price  = safe_text(cells[5]) if len(cells) > 5 else ''
                        drivetrain  = safe_text(cells[6]) if len(cells) > 6 else ''
                        transmission = safe_text(cells[7]) if len(cells) > 7 else ''
                        sale_date   = safe_text(cells[8]) if len(cells) > 8 else ''
                        vin         = safe_text(cells[9]) if len(cells) > 9 else ''
                    except Exception:
                        year = make = model = subseries = odo = sale_price = drivetrain = transmission = sale_date = vin = ''

                    csvwriter.writerow([year, make, model, subseries, odo, sale_price, drivetrain, transmission, sale_date, vin])
                    total_rows += 1
                    link_rows += 1

                    if total_rows % 100 == 0:
                        print(f'  {total_rows} rows collected so far...')

                print(f'  Collected {link_rows} rows from this date.')

            except Exception as e:
                print(f'  Error processing {href}: {e}')
                continue

        csvfile.close()
        browser.close()

        print(f'Scraping complete. Total rows collected: {total_rows}')
        print(f'Data saved to: {CSV_FILE}')


if __name__ == '__main__':
    run()
