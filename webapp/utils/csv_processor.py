"""
CSV processing utilities with data validation and sanitization
"""
import pandas as pd
import re
from typing import Dict, List, Any
from datetime import datetime
from sqlalchemy.orm import Session

from webapp.models.vehicle import Vehicle

class CSVProcessor:
    """Process and validate CSV vehicle data"""
    
    def __init__(self):
        self.required_columns = ['make', 'model', 'year']
        self.optional_columns = [
            'source', 'source_id', 'source_url', 'mileage', 'vin', 'title',
            'description', 'current_bid', 'reserve_price', 'location', 'state',
            'title_status', 'auction_end', 'trim', 'zip_code'
        ]
        
        # Column mappings for common variations
        self.column_mappings = {
            'vehicle_make': 'make',
            'vehicle_model': 'model',
            'model_year': 'year',
            'year_made': 'year',
            'odometer': 'mileage',
            'miles': 'mileage',
            'vehicle_identification_number': 'vin',
            'vin_number': 'vin',
            'current_price': 'current_bid',
            'price': 'current_bid',
            'bid_amount': 'current_bid',
            'reserve': 'reserve_price',
            'city': 'location',
            'auction_end_date': 'auction_end',
            'end_date': 'auction_end'
        }
    
    def validate_structure(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate DataFrame structure"""
        errors = []
        warnings = []
        
        if df.empty:
            errors.append("CSV file is empty")
            return {"valid": False, "errors": errors, "warnings": warnings}
        
        # Normalize column names
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        
        # Apply column mappings
        df = df.rename(columns=self.column_mappings)
        
        # Check for required columns
        missing_required = []
        for col in self.required_columns:
            if col not in df.columns:
                missing_required.append(col)
        
        if missing_required:
            errors.append(f"Missing required columns: {', '.join(missing_required)}")
        
        # Check data types and values
        if 'year' in df.columns:
            invalid_years = df[~df['year'].between(1900, 2030, na=False)]
            if not invalid_years.empty:
                warnings.append(f"Found {len(invalid_years)} rows with invalid years")
        
        if 'mileage' in df.columns:
            invalid_mileage = df[df['mileage'] < 0]
            if not invalid_mileage.empty:
                warnings.append(f"Found {len(invalid_mileage)} rows with negative mileage")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "normalized_df": df
        }
    
    async def process_data(self, df: pd.DataFrame, user_id: int, db: Session) -> Dict[str, Any]:
        """Process and import vehicle data"""
        
        # Validate structure first
        validation = self.validate_structure(df)
        if not validation["valid"]:
            return {
                "rows_processed": 0,
                "vehicles_created": 0,
                "vehicles_updated": 0,
                "errors": validation["errors"],
                "warnings": validation["warnings"]
            }
        
        df = validation["normalized_df"]
        errors = validation["errors"].copy()
        warnings = validation["warnings"].copy()
        
        vehicles_created = 0
        vehicles_updated = 0
        
        for index, row in df.iterrows():
            try:
                # Sanitize and validate row data
                clean_data = self._sanitize_row(row, index + 1)
                
                if clean_data["errors"]:
                    errors.extend(clean_data["errors"])
                    continue
                
                if clean_data["warnings"]:
                    warnings.extend(clean_data["warnings"])
                
                # Check if vehicle exists (by source and source_id or VIN)
                existing_vehicle = None
                vehicle_data = clean_data["data"]
                
                if vehicle_data.get("source") and vehicle_data.get("source_id"):
                    existing_vehicle = db.query(Vehicle).filter(
                        Vehicle.source == vehicle_data["source"],
                        Vehicle.source_id == vehicle_data["source_id"]
                    ).first()
                elif vehicle_data.get("vin"):
                    existing_vehicle = db.query(Vehicle).filter(
                        Vehicle.vin == vehicle_data["vin"]
                    ).first()
                
                if existing_vehicle:
                    # Update existing vehicle
                    for key, value in vehicle_data.items():
                        if value is not None:
                            setattr(existing_vehicle, key, value)
                    existing_vehicle.updated_at = datetime.now()
                    vehicles_updated += 1
                else:
                    # Create new vehicle
                    vehicle = Vehicle(**vehicle_data)
                    db.add(vehicle)
                    vehicles_created += 1
                
            except Exception as e:
                errors.append(f"Row {index + 1}: {str(e)}")
                continue
        
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            errors.append(f"Database error: {str(e)}")
        
        return {
            "rows_processed": len(df),
            "vehicles_created": vehicles_created,
            "vehicles_updated": vehicles_updated,
            "errors": errors,
            "warnings": warnings
        }
    
    def _sanitize_row(self, row: pd.Series, row_num: int) -> Dict[str, Any]:
        """Sanitize and validate individual row"""
        errors = []
        warnings = []
        clean_data = {}
        
        # Process each field
        for column, value in row.items():
            if pd.isna(value) or value == '':
                continue
            
            try:
                if column == 'make':
                    clean_data['make'] = self._sanitize_text(str(value), max_length=50)
                
                elif column == 'model':
                    clean_data['model'] = self._sanitize_text(str(value), max_length=100)
                
                elif column == 'year':
                    year = int(float(value))
                    if 1900 <= year <= 2030:
                        clean_data['year'] = year
                    else:
                        errors.append(f"Row {row_num}: Invalid year {year}")
                
                elif column == 'mileage':
                    mileage = int(float(value))
                    if mileage >= 0:
                        clean_data['mileage'] = mileage
                    else:
                        errors.append(f"Row {row_num}: Invalid mileage {mileage}")
                
                elif column == 'vin':
                    vin = self._sanitize_vin(str(value))
                    if vin:
                        clean_data['vin'] = vin
                    else:
                        warnings.append(f"Row {row_num}: Invalid VIN format")
                
                elif column in ['current_bid', 'reserve_price']:
                    price = float(str(value).replace('$', '').replace(',', ''))
                    if price >= 0:
                        clean_data[column] = price
                    else:
                        errors.append(f"Row {row_num}: Invalid price {price}")
                
                elif column == 'title':
                    clean_data['title'] = self._sanitize_text(str(value), max_length=500)
                
                elif column == 'description':
                    clean_data['description'] = self._sanitize_text(str(value), max_length=2000)
                
                elif column == 'source':
                    clean_data['source'] = self._sanitize_text(str(value), max_length=50).lower()
                
                elif column == 'source_id':
                    clean_data['source_id'] = self._sanitize_text(str(value), max_length=100)
                
                elif column == 'source_url':
                    url = str(value).strip()
                    if self._validate_url(url):
                        clean_data['source_url'] = url
                    else:
                        warnings.append(f"Row {row_num}: Invalid URL format")
                
                elif column == 'location':
                    clean_data['location'] = self._sanitize_text(str(value), max_length=200)
                
                elif column == 'state':
                    state = str(value).strip().upper()
                    if len(state) == 2 and state.isalpha():
                        clean_data['state'] = state
                    else:
                        warnings.append(f"Row {row_num}: Invalid state code {state}")
                
                elif column == 'title_status':
                    status = str(value).strip().lower()
                    if status in ['clean', 'salvage', 'rebuilt', 'flood', 'lemon']:
                        clean_data['title_status'] = status
                    else:
                        warnings.append(f"Row {row_num}: Unknown title status {status}")
                
                elif column == 'auction_end':
                    try:
                        # Try to parse various date formats
                        date_str = str(value).strip()
                        auction_end = pd.to_datetime(date_str)
                        clean_data['auction_end'] = auction_end
                    except:
                        warnings.append(f"Row {row_num}: Invalid date format {value}")
                
                elif column in ['trim', 'zip_code']:
                    clean_data[column] = self._sanitize_text(str(value), max_length=50)
                
            except Exception as e:
                errors.append(f"Row {row_num}, Column {column}: {str(e)}")
        
        # Ensure required fields are present
        for required_col in self.required_columns:
            if required_col not in clean_data:
                errors.append(f"Row {row_num}: Missing required field {required_col}")
        
        # Set defaults
        if 'source' not in clean_data:
            clean_data['source'] = 'csv_upload'
        
        if 'is_active' not in clean_data:
            clean_data['is_active'] = True
        
        return {
            "data": clean_data,
            "errors": errors,
            "warnings": warnings
        }
    
    def _sanitize_text(self, text: str, max_length: int = None) -> str:
        """Sanitize text input"""
        if not text:
            return ""
        
        # Remove potential SQL injection patterns
        text = re.sub(r'[;\'"\\]', '', str(text))
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        # Truncate if necessary
        if max_length and len(text) > max_length:
            text = text[:max_length]
        
        return text.strip()
    
    def _sanitize_vin(self, vin: str) -> str:
        """Validate and sanitize VIN"""
        if not vin:
            return ""
        
        # Remove non-alphanumeric characters
        vin = re.sub(r'[^A-Z0-9]', '', str(vin).upper())
        
        # VIN should be exactly 17 characters
        if len(vin) == 17:
            # Basic VIN validation (no I, O, Q)
            if not re.search(r'[IOQ]', vin):
                return vin
        
        return ""
    
    def _validate_url(self, url: str) -> bool:
        """Validate URL format"""
        if not url:
            return False
        
        # Basic URL validation
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        return url_pattern.match(url) is not None