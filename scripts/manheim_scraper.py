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


def get_select_options(page, select_index=0):
    """Get all non-empty options from a select dropdown by index."""
    try:
        selects = page.query_selector_all('select')
        if not selects or select_index >= len(selects):
            return []
        opts = selects[select_index].query_selector_all('option')
        results = []
        for opt in opts:
            val = opt.get_attribute('value') or ''
            txt = safe_text(opt)
            if val and txt and val not in ('', '0', 'null', 'undefined'):
                results.append((val, txt))
        return results
    except Exception:
        return []


def scrape_table(page):
    """Scrape all rows from current visible table."""
    rows_data = []
    try:
        page.wait_for_selector('table tbody tr', timeout=8000)
    except Exception:
        return rows_data

    rows = page.query_selector_all('table tbody tr')
    for row in rows:
        try:
            cells = row.query_selector_all('td')
            # Columns visible: Year, Make, Model + more off-screen
            year  = safe_text(cells[0])  if len(cells) > 0  else ''
            make  = safe_text(cells[1])  if len(cells) > 1  else ''
            model = safe_text(cells[2])  if len(cells) > 2  else ''
            col3  = safe_text(cells[3])  if len(cells) > 3  else ''
            col4  = safe_text(cells[4])  if len(cells) > 4  else ''
            col5  = safe_text(cells[5])  if len(cells) > 5  else ''
            col6  = safe_text(cells[6])  if len(cells) > 6  else ''
            col7  = safe_text(cells[7])  if len(cells) > 7  else ''
            col8  = safe_text(cells[8])  if len(cells) > 8  else ''
            col9  = safe_text(cells[9])  if len(cells) > 9  else ''
            col10 = safe_text(cells[10]) if len(cells) > 10 else ''
            col11 = safe_text(cells[11]) if len(cells) > 11 else ''
            col12 = safe_text(cells[12]) if len(cells) > 12 else ''
            col13 = safe_text(cells[13]) if len(cells) > 13 else ''
        except Exception:
            year = make = model = col3 = col4 = col5 = col6 = col7 = ''
            col8 = col9 = col10 = col11 = col12 = col13 = ''

        if year or make or model:  # skip blank rows
            rows_data.append([year, make, model, col3, col4, col5, col6, col7,
                               col8, col9, col10, col11, col12, col13])
    return rows_data


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

        # Screenshot to verify page loaded correctly
        page.screenshot(path='scripts/manheim_debug.png')
        print('Debug screenshot saved to scripts/manheim_debug.png')

        # Find all date links in the LEFT SIDEBAR (List of Sales)
        # They are clickable links like "March 18, 2026", "March 17, 2026" etc.
        date_links = page.eval_on_selector_all(
            'a',
            '''els => els
                .map(el => ({text: el.innerText.trim(), href: el.href, id: el.id || ""}))
                .filter(l => /\\b(january|february|march|april|may|june|july|august|september|october|november|december)\\b/i.test(l.text) && /202[0-9]/.test(l.text))
            '''
        )

        if not date_links:
            print('ERROR: No date links found in sidebar.')
            print('Check scripts/manheim_debug.png to see what loaded.')
            browser.close()
            return

        print(f'Found {len(date_links)} date links.')

        # Prepare CSV — use generic column headers, first row will define actual content
        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['year', 'make', 'model', 'col4', 'col5', 'col6',
                             'col7', 'col8', 'col9', 'col10', 'col11', 'col12',
                             'col13', 'col14', 'sale_date'])

            total_rows = 0

            for i, link in enumerate(date_links):
                sale_date = link['text']
                href = link['href']
                print(f'\n[{i+1}/{len(date_links)}] {sale_date}')

                try:
                    # Navigate to the date (sidebar click loads in-place)
                    page.goto(href)
                    page.wait_for_load_state('networkidle')
                    time.sleep(1.5)

                    # LEVEL 1 — Loop through every Make in first dropdown
                    makes = get_select_options(page, 0)
                    if not makes:
                        # No dropdown — scrape whatever is visible
                        rows = scrape_table(page)
                        for row in rows:
                            writer.writerow(row + [sale_date])
                            total_rows += 1
                        print(f'  → {len(rows)} rows (no make filter)')
                        csvfile.flush()
                        continue

                    date_total = 0
                    for make_val, make_label in makes:
                        try:
                            selects = page.query_selector_all('select')
                            selects[0].select_option(make_val)
                            page.wait_for_load_state('networkidle')
                            time.sleep(1)

                            # LEVEL 2 — Loop through every Model in second dropdown
                            models = get_select_options(page, 1)
                            if not models:
                                models = [('', 'ALL')]

                            for model_val, model_label in models:
                                try:
                                    if model_val:
                                        selects = page.query_selector_all('select')
                                        if len(selects) > 1:
                                            selects[1].select_option(model_val)
                                            page.wait_for_load_state('networkidle')
                                            time.sleep(0.8)

                                    rows = scrape_table(page)
                                    for row in rows:
                                        writer.writerow(row + [sale_date])
                                        total_rows += 1
                                        date_total += 1
                                        if total_rows % 500 == 0:
                                            print(f'  → {total_rows} total rows...')

                                except Exception as e:
                                    print(f'    skip model {model_label}: {e}')
                                    continue

                        except Exception as e:
                            print(f'  skip make {make_label}: {e}')
                            continue

                    print(f'  → {date_total} vehicles ({len(makes)} makes)')
                    csvfile.flush()

                except Exception as e:
                    print(f'  ERROR on {sale_date}: {e}')
                    continue

        browser.close()
        print(f'\n========================================')
        print(f'COMPLETE. Total rows: {total_rows}')
        print(f'Saved to: {CSV_FILE}')
        print(f'========================================')


if __name__ == '__main__':
    run()
