# dependencies: pip install playwright supabase && playwright install chromium
# Run: python scripts/manheim_scraper.py
# Flow: Post-Sale Results → 5 CA Manheim locations → SHOW ALL → paginate → Supabase

from playwright.sync_api import sync_playwright
from supabase import create_client
import time

CSV_FILE = 'scripts/manheim_postsale_export.csv'  # local backup
URL_POSTSALE = 'https://www.manheim.com/postsale'

# Supabase config
SUPABASE_URL = 'https://lbnxzvqppccajllsqaaw.supabase.co'
SUPABASE_KEY = 'SUPABASE_SERVICE_ROLE_KEY_REDACTED'
BATCH_SIZE = 100  # insert 100 rows at a time

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


def clean_price(val):
    """Convert '$12,500' → 12500.0"""
    try:
        return float(val.replace('$', '').replace(',', '').strip())
    except:
        return None


def clean_odo(val):
    """Convert '45,231' → 45231"""
    try:
        return int(val.replace(',', '').strip())
    except:
        return None


def clean_year(val):
    try:
        y = int(val.strip())
        return y if 1980 <= y <= 2030 else None
    except:
        return None


def rows_to_records(rows_raw, location):
    """Convert raw cell data to Supabase dealer_sales records."""
    records = []
    for data in rows_raw:
        while len(data) < 14:
            data.append('')
        record = {
            'year':             clean_year(data[0]),
            'make':             data[1].strip() or None,
            'model':            data[2].strip() or None,
            'trim':             data[3].strip() or None,   # subseries/color
            'color':            data[4].strip() or None,
            'doors':            data[5].strip() or None,
            'cylinders':        data[6].strip() or None,
            'fuel_type':        data[7].strip() or None,
            'transmission':     data[8].strip() or None,
            'drive_type':       data[9].strip() or None,
            'odometer':         clean_odo(data[12]),
            'sale_price':       clean_price(data[13]),
            'auction_location': location,
            'source':           'manheim_postsale',
        }
        if record['make'] and record['model']:
            records.append(record)
    return records


def scrape_table_page(page):
    """Scrape all rows from the current visible table. Returns list of raw cell data."""
    rows_data = []
    try:
        page.wait_for_selector('table tbody tr', timeout=10000)
    except Exception:
        return rows_data

    rows = page.query_selector_all('table tbody tr')
    for row in rows:
        try:
            cells = row.query_selector_all('td')
            data = [safe_text(c) for c in cells]
            if any(data[:3]):
                rows_data.append(data)
        except Exception:
            continue
    return rows_data


def flush_to_supabase(supabase, batch, csv_writer, total_rows):
    """Insert batch to Supabase + write to CSV backup."""
    if not batch:
        return total_rows
    try:
        supabase.table('dealer_sales').upsert(batch, on_conflict='vin,sale_date').execute()
    except Exception as e:
        # Non-fatal: log and continue
        print(f'  Supabase insert warning: {e}')
    for rec in batch:
        csv_writer.writerow([
            rec.get('year',''), rec.get('make',''), rec.get('model',''),
            rec.get('trim',''), rec.get('color',''), rec.get('doors',''),
            rec.get('cylinders',''), rec.get('fuel_type',''), rec.get('transmission',''),
            rec.get('drive_type',''), rec.get('odometer',''), rec.get('sale_price',''),
            rec.get('auction_location','')
        ])
    total_rows += len(batch)
    if total_rows % 500 == 0:
        print(f'  → {total_rows} rows saved to Supabase...')
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

        # Init Supabase
        print('\nConnecting to Supabase...')
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print('✅ Supabase connected\n')

        import csv as csv_mod
        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
            csv_writer = csv_mod.writer(csvfile)
            csv_writer.writerow([
                'year', 'make', 'model', 'trim', 'color', 'doors', 'cyl', 'fuel',
                'trans', 'drive', 'odometer', 'sale_price', 'auction_location'
            ])

            total_rows = 0
            start_time = time.time()
            batch = []

            for location in CA_LOCATIONS:
                print(f'\n{"="*40}')
                print(f'LOCATION: {location}')
                print(f'{"="*40}')

                page.goto(URL_POSTSALE)
                page.wait_for_load_state('networkidle')
                time.sleep(2)

                try:
                    loc_link = page.locator(f'a:has-text("{location}")').first
                    loc_link.click()
                    page.wait_for_load_state('networkidle')
                    time.sleep(2)
                    print(f'✅ {location} selected')
                except Exception as e:
                    print(f'Could not find "{location}": {e} — skipping')
                    continue

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
                    print(f'No SHOW button: {e}')
                    print('Click SHOW VEHICLES manually then press Enter.')
                    input()

                page_num = 0
                loc_rows = 0

                while True:
                    page_num += 1
                    raw_rows = scrape_table_page(page)
                    records = rows_to_records(raw_rows, location)
                    batch.extend(records)
                    loc_rows += len(records)

                    # Flush batch to Supabase every BATCH_SIZE rows
                    if len(batch) >= BATCH_SIZE:
                        total_rows = flush_to_supabase(supabase, batch, csv_writer, total_rows)
                        csvfile.flush()
                        batch = []

                    print(f'  Page {page_num}: +{len(records)} rows | location total: {loc_rows}')

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
                            print(f'  ✅ {location} done: {loc_rows} vehicles')
                            break
                    except Exception as e:
                        print(f'  Pagination ended: {e}')
                        break

            # Flush remaining batch
            if batch:
                total_rows = flush_to_supabase(supabase, batch, csv_writer, total_rows)

        elapsed = int((time.time() - start_time) / 60)
        browser.close()
        print(f'\n========================================')
        print(f'ALL 5 CA LOCATIONS COMPLETE in {elapsed} minutes.')
        print(f'Total rows in Supabase: {total_rows}')
        print(f'CSV backup: {CSV_FILE}')
        print(f'========================================')


if __name__ == '__main__':
    run()
