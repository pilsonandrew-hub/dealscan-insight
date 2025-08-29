#!/usr/bin/env python3
"""
DealerScope HTML Report Generator
Creates comprehensive HTML dashboard from validation results
"""

import json
import os
from datetime import datetime
from pathlib import Path

def load_summary_json(reports_dir):
    """Load the summary.json file"""
    summary_path = os.path.join(reports_dir, 'final', 'summary.json')
    try:
        with open(summary_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def get_status_badge_class(status):
    """Get CSS class for status badge"""
    status_map = {
        'PASS': 'success',
        'WARN': 'warning', 
        'FAIL': 'error',
        'UNKNOWN': 'info'
    }
    return status_map.get(status, 'info')

def get_status_icon(status):
    """Get icon for status"""
    status_map = {
        'PASS': '✅',
        'WARN': '⚠️',
        'FAIL': '❌',
        'UNKNOWN': '❓'
    }
    return status_map.get(status, '❓')

def generate_html_report(summary_data):
    """Generate comprehensive HTML report"""
    
    if not summary_data:
        # Fallback HTML if no summary data
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DealerScope Validation Dashboard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; }
        .card { background: white; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); padding: 40px; }
        h1 { color: #2563eb; margin: 0 0 20px 0; font-size: 2.5rem; }
        .warning { background: #fef3c7; color: #92400e; padding: 20px; border-radius: 8px; border: 2px solid #fbbf24; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>🚀 DealerScope Validation Dashboard</h1>
            <div class="warning">
                <strong>⚠️ No validation data available</strong><br>
                Reports are being generated or validation suite needs configuration.
            </div>
        </div>
    </div>
</body>
</html>
        """
    
    overall_status = summary_data.get('overall_status', 'UNKNOWN')
    score_percentage = summary_data.get('score_percentage', 0)
    status_class = get_status_badge_class(overall_status)
    status_icon = get_status_icon(overall_status)
    
    # Generate category cards
    categories_html = ""
    categories = summary_data.get('categories', {})
    
    for category_name, category_data in categories.items():
        cat_status = category_data.get('status', 'UNKNOWN')
        cat_icon = get_status_icon(cat_status)
        cat_class = get_status_badge_class(cat_status)
        
        if category_name == 'security':
            details = f"""
                <div class="detail-item">
                    <span class="detail-label">Vulnerabilities:</span>
                    <span class="detail-value">{category_data.get('vulnerabilities_found', 0)}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Scans:</span>
                    <span class="detail-value">{', '.join(category_data.get('scans_performed', []))}</span>
                </div>
            """
        elif category_name == 'performance':
            details = f"""
                <div class="detail-item">
                    <span class="detail-label">Lighthouse Score:</span>
                    <span class="detail-value">{category_data.get('lighthouse_score', 0)}/100</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Bundle Size:</span>
                    <span class="detail-value">{category_data.get('bundle_size', 'Unknown')}</span>
                </div>
            """
        else:
            details = f"""
                <div class="detail-item">
                    <span class="detail-label">Status:</span>
                    <span class="detail-value">{cat_status}</span>
                </div>
            """
        
        categories_html += f"""
        <div class="category-card">
            <div class="category-header">
                <h3>{cat_icon} {category_name.title()}</h3>
                <span class="status-badge {cat_class}">{cat_status}</span>
            </div>
            <div class="category-details">
                {details}
            </div>
        </div>
        """
    
    # Generate recommendations
    recommendations_html = ""
    for rec in summary_data.get('recommendations', []):
        recommendations_html += f"<li>{rec}</li>"
    
    # Main HTML template
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DealerScope Validation Dashboard</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            margin: 0; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        .container {{ 
            max-width: 1400px; 
            margin: 0 auto; 
            padding: 40px 20px; 
        }}
        .header-card {{ 
            background: white; 
            border-radius: 16px; 
            box-shadow: 0 20px 40px rgba(0,0,0,0.1); 
            padding: 40px; 
            margin-bottom: 30px;
            text-align: center;
        }}
        h1 {{ 
            color: #1e40af; 
            margin: 0 0 20px 0; 
            font-size: 3rem; 
            font-weight: 700;
        }}
        .score-circle {{
            width: 120px;
            height: 120px;
            border-radius: 50%;
            margin: 20px auto;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2rem;
            font-weight: bold;
            color: white;
            background: linear-gradient(135deg, 
                {('#10b981' if score_percentage >= 80 else '#f59e0b' if score_percentage >= 60 else '#ef4444')} 0%, 
                {('#059669' if score_percentage >= 80 else '#d97706' if score_percentage >= 60 else '#dc2626')} 100%);
        }}
        .status-badge {{ 
            display: inline-block; 
            padding: 12px 24px; 
            border-radius: 25px; 
            font-weight: 600; 
            margin: 15px 0;
            font-size: 1.1rem;
        }}
        .success {{ background: #d1fae5; color: #065f46; border: 2px solid #10b981; }}
        .warning {{ background: #fef3c7; color: #92400e; border: 2px solid #f59e0b; }}
        .error {{ background: #fee2e2; color: #991b1b; border: 2px solid #ef4444; }}
        .info {{ background: #dbeafe; color: #1e40af; border: 2px solid #3b82f6; }}
        
        .grid {{ 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); 
            gap: 25px; 
            margin: 30px 0;
        }}
        .category-card {{ 
            background: white; 
            border-radius: 12px; 
            box-shadow: 0 10px 25px rgba(0,0,0,0.1); 
            padding: 30px;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .category-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 15px 35px rgba(0,0,0,0.15);
        }}
        .category-header {{ 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            margin-bottom: 20px;
            border-bottom: 2px solid #f1f5f9;
            padding-bottom: 15px;
        }}
        .category-header h3 {{ 
            margin: 0; 
            color: #1e40af; 
            font-size: 1.4rem;
        }}
        .category-details {{ 
            space-y: 10px; 
        }}
        .detail-item {{ 
            display: flex; 
            justify-content: space-between; 
            padding: 8px 0;
            border-bottom: 1px solid #f1f5f9;
        }}
        .detail-label {{ 
            font-weight: 600; 
            color: #64748b; 
        }}
        .detail-value {{ 
            color: #1e293b; 
            font-weight: 500;
        }}
        .recommendations {{ 
            background: white; 
            border-radius: 12px; 
            box-shadow: 0 10px 25px rgba(0,0,0,0.1); 
            padding: 30px; 
            margin-top: 30px;
        }}
        .recommendations h2 {{ 
            color: #1e40af; 
            margin-top: 0; 
            font-size: 1.8rem;
        }}
        .recommendations ul {{ 
            list-style: none; 
            padding: 0; 
        }}
        .recommendations li {{ 
            padding: 12px 0; 
            border-bottom: 1px solid #f1f5f9;
            color: #475569;
            line-height: 1.6;
        }}
        .recommendations li:before {{ 
            content: "💡 "; 
            margin-right: 10px; 
        }}
        .metadata {{ 
            background: #f8fafc; 
            border-radius: 8px; 
            padding: 20px; 
            margin: 20px 0;
            font-size: 0.9rem;
            color: #64748b;
        }}
        .metadata-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }}
        .metadata-item {{
            display: flex;
            flex-direction: column;
        }}
        .metadata-label {{
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 4px;
        }}
        .footer {{ 
            text-align: center; 
            padding: 40px 20px; 
            color: rgba(255,255,255,0.8);
            font-size: 0.9rem;
        }}
        .links {{
            margin-top: 30px;
        }}
        .link {{ 
            display: inline-block; 
            background: #2563eb; 
            color: white; 
            padding: 14px 28px; 
            border-radius: 8px; 
            text-decoration: none; 
            margin: 10px 10px 10px 0; 
            transition: all 0.2s;
            font-weight: 600;
        }}
        .link:hover {{ 
            background: #1d4ed8; 
            transform: translateY(-2px); 
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header-card">
            <h1>🚀 DealerScope Validation Dashboard</h1>
            <div class="score-circle">
                {score_percentage}%
            </div>
            <div class="status-badge {status_class}">
                {status_icon} {overall_status}
            </div>
            
            <div class="metadata">
                <div class="metadata-grid">
                    <div class="metadata-item">
                        <span class="metadata-label">Generated</span>
                        <span>{summary_data.get('generated_at', 'Unknown')}</span>
                    </div>
                    <div class="metadata-item">
                        <span class="metadata-label">Commit</span>
                        <span>{summary_data.get('source_commit', 'Unknown')[:8]}</span>
                    </div>
                    <div class="metadata-item">
                        <span class="metadata-label">Workflow Run</span>
                        <span>#{summary_data.get('workflow_run', 'Unknown')}</span>
                    </div>
                    <div class="metadata-item">
                        <span class="metadata-label">Tests Summary</span>
                        <span>{summary_data.get('passed_tests', 0)} passed, {summary_data.get('failed_tests', 0)} failed, {summary_data.get('warned_tests', 0)} warnings</span>
                    </div>
                </div>
            </div>
            
            <div class="links">
                <a href="./summary.json" class="link">📄 View Raw JSON Data</a>
            </div>
        </div>
        
        <div class="grid">
            {categories_html}
        </div>
        
        <div class="recommendations">
            <h2>💡 Recommendations</h2>
            <ul>
                {recommendations_html}
            </ul>
        </div>
    </div>
    
    <div class="footer">
        <p>Generated by DealerScope Validation Suite • Built with ❤️ for production readiness</p>
    </div>
</body>
</html>
    """
    
    return html_content

def main():
    """Main function to generate HTML report"""
    reports_dir = os.path.join(os.getcwd(), 'validation-reports')
    final_dir = os.path.join(reports_dir, 'final')
    
    # Ensure final directory exists
    os.makedirs(final_dir, exist_ok=True)
    
    # Load summary data
    summary_data = load_summary_json(reports_dir)
    
    # Generate HTML report
    html_content = generate_html_report(summary_data)
    
    # Write index.html
    html_path = os.path.join(final_dir, 'index.html')
    with open(html_path, 'w') as f:
        f.write(html_content)
    
    print(f"✅ Generated HTML report: {html_path}")
    
    if summary_data:
        print(f"📊 Overall Status: {summary_data.get('overall_status', 'UNKNOWN')}")
        print(f"🎯 Score: {summary_data.get('score_percentage', 0)}%")
    
    return 0

if __name__ == '__main__':
    exit(main())