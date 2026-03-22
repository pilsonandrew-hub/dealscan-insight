#!/usr/bin/env python3
"""
Parse and load Manheim post-sale text files into Supabase dealer_sales table.
Handles the fixed-width format from Manheim's post-sale report exports.
"""
import re
import sys
from supabase import create_client

SUPABASE_URL = 'https://lbnxzvqppccajllsqaaw.supabase.co'
SUPABASE_KEY = 'SUPABASE_SERVICE_ROLE_KEY_REDACTED'

FILES = [
    '/Users/andrewpilson/.openclaw/media/inbound/324114251-Manheim-Post-Sale-Results-062316---d88fc39f-d0d0-44ca-960d-d8b6104af741.txt',
    '/Users/andrewpilson/.openclaw/media/inbound/389800411-Manheim_2---5cb507ba-c7b0-459b-ba06-320c24090b9e.txt',
    '/Users/andrewpilson/.openclaw/media/inbound/389800411-Manheim---c81c220a-ebae-40c6-9760-3e7291268a7e.txt',
]

def clean_price(val):
    try:
        return float(re.sub(r'[^\d.]', '', val))
    except:
        return None

def clean_odo(val):
    try:
        v = re.sub(r'[^\d]', '', val)
        n = int(v)
        return n if n < 999990 else None
    except:
        return None

def clean_year(val):
    try:
        y = int(val.strip())
        return y if 1980 <= y <= 2030 else None
    except:
        return None

def parse_postsale_file(filepath):
    """Parse Manheim post-sale format: columns of YR, MAKE, MODEL, ..., ODOMETER, COLOR, PRICE"""
    records = []
    
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Detect auction name and date
    auction_location = 'Manheim Atlanta'
    sale_date = None
    date_match = re.search(r'(\d{2}/\d{2}/\d{4})', content)
    if date_match:
        sale_date = date_match.group(1)
    
    loc_match = re.search(r'Manheim\s+[\w\s]+(?=\n)', content)
    if loc_match:
        auction_location = loc_match.group(0).strip()

    is_presale = 'Pre-Sale' in content or 'presale' in filepath.lower()

    if is_presale:
        # Pre-sale format: Ln/Run Year Make/Model Eng/T Odometer Color VIN AC Top
        # Example: 17 35 2017 AUDI A4 AWD 4D SEDAN PREMIUM PLUS 4GT/A 9,898 BLACK WAUENAF40HN036855 X SR
        pattern = re.compile(
            r'\d+\s+\d+\s+(\d{4})\s+([A-Z][A-Z \-\.]+?)\s+(\d[\d,]+)\s+([A-Z][A-Z ]+?)\s+([A-Z0-9]{17})',
        )
        for m in pattern.finditer(content):
            year_str, make_model, odo_str, color, vin = m.groups()
            # Split make/model
            parts = make_model.strip().split()
            make = parts[0] if parts else ''
            model = ' '.join(parts[1:]) if len(parts) > 1 else ''
            records.append({
                'year': clean_year(year_str),
                'make': make.strip() or None,
                'model': model.strip() or None,
                'color': color.strip() or None,
                'odometer': clean_odo(odo_str),
                'vin': vin.strip(),
                'auction_location': auction_location,
                'sale_date_label': sale_date,
                'source': 'manheim_presale_import',
            })
    else:
        # Post-sale format: columnar data with PRICE column
        # Extract rows with price pattern: ends with $XX,XXX
        # Each vehicle row has year at start and price at end
        row_pattern = re.compile(
            r'^(\d{4})\s+([A-Z][A-Z &\-/]+?)\s+([A-Z0-9][A-Z0-9 &\-/]+?)\s+[\w]+\s+[\w]+\s+[\w]+\s+[\w]+\s+[\w]+\s+[\w]+\s+[\w]+\s+([\d,]+)\s+([A-Z][A-Z ]+?)\s+\$([0-9,]+)',
            re.MULTILINE
        )
        
        # Simpler approach: find all price lines by scanning for $XX,XXX patterns
        # and working backwards to get year/make/model/odo
        lines = content.split('\n')
        
        # Build column arrays — the file has parallel columns
        # YR column, MAKE column, MODEL column, ODOMETER column, COLOR column, PRICE column
        yr_block = []
        make_block = []
        model_block = []
        odo_block = []
        color_block = []
        price_block = []
        
        # Find where each column section starts
        in_yr = False
        in_make = False
        
        yr_lines = []
        make_lines = []
        model_lines = []
        odo_lines = []
        color_lines = []
        price_lines = []
        
        for line in lines:
            line = line.strip()
            # Year lines: 4-digit years only
            if re.match(r'^\d{4}$', line):
                yr_lines.append(line)
            # Price lines: $XX,XXX
            elif re.match(r'^\$[\d,]+$', line):
                price_lines.append(line)
            # Odometer: numbers with commas, 4-7 digits
            elif re.match(r'^[\d,]{4,8}$', line) and ',' in line:
                odo_lines.append(line)
            # Make: ALL CAPS words
            elif re.match(r'^[A-Z][A-Z ]{2,}$', line) and len(line) < 30:
                if line not in ('PS', 'PB', 'AC', 'SR', 'HT', 'MR', 'CV', 'TR', 'PN', 'HC', 'RT',
                                'AWD', 'FWD', 'RWD', '4X2', '4X4', '4WD', 'SUV', 'DSN'):
                    make_lines.append(line)

        print(f'  Found: {len(yr_lines)} years, {len(price_lines)} prices, {len(odo_lines)} odometers')
        
        # Match up by index — years and prices should align
        count = min(len(yr_lines), len(price_lines))
        for i in range(count):
            make = make_lines[i] if i < len(make_lines) else None
            odo = clean_odo(odo_lines[i]) if i < len(odo_lines) else None
            price = clean_price(price_lines[i])
            
            if clean_year(yr_lines[i]) and price:
                records.append({
                    'year': clean_year(yr_lines[i]),
                    'make': make,
                    'model': None,
                    'odometer': odo,
                    'sale_price': price,
                    'auction_location': auction_location,
                    'sale_date_label': sale_date,
                    'source': 'manheim_postsale_import',
                })

    return records


def main():
    print('Connecting to Supabase...')
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print('✅ Connected\n')

    total = 0
    for filepath in FILES:
        print(f'Parsing: {filepath.split("/")[-1][:50]}')
        try:
            records = parse_postsale_file(filepath)
            print(f'  Parsed {len(records)} records')
            
            # Filter valid records
            valid = [r for r in records if r.get('year') and (r.get('make') or r.get('model'))]
            print(f'  Valid: {len(valid)} records')
            
            # Insert in batches of 100
            for i in range(0, len(valid), 100):
                batch = valid[i:i+100]
                try:
                    supabase.table('dealer_sales').insert(batch).execute()
                    total += len(batch)
                    print(f'  Inserted batch {i//100 + 1}: {total} total rows')
                except Exception as e:
                    print(f'  Insert error: {e}')
                    
        except Exception as e:
            print(f'  Parse error: {e}')

    print(f'\n✅ DONE. Total rows inserted: {total}')


if __name__ == '__main__':
    main()
