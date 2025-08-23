"""
File upload validation utilities
"""
import magic
from typing import Dict, List
from fastapi import UploadFile
from config.settings import settings

class FileValidator:
    """Validate uploaded files for security and format"""
    
    def __init__(self):
        self.allowed_mime_types = {
            "text/csv",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel"
        }
        
        self.allowed_extensions = {".csv", ".xlsx", ".xls"}
        self.max_size = settings.max_upload_size
        
        # Magic number signatures for additional validation
        self.file_signatures = {
            "csv": [b""],  # CSV can start with anything
            "xlsx": [b"PK\x03\x04"],  # ZIP-based format
            "xls": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"]  # OLE format
        }
    
    async def validate_file(self, file: UploadFile) -> Dict[str, any]:
        """Comprehensive file validation"""
        errors = []
        warnings = []
        
        # Check file size
        if hasattr(file, 'size') and file.size > self.max_size:
            errors.append(f"File too large. Maximum size: {self.max_size // (1024*1024)}MB")
        
        # Check filename
        if not file.filename:
            errors.append("Filename is required")
            return {"valid": False, "errors": errors, "warnings": warnings}
        
        # Check file extension
        filename_lower = file.filename.lower()
        if not any(filename_lower.endswith(ext) for ext in self.allowed_extensions):
            errors.append(f"Invalid file extension. Allowed: {', '.join(self.allowed_extensions)}")
        
        # Check content type
        if file.content_type not in self.allowed_mime_types:
            errors.append(f"Invalid content type: {file.content_type}")
        
        # Read first chunk for magic number validation
        try:
            chunk = await file.read(512)  # Read first 512 bytes
            await file.seek(0)  # Reset file pointer
            
            # Validate magic numbers
            if filename_lower.endswith('.xlsx'):
                if not chunk.startswith(b'PK\x03\x04'):
                    errors.append("File appears to be corrupted or not a valid Excel file")
            elif filename_lower.endswith('.xls'):
                if not chunk.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
                    errors.append("File appears to be corrupted or not a valid Excel file")
            
            # Check for potential security threats
            security_check = self._check_security_threats(chunk, filename_lower)
            errors.extend(security_check["errors"])
            warnings.extend(security_check["warnings"])
            
        except Exception as e:
            errors.append(f"Failed to read file: {str(e)}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def _check_security_threats(self, content: bytes, filename: str) -> Dict[str, List[str]]:
        """Check for potential security threats in file content"""
        errors = []
        warnings = []
        
        # Check for embedded executables (basic check)
        executable_signatures = [
            b'MZ',      # Windows executable
            b'\x7fELF', # Linux executable
            b'\xca\xfe\xba\xbe',  # Java class file
            b'#!/bin/', # Shell script
            b'<script', # JavaScript
            b'<?php',   # PHP
        ]
        
        content_lower = content.lower()
        for sig in executable_signatures:
            if sig.lower() in content_lower:
                errors.append("File contains potentially dangerous content")
                break
        
        # Check for suspicious file patterns
        if b'<html' in content_lower or b'<body' in content_lower:
            warnings.append("File appears to contain HTML content")
        
        if b'javascript:' in content_lower:
            errors.append("File contains potentially malicious JavaScript")
        
        # Check for macro indicators in Office files
        if filename.endswith(('.xlsx', '.xls')):
            if b'vbaProject' in content or b'macros' in content_lower:
                warnings.append("File may contain macros - these will be ignored")
        
        return {"errors": errors, "warnings": warnings}
    
    def validate_csv_structure(self, content: bytes) -> Dict[str, any]:
        """Validate CSV structure and content"""
        errors = []
        warnings = []
        
        try:
            # Decode content
            text_content = content.decode('utf-8')
            lines = text_content.split('\n')
            
            if len(lines) < 2:
                errors.append("CSV must contain at least a header row and one data row")
                return {"valid": False, "errors": errors, "warnings": warnings}
            
            # Check for consistent column count
            header_cols = len(lines[0].split(','))
            for i, line in enumerate(lines[1:6], 1):  # Check first 5 data rows
                if line.strip():  # Skip empty lines
                    cols = len(line.split(','))
                    if cols != header_cols:
                        warnings.append(f"Row {i} has {cols} columns, expected {header_cols}")
            
            # Check for required columns
            header = lines[0].lower()
            required_columns = ['make', 'model', 'year']
            missing_required = []
            
            for col in required_columns:
                if col not in header:
                    missing_required.append(col)
            
            if missing_required:
                errors.append(f"Missing required columns: {', '.join(missing_required)}")
            
            # Check for suspicious patterns
            if 'password' in header or 'token' in header:
                warnings.append("File contains columns with sensitive names")
            
        except UnicodeDecodeError:
            errors.append("File encoding is not UTF-8 compatible")
        except Exception as e:
            errors.append(f"Failed to validate CSV structure: {str(e)}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }