"""
File upload API endpoints with security validation
"""
import io
import csv
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
import pandas as pd
from pydantic import BaseModel

from webapp.database import get_db
from webapp.models.user import User
from webapp.models.vehicle import Vehicle
from webapp.auth import get_current_user
from webapp.utils.file_validator import FileValidator
from webapp.utils.csv_processor import CSVProcessor
from config.settings import settings

router = APIRouter()

class UploadResponse(BaseModel):
    status: str
    rows_processed: int
    vehicles_created: int
    vehicles_updated: int
    errors: List[str]
    warnings: List[str]

# Initialize utilities
file_validator = FileValidator()
csv_processor = CSVProcessor()

@router.post("/csv", response_model=UploadResponse)
async def upload_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload and process vehicle data CSV file"""
    
    # Validate file
    validation_result = await file_validator.validate_file(file)
    if not validation_result["valid"]:
        raise HTTPException(status_code=400, detail=validation_result["errors"])
    
    try:
        # Read file content
        content = await file.read()
        
        # Process CSV
        if file.content_type == "text/csv":
            df = pd.read_csv(io.BytesIO(content))
        elif file.content_type in [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel"
        ]:
            df = pd.read_excel(io.BytesIO(content))
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")
        
        # Validate CSV structure
        validation_result = csv_processor.validate_structure(df)
        if not validation_result["valid"]:
            raise HTTPException(status_code=400, detail=validation_result["errors"])
        
        # Process in background for large files
        if len(df) > 100:
            background_tasks.add_task(
                process_large_csv_task,
                df.to_dict('records'),
                current_user.id,
                db
            )
            return UploadResponse(
                status="processing",
                rows_processed=len(df),
                vehicles_created=0,
                vehicles_updated=0,
                errors=[],
                warnings=["Large file processing in background. Check back later for results."]
            )
        
        # Process synchronously for small files
        result = await csv_processor.process_data(df, current_user.id, db)
        
        return UploadResponse(
            status="completed",
            rows_processed=result["rows_processed"],
            vehicles_created=result["vehicles_created"],
            vehicles_updated=result["vehicles_updated"],
            errors=result["errors"],
            warnings=result["warnings"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@router.get("/template")
async def download_template(
    current_user: User = Depends(get_current_user)
):
    """Download CSV template for vehicle data upload"""
    
    from fastapi.responses import StreamingResponse
    import io
    
    # Define template columns with examples
    template_data = {
        "source": ["govdeals", "publicsurplus", "copart"],
        "source_id": ["12345", "ABC-123", "LOT-456"],
        "source_url": [
            "https://www.govdeals.com/auction/12345",
            "https://www.publicsurplus.com/auction/ABC-123",
            "https://www.copart.com/lot/LOT-456"
        ],
        "make": ["Ford", "Chevrolet", "Toyota"],
        "model": ["F-150", "Silverado", "Camry"],
        "year": [2018, 2019, 2020],
        "mileage": [45000, 62000, 38000],
        "vin": ["1FTFW1ET8JFA12345", "1GCVKREC5JZ123456", "4T1BF1FK5GU123456"],
        "title": [
            "2018 Ford F-150 SuperCrew Cab",
            "2019 Chevrolet Silverado 1500",
            "2020 Toyota Camry LE"
        ],
        "description": [
            "Well maintained fleet vehicle with service records",
            "Heavy duty pickup with towing package",
            "Low mileage sedan with clean history"
        ],
        "current_bid": [15000.00, 18500.00, 12000.00],
        "reserve_price": [20000.00, 22000.00, 15000.00],
        "location": ["Los Angeles, CA", "Houston, TX", "Atlanta, GA"],
        "state": ["CA", "TX", "GA"],
        "title_status": ["clean", "clean", "clean"],
        "auction_end": [
            "2024-01-15 15:30:00",
            "2024-01-16 14:00:00",
            "2024-01-17 16:45:00"
        ]
    }
    
    # Create CSV content
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=template_data.keys())
    writer.writeheader()
    
    # Write example rows
    for i in range(3):
        row = {col: values[i] for col, values in template_data.items()}
        writer.writerow(row)
    
    # Create response
    output.seek(0)
    response = StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=vehicle_upload_template.csv"}
    )
    
    return response

@router.get("/history")
async def get_upload_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's upload history"""
    
    # This would require an upload_history table
    # For now, return placeholder
    return {
        "uploads": [
            {
                "id": 1,
                "filename": "vehicles_2024_01.csv",
                "uploaded_at": "2024-01-15T10:30:00Z",
                "status": "completed",
                "rows_processed": 150,
                "vehicles_created": 145,
                "errors": 5
            }
        ]
    }

async def process_large_csv_task(data_records: List[Dict[str, Any]], user_id: int, db: Session):
    """Background task for processing large CSV files"""
    try:
        # Convert back to DataFrame
        df = pd.DataFrame(data_records)
        
        # Process the data
        result = await csv_processor.process_data(df, user_id, db)
        
        # Store results (would need upload_results table)
        print(f"Background processing completed: {result}")
        
    except Exception as e:
        print(f"Background processing failed: {e}")
        # Log error (would need error logging table)