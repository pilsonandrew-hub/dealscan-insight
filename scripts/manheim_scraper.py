# dependencies: pip install playwright && playwright install chromium
# Run: python scripts/manheim_scraper.py
# Scrapes ALL sale dates (1 year back), ALL makes, ALL models from Manheim CA post-sale reports

from playwright.sync_api import sync_playwright
import csv
import time
from datetime import datetime, timedelta

CSV_FILE = 'scripts/manheim_postsale_export.csv'
URL_POSTSALE = 'https://www.manheim.com/postsale?auctionAccessNumber=5500030'

# All makes seen at Manheim California — hardcoded as fallback
KNOWN_MAKES = [
    'ACURA', 'ALFA ROMEO', 'AUDI', 'BENTLEY', 'BMW', 'BUICK', 'CADILLAC',
    'CHEVROLET', 'CHRYSLER', 'DODGE', 'FIAT', 'FORD', 'GENESIS', 'GMC',
    'HONDA', 'HYUNDAI', 'INFINITI', 'JAGUAR', 'JEEP', 'KIA', 'LAND ROVER',
    'LEXUS', 'LINCOLN', 'MASERATI', 'MAZDA', 'MERCEDES-BENZ', 'MINI',
    'MITSUBISHI', 'NISSAN', 'PORSCHE', 'RAM', 'RIVIAN', 'SUBARU', 'TESLA',
    'TOYOTA', 'VOLKSWAGEN', 'VOLVO'
]


def safe_text(el):
    try:
        return el.inner_text().strip()
    except:
        return ''


def scrape_table(page):
    """Scrape all visible table rows. Handles multi-page results."""
    rows_data = []
    page_num = 0
    while True:
        page_num += 1
        try:
            page.wait_for_selector('table tbody tr', timeout=8000)
        except Exception:
            break

        rows = page.query_selector_all('table tbody tr')
        for row in rows:
            try:
                cells = row.query_selector_all('td')
                data = [safe_text(c) for c in cells]
                while len(data) < 14:
                    data.append('')
                if any(data[:3]):
                    rows_data.append(data[:14])
            except Exception:
                continue

        # Handle Next page if present
        try:
            next_btn = page.query_selector(
                'a:has-text("Next"), button:has-text("Next"), [aria-label="Next page"], [aria-label="Next"]'
            )
            if next_btn and not next_btn.is_disabled():
                next_btn.click()
                page.wait_for_load_state('networkidle')
                time.sleep(1)
            else:
                break
        except Exception:
            break

    return rows_data


def open_dropdown(page, button_selector):
    """Open a dropdown button. Returns True if opened."""
    try:
        btn = page.query_selector(button_selector)
        if not btn:
            btn = page.locator('button', has_text='View').first
        if btn:
            btn.click()
            time.sleep(0.6)
            return True
    except Exception:
        pass
    return False


def get_dropdown_options(page):
    """Get all options from the currently open dropdown."""
    opts = []
    try:
        items = page.query_selector_all(
            '[role="menuitem"], [role="option"], .dropdown-item, ul.dropdown-menu li a, .dropdown li a'
        )
        for item in items:
            txt = safe_text(item)
            if txt:
                opts.append(txt)
        if not opts:
            items = page.query_selector_all('.show li, .open li, [aria-expanded="true"] ~ * li')
            for item in items:
                txt = safe_text(item)
                if txt:
                    opts.append(txt)
    except Exception:
        pass
    return opts


def click_option(page, text):
    """Click a dropdown option by text."""
    try:
        # Try role-based selectors first
        for selector in [
            f'[role="menuitem"]:has-text("{text}")',
            f'[role="option"]:has-text("{text}")',
            f'.dropdown-item:has-text("{text}")',
            f'ul.dropdown-menu li a:has-text("{text}")',
        ]:
            el = page.query_selector(selector)
            if el:
                el.click()
                page.wait_for_load_state('networkidle')
                time.sleep(1)
                return True
        # Fallback: click by visible text
        page.click(f'text="{text}"')
        page.wait_for_load_state('networkidle')
        time.sleep(1)
        return True
    except Exception:
        return False


