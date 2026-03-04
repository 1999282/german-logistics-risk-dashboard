import os
import requests
import zipfile
import pandas as pd
from pyproj import Transformer
import sys

# Constants
DEST_FOLDER = "data"
RAW_ZIP_PATH = os.path.join(DEST_FOLDER, "unfallatlas.zip")
EXTRACT_FOLDER = os.path.join(DEST_FOLDER, "raw")
OUTPUT_CSV = "unfallatlas_2022_geospatial.csv"

# Official Open Data Link for the 2022 Traffic Accident Atlas (Unfallatlas)
# Provided by German Federal States / Destatis 
DOWNLOAD_URL = "https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas/Unfallorte2022_EPSG25832_CSV.zip"

def download_and_extract():
    if not os.path.exists(DEST_FOLDER):
        os.makedirs(DEST_FOLDER)
    
    # 1. Download
    print(f"[*] Downloading massive Unfallatlas 2022 dataset (~30MB ZIP)...")
    try:
        response = requests.get(DOWNLOAD_URL, stream=True)
        response.raise_for_status()
        with open(RAW_ZIP_PATH, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print("[+] Download complete.")
    except Exception as e:
        print(f"[-] Download failed: {e}")
        print("[!] Ensure you have internet access and the server is up.")
        sys.exit(1)

    # 2. Extract
    print(f"[*] Extracting CSVs...")
    with zipfile.ZipFile(RAW_ZIP_PATH, 'r') as zip_ref:
        zip_ref.extractall(EXTRACT_FOLDER)
    
    # Locate the CSV file (it might have a varying name)
    csv_files = []
    for root, dirs, files in os.walk(EXTRACT_FOLDER):
        for file in files:
            if file.endswith('.csv'):
                csv_files.append(os.path.join(root, file))
    
    if not csv_files:
        print("[-] Error: No CSV file found in the extracted contents.")
        sys.exit(1)
        
    target_csv = csv_files[0]
    for c in csv_files:
        if '2022' in c.lower() and 'lin' not in c.lower(): # Avoid line strings
            target_csv = c
            break
            
    print(f"[+] Found target CSV: {target_csv}")
    return target_csv

def process_and_project(target_csv):
    print("[*] Loading payload into Pandas (this may take a moment)...")
    # German CSVs usually use ';' as separator and ',' for decimals, but Unfallatlas usually uses ';'
    try:
        df = pd.read_csv(target_csv, sep=';', encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(target_csv, sep=';', encoding='latin1')
        
    print(f"[+] Successfully loaded {len(df):,} accident records.")
    
    print("[*] Engineering Geospatial Features: Converting EPSG:25832 (UTM32N) to EPSG:4326 (Lat/Lon)...")
    # Destatis provides X and Y coordinates in EPSG:25832. 
    # PyDeck/Streamlit requires standard WGS84 Latitude and Longitude.
    
    # Check column names. Sometime they are XGCSWGS84, but if we only have X/Y, we project.
    if 'XGCSWGS84' in df.columns and 'YGCSWGS84' in df.columns:
        print("[+] WGS84 coordinates already exist in dataset. Mapping directly.")
        df['longitude'] = pd.to_numeric(df['XGCSWGS84'].astype(str).str.replace(',', '.'), errors='coerce')
        df['latitude'] = pd.to_numeric(df['YGCSWGS84'].astype(str).str.replace(',', '.'), errors='coerce')
    elif 'X' in df.columns and 'Y' in df.columns:
        print("[*] Performing live geospatial projection...")
        # Clean comma decimals if present
        x_coords = pd.to_numeric(df['X'].astype(str).str.replace(',', '.'), errors='coerce')
        y_coords = pd.to_numeric(df['Y'].astype(str).str.replace(',', '.'), errors='coerce')
        
        # Initialize pyproj transformer
        transformer = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(x_coords.values, y_coords.values)
        
        df['longitude'] = lon
        df['latitude'] = lat
    else:
        print("[-] Could not find spatial coordinate columns (X/Y or WGS84).")
        print(df.columns)
        sys.exit(1)
        
    # Drop rows without valid coordinates
    df_clean = df.dropna(subset=['latitude', 'longitude']).copy()
    
    print(f"[*] Basic cleaning: Translating key columns for international C-Suite audience...")
    # Map german severity classifications to English
    # UKATEGORY: 1 = Fatal, 2 = Severe Injury, 3 = Light Injury
    severity_map = {1: 'Fatal', 2: 'Severe Injury', 3: 'Light Injury'}
    if 'UKATEGORIE' in df_clean.columns:
        df_clean['accident_severity'] = df_clean['UKATEGORIE'].map(severity_map)
        
    # Translate boolean vehicle involvement
    bool_columns = {
        'IstRad': 'involved_bicycle',
        'IstPKW': 'involved_car',
        'IstFuss': 'involved_pedestrian',
        'IstKrad': 'involved_motorcycle',
        'IstGkfz': 'involved_truck',
        'IstSonstige': 'involved_other'
    }
    for old, new in bool_columns.items():
        if old in df_clean.columns:
            # Usually 1 = true, 0 = false
            df_clean[new] = df_clean[old] == 1
            
    # Export the engineered layer
    print(f"[*] Exporting optimal geospatial layer for PyDeck: {OUTPUT_CSV}")
    df_clean.to_csv(OUTPUT_CSV, index=False)
    print(f"[+] SUCCESS: Final geospatial dataset contains {len(df_clean):,} validated rows.")
    print(f"[+] Ready for SQL Spatial joins and Streamlit 3D Mapping.")

if __name__ == "__main__":
    target = download_and_extract()
    process_and_project(target)
