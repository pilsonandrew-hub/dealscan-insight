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


def scrape_table(page):
    """Scrape all rows from the currently visible results table."""
    rows_data = []
    try:
        page.wait_for_selector('table tbody tr', timeout=8000)
    except Exception:
        return rows_data

    rows = page.query_selector_all('table tbody tr')
    for row in rows:
        try:
            cells = row.query_selector_all('td')
            # Full column order (some may be scrolled off — capture all):
            # Year, Make, Model, Color, Drs, Cyl, Fuel, Trans, 4x4, Radio, Int, Odometer, Price
            data = [safe_text(c) for c in cells]
            # Pad to 14 columns
            while len(data) < 14:
                data.append('')
            if any(data[:3]):  # skip blank rows
                rows_data.append(data[:14])
        except Exception:
            continue
    return rows_data


def open_view_dropdown_and_get_makes(page):
    """Open the View dropdown and return list of make option texts."""
    makes = []
    try:
        # Try clicking the "View" button to open the dropdown
        view_btn = page.query_selector('button:has-text("View"), [aria-label*="View"], .view-dropdown, #viewDropdown')
        if not view_btn:
            # Try finding by partial text
            view_btn = page.locator('button', has_text='View').first
        if view_btn:
            view_btn.click()
            time.sleep(0.8)

        # Get all make options from the open dropdown
        # They appear as list items or menu items
        opts = page.query_selector_all('[role="menuitem"], [role="option"], .dropdown-item, ul.dropdown-menu li a, .view-menu li')
        for opt in opts:
            txt = safe_text(opt)
            if txt:
                makes.append(txt)

        if not makes:
            # Fallback: look for any list inside an open dropdown
            opts = page.query_selector_all('.show li, .open li, [aria-expanded="true"] li')
            for opt in opts:
                txt = safe_text(opt)
                if txt:
                    makes.append(txt)

    except Exception as e:
        print(f'  Could not open View dropdown: {e}')

    return makes


def select_make(page, make_text):
    """Click a make option in the open dropdown."""
    try:
        # Find and click the option matching this make text
        # Strip the count in parens e.g. "ACURA (11)" -> click element with that text
        el = page.locator(f'[role="menuitem"]:has-text("{make_text}"), [role="option"]:has-text("{make_text}"), .dropdown-item:has-text("{make_text}")').first
        if el:
            el.click()
            page.wait_for_load_state('networkidle')
            time.sleep(1)
            return True
    except Exception:
        pass

    # Fallback: find any clickable element with that text
    try:
        page.click(f'text="{make_text}"')
        page.wait_for_load_state('networkidle')
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

        # Save debug screenshot
        page.screenshot(path='scripts/manheim_debug.png')
        print('Debug screenshot saved.')

        # Find all date links in the LEFT SIDEBAR
        # e.g. "26 Sales Results for Wednesday March 18th" or just "March 18"
        date_links = page.eval_on_selector_all(
            'a',
            '''els => els
                .map(el => ({text: el.innerText.trim(), href: el.href}))
                .filter(l =>
                    l.text.length > 0 &&
                    l.href.includes("postsale") &&
                    l.href !== window.location.href &&
                    (
                        /\\b(january|february|march|april|may|june|july|august|september|october|november|december)\\b/i.test(l.text) ||
                        /sales results/i.test(l.text)
                    )
                )
            '''
        )

        # Deduplicate
        seen = set()
        unique_dates = []
        for l in date_links:
            if l['href'] not in seen:
                seen.add(l['href'])
                unique_dates.append(l)

        if not unique_dates:
            print('ERROR: No date links found. Check scripts/manheim_debug.png')
            browser.close()
            return

        print(f'Found {len(unique_dates)} auction dates to scrape.\n')

        # KNOWN MAKES from your screenshot (fallback if dropdown detection fails)
        KNOWN_MAKES = [
            'ACURA', 'ALFA ROMEO', 'AUDI', 'BENTLEY', 'BMW', 'BUICK', 'CADILLAC',
            'CHEVROLET', 'CHRYSLER', 'DODGE', 'FIAT', 'FORD', 'GENESIS', 'GMC',
            'HONDA', 'HYUNDAI', 'INFINITI', 'JAGUAR', 'JEEP', 'KIA', 'LAND ROVER',
            'LEXUS', 'LINCOLN', 'MACK', 'MASERATI', 'MAZDA', 'MERCEDES',
            'MERCEDES B', 'MERCEDES-B', 'MINI', 'MITSUBISHI', 'NISSAN', 'PONTIAC',
            'PORSCHE', 'RAM', 'RIVIAN', 'SAAB', 'SCION', 'SUBARU', 'TESLA',
            'TOYOTA', 'VOLKSWAGEN', 'VOLVO'
        ]

        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'year', 'make', 'model', 'color', 'doors', 'cyl', 'fuel',
                'trans', '4x4', 'radio', 'interior', 'odometer', 'price', 'col14',
                'sale_date', 'make_filter'
            ])

            total_rows = 0

            for i, link in enumerate(unique_dates):
                sale_date = link['text']
                href = link['href']
                print(f'[{i+1}/{len(unique_dates)}] {sale_date}')

                try:
                    page.goto(href)
                    page.wait_for_load_state('networkidle')
                    time.sleep(1.5)

                    # Try to get makes from View dropdown
                    makes = open_view_dropdown_and_get_makes(page)

                    if not makes:
                        # Use known makes list as fallback
                        print('  Using known makes list as fallback')
                        makes = KNOWN_MAKES

                    date_total = 0
                    for make in makes:
                        try:
                            # Re-open dropdown and select make
                            view_btn = page.query_selector('button:has-text("View"), .view-dropdown')
                            if not view_btn:
                                view_btn = page.locator('button', has_text='View').first
                            if view_btn:
                                view_btn.click()
                                time.sleep(0.5)

                            selected = select_make(page, make)
                            if not selected:
                                continue

                            rows = scrape_table(page)
                            for row in rows:
                                writer.writerow(row + [sale_date, make])
                                total_rows += 1
                                date_total += 1
                                if total_rows % 500 == 0:
                                    print(f'  → {total_rows} total rows...')

                        except Exception as e:
                            print(f'  skip {make}: {e}')
                            continue

                    print(f'  → {date_total} vehicles')
                    csvfile.flush()

                except Exception as e:
                    print(f'  ERROR on {sale_date}: {e}')
                    continue

        browser.close()
        print(f'\n========================================')
        print(f'COMPLETE. {total_rows} total rows saved.')
        print(f'File: {CSV_FILE}')
        print(f'========================================')


if __name__ == '__main__':
    run()