def collect_all_date_links(page):
    """
    Collect all sale date links across all months for the past year.
    Tries navigating Previous Month up to 13 times to get a full year.
    """
    all_links = {}  # href -> text, deduped

    def harvest_current_page():
        links = page.eval_on_selector_all(
            'a',
            '''els => els
                .map(el => ({text: el.innerText.trim(), href: el.href}))
                .filter(l =>
                    l.href.length > 0 &&
                    l.href !== window.location.href &&
                    l.href.includes("postsale") &&
                    l.text.length > 3
                )
            '''
        )
        for l in links:
            if l['href'] not in all_links:
                all_links[l['href']] = l['text']

    # Harvest current (most recent) month
    harvest_current_page()
    months_back = 0

    # Navigate back month by month for up to 12 more months
    while months_back < 12:
        try:
            prev_btn = page.query_selector(
                'button:has-text("Previous"), a:has-text("Previous"), '
                '[aria-label="Previous month"], [aria-label="Previous"]'
            )
            if not prev_btn:
                break
            prev_btn.click()
            page.wait_for_load_state('networkidle')
            time.sleep(1.5)
            months_back += 1
            harvest_current_page()
            print(f'  Month -{months_back}: {len(all_links)} total date links so far')
        except Exception as e:
            print(f'  Month navigation stopped: {e}')
            break

    return [{'href': href, 'text': text} for href, text in all_links.items()]


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

        print('\nNavigating to post-sale page...')
        page.goto(URL_POSTSALE)
        page.wait_for_load_state('networkidle')
        time.sleep(2)

        page.screenshot(path='scripts/manheim_debug.png')
        print('Debug screenshot saved to scripts/manheim_debug.png\n')

        # Collect ALL date links going back 1 full year
        print('Collecting date links (going back 1 year)...')
        date_links = collect_all_date_links(page)

        if not date_links:
            print('ERROR: No date links found. Check scripts/manheim_debug.png')
            browser.close()
            return

        print(f'\nTotal auction dates found: {len(date_links)}')
        print('Starting full scrape — fully automatic from here.\n')

        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'year', 'make', 'model', 'color', 'doors', 'cyl', 'fuel',
                'trans', '4x4', 'radio', 'interior', 'odometer', 'price', 'col14',
                'sale_date', 'make_filter', 'model_filter'
            ])

            total_rows = 0
            start_time = time.time()

            for i, link in enumerate(date_links):
                sale_date = link['text']
                href = link['href']
                eta_str = ''
                if i > 0:
                    elapsed = time.time() - start_time
                    rate = i / elapsed
                    remaining = (len(date_links) - i) / rate if rate > 0 else 0
                    eta_str = f' | ETA {int(remaining/60)}m'

                print(f'[{i+1}/{len(date_links)}] {sale_date}{eta_str}')

                try:
                    page.goto(href)
                    page.wait_for_load_state('networkidle')
                    time.sleep(1.5)

                    # Try to detect makes from View dropdown
                    open_dropdown(page, 'button:has-text("View"), .view-dropdown, #viewDropdown')
                    makes_from_dropdown = get_dropdown_options(page)

                    # Close dropdown if still open
                    try:
                        page.keyboard.press('Escape')
                        time.sleep(0.3)
                    except Exception:
                        pass

                    makes = makes_from_dropdown if makes_from_dropdown else KNOWN_MAKES
                    date_total = 0

                    for make in makes:
                        # Open View dropdown and select make
                        try:
                            open_dropdown(page, 'button:has-text("View"), .view-dropdown')
                            if not click_option(page, make):
                                continue

                            # Check for Model sub-dropdown after selecting make
                            open_dropdown(page, 'button:has-text("Model"), .model-dropdown')
                            models_from_dropdown = get_dropdown_options(page)

                            try:
                                page.keyboard.press('Escape')
                                time.sleep(0.3)
                            except Exception:
                                pass

                            if models_from_dropdown:
                                # Loop through every model
                                for model in models_from_dropdown:
                                    try:
                                        open_dropdown(page, 'button:has-text("Model"), .model-dropdown')
                                        if not click_option(page, model):
                                            continue

                                        rows = scrape_table(page)
                                        for row in rows:
                                            writer.writerow(row + [sale_date, make, model])
                                            total_rows += 1
                                            date_total += 1
                                            if total_rows % 500 == 0:
                                                print(f'  → {total_rows} total rows...')
                                    except Exception as e:
                                        print(f'    skip model {model}: {e}')
                                        continue
                            else:
                                # No model dropdown — scrape all models for this make at once
                                rows = scrape_table(page)
                                for row in rows:
                                    writer.writerow(row + [sale_date, make, ''])
                                    total_rows += 1
                                    date_total += 1
                                    if total_rows % 500 == 0:
                                        print(f'  → {total_rows} total rows...')

                        except Exception as e:
                            print(f'  skip make {make}: {e}')
                            continue

                    print(f'  → {date_total} vehicles from {sale_date}')
                    csvfile.flush()

                except Exception as e:
                    print(f'  ERROR on {sale_date}: {e}')
                    continue

        browser.close()
        elapsed_min = int((time.time() - start_time) / 60)
        print(f'\n========================================')
        print(f'COMPLETE in {elapsed_min} minutes.')
        print(f'Total rows: {total_rows}')
        print(f'Saved to: {CSV_FILE}')
        print(f'========================================')


if __name__ == '__main__':
    run()
