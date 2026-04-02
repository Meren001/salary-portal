from flask import Flask, request, jsonify, render_template
import pandas as pd
import os
import glob
from flask_cors import CORS
import base64
from functools import wraps

app = Flask(__name__)
CORS(app)

# Path to your salary data folder
import os
DATA_FOLDER = os.path.join(os.getcwd(), "data")
file_path = os.path.join(DATA_FOLDER, "Regular Govt Employees details for SGSP and PSP.xlsx")
salary_data = None
def mask_account_number(acc):
    """Mask bank account number showing only last 4 digits"""
    if pd.isna(acc):
        return 'N/A'
    
    acc = str(acc).strip()
    
    if len(acc) <= 4:
        return acc
    
    return 'X' * (len(acc) - 4) + acc[-4:]

# Simple authentication check
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Check if it's Basic auth
        if not auth_header.startswith('Basic '):
            return jsonify({'error': 'Invalid authentication method'}), 401
        
        # Decode and check credentials (username: admin, password: portal123)
        encoded_credentials = auth_header.split(' ')[1]
        decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
        
        if decoded_credentials != 'admin:portal123':
            return jsonify({'error': 'Invalid credentials'}), 401
        
        return f(*args, **kwargs)
    return decorated

def load_salary_data():
    """Load all salary data from Excel/CSV files in the folder"""
    all_data = pd.DataFrame()
    
    # Look for Excel files
    excel_files = glob.glob(os.path.join(DATA_FOLDER, "*.xlsx")) + \
                  glob.glob(os.path.join(DATA_FOLDER, "*.xls"))
    
    # Look for CSV files
    csv_files = glob.glob(os.path.join(DATA_FOLDER, "*.csv"))
    
    all_files = excel_files + csv_files
    
    if not all_files:
        print(f"No Excel/CSV files found in {DATA_FOLDER}")
        print(f"Files in folder: {os.listdir(DATA_FOLDER)}")
        return pd.DataFrame()
    
    for file_path in all_files:
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext in ['.xlsx', '.xls']:
                # Read Excel file
                df = pd.read_excel(file_path)
            elif file_ext == '.csv':
                # Read CSV file
                df = pd.read_csv(file_path)
            else:
                continue
            
            print(f"DEBUG: Loaded {len(df)} records from {os.path.basename(file_path)}")
            print(f"DEBUG: Original columns: {list(df.columns)}")
            
            # Standardize column names - remove dots, spaces, make uppercase
            df.columns = df.columns.str.strip().str.replace(' ', '_').str.replace('.', '').str.upper()
            print(f"DEBUG: After standardization: {list(df.columns)}")
            
            # Check if FULLNAME column exists
            if 'FULLNAME' in df.columns:
                print(f"DEBUG: FULLNAME column found. First 5 names:")
                print(df['FULLNAME'].head().tolist())
            else:
                print(f"DEBUG: FULLNAME column NOT found!")
                # Try to find similar columns
                name_cols = [col for col in df.columns if 'NAME' in col or 'FULL' in col]
                if name_cols:
                    print(f"DEBUG: Using alternative column: {name_cols[0]}")
                    df = df.rename(columns={name_cols[0]: 'FULLNAME'})
            
            # Convert date columns
            for date_col in ['DOB', 'DOJ']:
                if date_col in df.columns:
                    df[date_col] = pd.to_datetime(df[date_col], errors='coerce').dt.strftime('%Y-%m-%d')
            
            # Convert numeric columns
            if 'GROSS' in df.columns:
                df['GROSS'] = pd.to_numeric(df['GROSS'], errors='coerce')
            
            # Fill NaN values in text columns
            text_columns = ['BANK_ADDRESS', 'BANKNAME', 'DESIGNATION', 'DEPARTMENT', 'CADRE']
            for col in text_columns:
                if col in df.columns:
                    df[col] = df[col].fillna('Not available')
            
            all_data = pd.concat([all_data, df], ignore_index=True)
            print(f"Successfully loaded {len(df)} records from {os.path.basename(file_path)}")
            
        except Exception as e:
            print(f"Error loading {file_path}: {str(e)}")
            continue
    
    print(f"DEBUG: Final data - {len(all_data)} total records")
    print(f"DEBUG: Final columns: {list(all_data.columns)}")
    
    return all_data

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/search', methods=['POST'])
def search_employee():
    try:
        data = request.json
        name = data.get('name', '').strip().lower()
        dob = data.get('dob', '').strip()
        
        print(f"\n=== SEARCH START ===")
        print(f"Searching for: name='{name}', dob='{dob}'")
        
        df = salary_data.copy()
        print(f"Total records loaded: {len(df)}")
        
        if df.empty:
            return jsonify({
                'success': False,
                'error': 'No salary data found in the system',
                'employees': []
            })
        
        # Check if FULLNAME column exists
        if 'FULLNAME' not in df.columns:
            print(f"ERROR: FULLNAME column not found!")
            print(f"Available columns: {list(df.columns)}")
            return jsonify({
                'success': False,
                'error': 'Name column not found in data',
                'employees': []
            })
        
        # Show all names containing the search term (for debugging)
        print(f"\nSearching for '{name}' in {len(df)} records...")
        
        # Create a mask for matching names
        original_count = len(df)
        
        # Method 1: Direct string contains (most common)
        mask = df['FULLNAME'].astype(str).str.lower().str.contains(name, na=False)
        matches_count = mask.sum()
        print(f"Method 1 (direct contains): Found {matches_count} matches")
        
        # If no matches, try more flexible methods
        if matches_count == 0 and name:
            print(f"No matches found with direct contains. Trying alternative methods...")
            
            # Method 2: Split search term and look for any part
            search_terms = name.split()
            if len(search_terms) > 1:
                for term in search_terms:
                    if len(term) > 2:  # Only search for terms longer than 2 chars
                        term_mask = df['FULLNAME'].astype(str).str.lower().str.contains(term, na=False)
                        matches_count = term_mask.sum()
                        print(f"  Searching for part '{term}': Found {matches_count} matches")
                        if matches_count > 0:
                            mask = term_mask
                            break
            
            # Method 3: Try searching in other columns too
            if matches_count == 0:
                print(f"Trying to search in all text columns...")
                text_columns = ['FULLNAME', 'DESIGNATION', 'DEPARTMENT', 'CADRE']
                combined_mask = pd.Series(False, index=df.index)
                
                for col in text_columns:
                    if col in df.columns:
                        col_mask = df[col].astype(str).str.lower().str.contains(name, na=False)
                        col_matches = col_mask.sum()
                        if col_matches > 0:
                            print(f"  Found {col_matches} matches in '{col}' column")
                            combined_mask = combined_mask | col_mask
                
                if combined_mask.sum() > 0:
                    mask = combined_mask
                    matches_count = mask.sum()
        
        # Apply the mask
        df = df[mask]
        print(f"Final matches: {len(df)} out of {original_count} records")
        
        # Show matching names
        if len(df) > 0:
            print(f"\nMatching names found:")
            for idx, (_, row) in enumerate(df.iterrows(), 1):
                print(f"  {idx}. {row.get('FULLNAME', 'N/A')}")
        
        # Filter by DOB if provided
        if dob and len(df) > 0:
            print(f"\nFiltering by DOB: '{dob}'")
            before_dob = len(df)
            df = df[df['DOB'].astype(str).str.contains(dob, na=False)]
            print(f"After DOB filter: {len(df)} matches (was {before_dob})")
        
        # Prepare results
        results = []
        for _, row in df.iterrows():
            employee = {
                'sl_no': 'N/A' if pd.isna(row.get('SLNO')) else row.get('SLNO'),
                'full_name': 'N/A' if pd.isna(row.get('FULLNAME')) else row.get('FULLNAME'),
                'dob': 'N/A' if pd.isna(row.get('DOB')) else row.get('DOB'),
                'doj': 'N/A' if pd.isna(row.get('DOJ')) else row.get('DOJ'),
                'designation': 'N/A' if pd.isna(row.get('DESIGNATION')) else row.get('DESIGNATION'),
                'department': 'N/A' if pd.isna(row.get('DEPARTMENT')) else row.get('DEPARTMENT'),
                'cadre': 'N/A' if pd.isna(row.get('CADRE')) else row.get('CADRE'),
                'bank_account_no': mask_account_number(row.get('BANK_AC_NO')),
                'bsr_code': 'N/A' if pd.isna(row.get('BSR_CODE')) else row.get('BSR_CODE'),
                'bank_address': 'Address not available' if pd.isna(row.get('BANK_ADDRESS')) else row.get('BANK_ADDRESS'),
                'bank_name': 'N/A' if pd.isna(row.get('BANKNAME')) else row.get('BANKNAME'),
                'gross_salary': f"₹{int(row.get('GROSS', 0)):,}" if pd.notna(row.get('GROSS')) else 'N/A',
                'raw_gross': float(row.get('GROSS', 0)) if pd.notna(row.get('GROSS')) else 0
            }
            results.append(employee)
        
        print(f"=== SEARCH END: Returning {len(results)} employees ===\n")
        
        return jsonify({
            'success': True,
            'count': len(results),
            'employees': results
        })
        
    except Exception as e:
        print(f"ERROR in search: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'employees': []
        }), 500

@app.route('/api/stats', methods=['GET'])
@require_auth
def get_stats():
    try:
        df = load_salary_data()
        
        if df.empty:
            return jsonify({
                'success': False,
                'error': 'No data loaded',
                'stats': {}
            })
        
        stats = {
            'total_employees': len(df),
            'departments': df['DEPARTMENT'].nunique() if 'DEPARTMENT' in df.columns else 0,
            'data_loaded': True,
            'columns_found': list(df.columns)
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    print("Loading salary data...")
    salary_data = load_salary_data()
    print(f"Loaded {len(salary_data)} records")
    print("Server starting at http://localhost:5000")
    print("Access from other devices: http://YOUR_IP:5000")
    app.run(debug=False, host='0.0.0.0', port=5000)

    