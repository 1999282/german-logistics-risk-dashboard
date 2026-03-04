import sqlite3
import pandas as pd
import os

DB_NAME = "spatial_risk.db"
CSV_FILE = "unfallatlas_2022_geospatial.csv"

def run_sql_analysis():
    print(f"[*] Establishing connection to SQLite database: {DB_NAME}")
    conn = sqlite3.connect(DB_NAME)
    
    print(f"[*] Loading 250k+ record geospatial dataset into memory...")
    # Read the cleaned dataset
    try:
        # Some German ObjectIDs exceed SQLite's 64-bit integer limits. Parse them as strings or drop them.
        df = pd.read_csv(CSV_FILE, low_memory=False)
        for col in df.columns:
            if 'ID' in col.upper():
                df[col] = df[col].astype(str)
    except FileNotFoundError:
        print(f"[-] Error: Could not find {CSV_FILE}.")
        return

    print(f"[*] Ingesting DataFrame directly into SQLite table 'accidents'...")
    df.to_sql('accidents', conn, if_exists='replace', index=False)
    
    cursor = conn.cursor()
    
    # ---------------------------------------------------------
    # QUERY 1: High-Level Portfolio KPIs
    # ---------------------------------------------------------
    print("\n--- 1. OVERALL RISK VOLUME (C-SUITE KPIs) ---")
    q1 = """
    SELECT 
        COUNT(*) as total_accidents,
        SUM(CASE WHEN accident_severity = 'Fatal' THEN 1 ELSE 0 END) as total_fatalities,
        SUM(CASE WHEN accident_severity = 'Severe Injury' THEN 1 ELSE 0 END) as total_severe_injuries,
        SUM(CASE WHEN involved_bicycle = 1 THEN 1 ELSE 0 END) as bicycle_involved,
        SUM(CASE WHEN involved_truck = 1 THEN 1 ELSE 0 END) as truck_involved
    FROM accidents;
    """
    kpi_df = pd.read_sql_query(q1, conn)
    print(kpi_df.to_markdown(index=False))

    # ---------------------------------------------------------
    # QUERY 2: Regional Risk Profiling (by State - 'Land')
    # ---------------------------------------------------------
    print("\n--- 2. REGIONAL RISK PROFILING (TOP 5 WORST STATES) ---")
    # 'ULAND' is the statistical State Code in Germany (1-16)
    # We will map standard codes for readability.
    q2 = """
    SELECT 
        CASE 
            WHEN ULAND = 1 THEN 'Schleswig-Holstein'
            WHEN ULAND = 2 THEN 'Hamburg'
            WHEN ULAND = 3 THEN 'Niedersachsen'
            WHEN ULAND = 4 THEN 'Bremen'
            WHEN ULAND = 5 THEN 'Nordrhein-Westfalen'
            WHEN ULAND = 6 THEN 'Hessen'
            WHEN ULAND = 7 THEN 'Rheinland-Pfalz'
            WHEN ULAND = 8 THEN 'Baden-Württemberg'
            WHEN ULAND = 9 THEN 'Bayern'
            WHEN ULAND = 10 THEN 'Saarland'
            WHEN ULAND = 11 THEN 'Berlin'
            WHEN ULAND = 12 THEN 'Brandenburg'
            WHEN ULAND = 13 THEN 'Mecklenburg-Vorpommern'
            WHEN ULAND = 14 THEN 'Sachsen'
            WHEN ULAND = 15 THEN 'Sachsen-Anhalt'
            WHEN ULAND = 16 THEN 'Thüringen'
            ELSE 'Unknown'
        END as State,
        COUNT(*) as Total_Accidents,
        SUM(CASE WHEN accident_severity = 'Fatal' THEN 1 ELSE 0 END) as Fatal_Accidents
    FROM accidents
    GROUP BY ULAND
    ORDER BY Total_Accidents DESC
    LIMIT 5;
    """
    state_df = pd.read_sql_query(q2, conn)
    print(state_df.to_markdown(index=False))
    
    # ---------------------------------------------------------
    # QUERY 3: Delivery / Freight Risk (Trucks vs Cyclists)
    # ---------------------------------------------------------
    print("\n--- 3. LOGISTICS HAZARDS: SEVERE TRUCK VS BICYCLE COLLISIONS ---")
    q3 = """
    SELECT 
        UJAHR as Year,
        UMONAT as Month,
        COUNT(*) as Fatal_Truck_Bike_Collisions
    FROM accidents
    WHERE involved_truck = 1 AND involved_bicycle = 1 AND accident_severity = 'Fatal'
    GROUP BY UJAHR, UMONAT
    ORDER BY Fatal_Truck_Bike_Collisions DESC
    LIMIT 5;
    """
    truck_bike_df = pd.read_sql_query(q3, conn)
    print(truck_bike_df.to_markdown(index=False))

    # ---------------------------------------------------------
    # QUERY 4: Time of Day Risk Analysis
    # ---------------------------------------------------------
    print("\n--- 4. TEMPORAL RISK IDENTIFICATION ---")
    # UWOCHENTAG = Day of Week (1 = Sunday, 2 = Monday, etc.)
    # UStunde = Hour of Day
    q4 = """
    SELECT 
        UStunde as Hour_of_Day,
        COUNT(*) as Accident_Volume,
        ROUND(AVG(CASE WHEN accident_severity = 'Fatal' THEN 100.0 ELSE 0 END), 2) as Fatality_Rate_Percentage
    FROM accidents
    WHERE UStunde IS NOT NULL AND UStunde <= 24
    GROUP BY UStunde
    ORDER BY Accident_Volume DESC
    LIMIT 5;
    """
    time_df = pd.read_sql_query(q4, conn)
    print(time_df.to_markdown(index=False))

    print("\n[*] SQL Analysis COMPLETE. SQLite Database finalized.")
    conn.close()

if __name__ == "__main__":
    run_sql_analysis()
