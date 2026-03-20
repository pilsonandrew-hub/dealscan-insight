# dependencies: pip install playwright supabase && playwright install chromium
# Run: python scripts/manheim_scraper.py
# Flow: Location → sidebar dates → each date → each make → scrape table → Supabase

from playwright.sync_api import sync_playwright
from supabase import create_client
import csv as csv_mod
import time

CSV_FILE = 'scripts/manheim_postsale_export.csv'
URL_POSTSALE = 'https://www.manheim.com/postsale'

SUPABASE_URL = 'https://lbnxzvqppccajllsqaaw.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxibnh6dnFwcGNjYWpsbHNxYWF3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MzIwMTQ3MSwiZXhwIjoyMDg4Nzc3NDcxfQ.gLFMWuEVDbwMMHYL1CPRwNv1oGukhBTFYZGYTuXftSg'
BATCH_SIZE = 100

CA_LOCATIONS = [
    'Manheim California Anaheim',   # ⭐ MOST IMPORTANT
    'Manheim California',           # Santa Clarita
    'Manheim Los Angeles',
    'Manheim Riverside',
    'Manheim Fontana',
    'Manheim Southern California',  # Fontana / So Cal
    'Manheim Oceanside',
    'Manheim San Diego',
    'Manheim San Francisco Bay',
    'Manheim Fresno',
]

# Fallback make list if dropdown detection fails
KNOWN_MAKES_VALUES = [
    'ACURA','ALFA ROMEO','AUDI','BENTLEY','BMW','BUICK','CADILLAC',
    'CHEVROLET','CHRYSLER','DODGE','FIAT','FORD','GENESIS','GMC',
    'HONDA','HYUNDAI','INFINITI','JAGUAR','JEEP','KIA','LAND ROVER',
    'LEXUS','LINCOLN','MACK','MASERATI','MAZDA',
    'MERCEDES','MERCEDES B','MERCEDES-B',  # 3 variants seen in dropdown
    'MINI','MITSUBISHI','NISSAN','PONTIAC','PORSCHE','RAM','RIVIAN',
    'SAAB','SCION','SUBARU','TESLA','TOYOTA','VOLKSWAGEN','VOLVO'
]


def safe_text(el):
    try:
        return el.inner_text().strip()
    except:
        return ''


def clean_price(val):
    try:
        return float(val.replace('$','').replace(',','').strip())
    except:
        return None


def clean_odo(val):
    try:
        return int(val.replace(',','').strip())
    except:
        return None


def clean_year(val):
    try:
        y = int(val.strip())
        return y if 1980 <= y <= 2030 else None
    except:
        return None


def get_make_options(page):
    """Get all options from the View <select> dropdown."""
    try:
        sel = page.query_selector('select')
        if not sel:
            return []
        opts = sel.query_selector_all('option')
        results = []
        for opt in opts:
            val = opt.get_attribute('value') or ''
            txt = safe_text(opt)
            # Filter out blank/placeholder options
            if val and txt and val not in ('', '0', '-1', 'null'):
                results.append((val, txt))
        return results
    except Exception:
        return []


def scrape_table(page):
    """Scrape all rows from current table. Returns list of row dicts."""
    records = []
    try:
        page.wait_for_selector('table tbody tr', timeout=8000)
    except Exception:
        return records

    rows = page.query_selector_all('table tbody tr')
    for row in rows:
        try:
            cells = row.query_selector_all('td')
            data = [safe_text(c) for c in cells]
            while len(data) < 14:
                data.append('')
            if not any(data[:3]):
                continue
            records.append({
                'year':             clean_year(data[0]),
                'make':             data[1].strip() or None,
                'model':            data[2].strip() or None,
                'trim':             data[3].strip() or None,
                'color':            data[4].strip() or None,
                'doors':            data[5].strip() or None,
                'cylinders':        data[6].strip() or None,
                'fuel_type':        data[7].strip() or None,
                'transmission':     data[8].strip() or None,
                'drive_type':       data[9].strip() or None,
                'odometer':         clean_odo(data[12]),
                'sale_price':       clean_price(data[13]),
            })
        except Exception:
            continue
    return records


def flush_batch(supabase, batch, csv_writer, total_rows, location, sale_date):
    """Write batch to Supabase + CSV."""
    if not batch:
        return total_rows
    # Enrich with location + date
    for rec in batch:
        rec['auction_location'] = location
        rec['sale_date_label'] = sale_date
        rec['source'] = 'manheim_postsale'
    try:
        supabase.table('dealer_sales').insert(batch).execute()
    except Exception as e:
        print(f'  Supabase warning: {e}')
    for rec in batch:
        csv_writer.writerow([
            rec.get('year',''), rec.get('make',''), rec.get('model',''),
            rec.get('trim',''), rec.get('color',''), rec.get('doors',''),
            rec.get('cylinders',''), rec.get('fuel_type',''), rec.get('transmission',''),
            rec.get('drive_type',''), rec.get('odometer',''), rec.get('sale_price',''),
            location, sale_date
        ])
    total_rows += len(batch)
    if total_rows % 500 == 0:
        print(f'  → {total_rows} rows saved to Supabase...')
    return total_rows


