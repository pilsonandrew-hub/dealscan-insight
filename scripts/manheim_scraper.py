# dependencies: pip install playwright && playwright install chromium
from playwright.sync_api import sync_playwright
import csv
import time

CSV_FILE = 'scripts/manheim_postsale_export.csv'
URL_MANHEIM = 'https://www.manheim.com'
URL_POSTSALE = 'https://www.manheim.com/members/reports/postsale'


# Helper to safely get text or empty string

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

        page.goto(URL_POSTSALE)

        # Set Filters: last year for date range and CA - Manheim California for auction
        try:
            # Open date range dropdown
            page.click("button:has-text('Date Range')")
            # Select Last Year
            page.click("button[role='option']:has-text('Last Year')")
            time.sleep(1)
        except Exception as e:
            print(f'Warning: Failed to set Last Year date range filter: {e}')

        try:
            # Auction filter dropdown
            page.click("button:has-text('Auction Location')")
            time.sleep(1)
            # Find option for CA - Manheim California by location id or text
            auctions = page.query_selector_all("button[role='option']")
            found = False
            for auction in auctions:
                text = auction.inner_text()
                if 'CA - Manheim California' in text or '5500030' in text:
                    auction.click()
                    found = True
                    break
            if not found:
                print('Warning: Could not find CA - Manheim California auction location filter')
            else:
                time.sleep(1)
        except Exception as e:
            print(f'Warning: Failed to set auction location filter: {e}')

        # Prepare CSV writer
        csvfile = open(CSV_FILE, mode='w', newline='', encoding='utf-8')
        csvwriter = csv.writer(csvfile)
        headers = ['year', 'make', 'model', 'subseries', 'odo', 'sale_price', 'drivetrain', 'transmission', 'sale_date', 'vin']
        csvwriter.writerow(headers)

        total_rows = 0
        try:
            while True:
                # Wait for table rows load
                page.wait_for_selector('table tbody tr')
                rows = page.query_selector_all('table tbody tr')
                if not rows:
                    print('No rows found on this page, stopping pagination.')
                    break

                for row in rows:
                    try:
                        cells = row.query_selector_all('td')
                        # Map cells to fields conservatively
                        year = safe_text(cells[0]) if len(cells) > 0 else ''
                        make = safe_text(cells[1]) if len(cells) > 1 else ''
                        model = safe_text(cells[2]) if len(cells) > 2 else ''
                        subseries = safe_text(cells[3]) if len(cells) > 3 else ''
                        odo = safe_text(cells[4]) if len(cells) > 4 else ''
                        sale_price = safe_text(cells[5]) if len(cells) > 5 else ''
                        drivetrain = safe_text(cells[6]) if len(cells) > 6 else ''
                        transmission = safe_text(cells[7]) if len(cells) > 7 else ''
                        sale_date = safe_text(cells[8]) if len(cells) > 8 else ''
                        vin = safe_text(cells[9]) if len(cells) > 9 else ''
                    except Exception:
                        # If row parsing fails, fill empty and continue
                        year = make = model = subseries = odo = sale_price = drivetrain = transmission = sale_date = vin = ''

                    csvwriter.writerow([year, make, model, subseries, odo, sale_price, drivetrain, transmission, sale_date, vin])
                    total_rows += 1

                    if total_rows % 100 == 0:
                        print(f'{total_rows} rows collected so far...')

                # Try to paginate to next page
                try:
                    next_button = page.query_selector('button[aria-label="Next"]')
                    if next_button and not next_button.is_disabled():
                        next_button.click()
                        time.sleep(3)  # wait for next page to load
                    else:
                        print('Reached last page or next button disabled.')
                        break

                except Exception as e:
                    print(f'Pagination failed: {e}')
                    break

        except Exception as e:
            print(f'Error during scraping: {e}')

        csvfile.close()
        browser.close()

        print(f'Scraping complete. Total rows collected: {total_rows}')
        print(f'Data saved to: {CSV_FILE}')


if __name__ == '__main__':
    run()