def collect_sidebar_dates(page):
    """Get all date links from the List of Sales sidebar."""
    try:
        links = page.eval_on_selector_all(
            'a',
            '''els => els
                .map(el => ({text: el.innerText.trim(), href: el.href}))
                .filter(l =>
                    l.href.length > 0 &&
                    l.text.length > 4 &&
                    /\\b(january|february|march|april|may|june|july|august|september|october|november|december)\\b/i.test(l.text) &&
                    /20[0-9]{2}/.test(l.text)
                )
            '''
        )
        seen = set()
        unique = []
        for l in links:
            if l['href'] not in seen:
                seen.add(l['href'])
                unique.append(l)
        return unique
    except Exception:
        return []


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto('https://www.manheim.com')
        print('Opening Manheim...')
        # If already logged in this will go straight through
        # If not, log in manually in the browser then press Enter
        page.wait_for_load_state('networkidle')
        time.sleep(3)
        # Check if login page appeared
        if 'login' in page.url.lower() or 'signin' in page.url.lower():
            print('========================================')
            print('LOG IN to Manheim in the browser window.')
            print('When fully logged in, press Enter here.')
            print('========================================')
            input()
        else:
            print('✅ Already logged in — proceeding automatically')

        print('\nConnecting to Supabase...')
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print('✅ Supabase connected\n')

        start_time = time.time()
        total_rows = 0
        batch = []

        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
            csv_writer = csv_mod.writer(csvfile)
            csv_writer.writerow([
                'year','make','model','trim','color','doors','cyl','fuel',
                'trans','drive','odometer','sale_price','auction_location','sale_date'
            ])

            for location in CA_LOCATIONS:
                print(f'\n{"="*50}')
                print(f'📍 {location}')
                print(f'{"="*50}')

                page.goto(URL_POSTSALE)
                page.wait_for_load_state('networkidle')
                time.sleep(2)

                # Click the location
                try:
                    page.locator(f'a:has-text("{location}")').first.click()
                    page.wait_for_load_state('networkidle')
                    time.sleep(2)
                    print(f'✅ Navigated to {location}')
                except Exception as e:
                    print(f'❌ Could not find {location}: {e} — skipping')
                    continue

                # Collect all date links from sidebar
                date_links = collect_sidebar_dates(page)
                if not date_links:
                    print('No date links found — check page loaded correctly')
                    page.screenshot(path=f'scripts/debug_{location.replace(" ","_")}.png')
                    continue

                print(f'Found {len(date_links)} auction dates\n')

                for d_idx, link in enumerate(date_links):
                    sale_date = link['text']
                    href = link['href']

                    elapsed = time.time() - start_time
                    rate = d_idx / elapsed if elapsed > 0 and d_idx > 0 else 0
                    eta = f'{int((len(date_links)-d_idx)/rate/60)}m' if rate > 0 else '?'

                    print(f'  [{d_idx+1}/{len(date_links)}] {sale_date} | ETA {eta}')

                    try:
                        page.goto(href)
                        page.wait_for_load_state('networkidle')
                        time.sleep(1)

                        # Get all makes from View dropdown
                        makes = get_make_options(page)
                        if not makes:
                            print(f'    No makes in dropdown — trying known makes list')
                            # Try each known make directly
                            makes = [(m, m) for m in KNOWN_MAKES_VALUES]

                        date_rows = 0
                        for make_val, make_label in makes:
                            try:
                                # Select the make
                                sel = page.query_selector('select')
                                if sel:
                                    sel.select_option(make_val)
                                    page.wait_for_load_state('networkidle')
                                    time.sleep(0.8)

                                records = scrape_table(page)
                                batch.extend(records)
                                date_rows += len(records)

                                # Flush when batch is large enough
                                if len(batch) >= BATCH_SIZE:
                                    total_rows = flush_batch(supabase, batch, csv_writer, total_rows, location, sale_date)
                                    csvfile.flush()
                                    batch = []

                            except Exception as e:
                                print(f'      skip make {make_label}: {e}')
                                continue

                        print(f'    → {date_rows} vehicles')

                    except Exception as e:
                        print(f'    ERROR on {sale_date}: {e}')
                        continue

            # Final flush
            if batch:
                total_rows = flush_batch(supabase, batch, csv_writer, total_rows, location, 'final')

        elapsed_min = int((time.time() - start_time) / 60)
        browser.close()
        print(f'\n{"="*50}')
        print(f'✅ COMPLETE in {elapsed_min} minutes')
        print(f'Total rows saved: {total_rows}')
        print(f'Supabase table: dealer_sales')
        print(f'CSV backup: {CSV_FILE}')
        print(f'{"="*50}')


if __name__ == '__main__':
    run()
