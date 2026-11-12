import sys, os
sys.path.insert(0, os.path.abspath("."))
from app.db import query_all, query_one

def main():
    print("=== LIVE DATABASE AUDIT ===")
    
    # 1. Version and DB name
    v = query_one("SELECT VERSION() as ver, DATABASE() as db;")
    print(f"MySQL Version: {v['ver']}, Current Database: {v['db']}")
    
    # 2. Tables and engine
    tables = query_all("""
        SELECT TABLE_NAME, ENGINE, TABLE_ROWS, TABLE_COLLATION 
        FROM INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_SCHEMA = 'ev_charging_db';
    """)
    print("\n--- TABLES & ENGINES ---")
    for t in tables:
        print(f"Table: {t['TABLE_NAME']} | Engine: {t['ENGINE']} | Estimated Rows: {t['TABLE_ROWS']} | Collation: {t['TABLE_COLLATION']}")
        
    # 3. Columns & constraints
    print("\n--- COLUMNS IN DETAIL ---")
    cols = query_all("""
        SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, COLUMN_DEFAULT, EXTRA
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'ev_charging_db'
        ORDER BY TABLE_NAME, ORDINAL_POSITION;
    """)
    for c in cols:
        print(f"{c['TABLE_NAME']}.{c['COLUMN_NAME']}: {c['COLUMN_TYPE']} (Null: {c['IS_NULLABLE']}, Key: {c['COLUMN_KEY']}, Default: {c['COLUMN_DEFAULT']})")
        
    # 4. Foreign Keys with Delete / Update Rules
    print("\n--- FOREIGN KEYS & RULES ---")
    fks = query_all("""
        SELECT 
            rc.CONSTRAINT_NAME,
            kcu.TABLE_NAME,
            kcu.COLUMN_NAME,
            kcu.REFERENCED_TABLE_NAME,
            kcu.REFERENCED_COLUMN_NAME,
            rc.UPDATE_RULE,
            rc.DELETE_RULE
        FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
        JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
            ON rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
            AND rc.CONSTRAINT_SCHEMA = kcu.TABLE_SCHEMA
        WHERE rc.CONSTRAINT_SCHEMA = 'ev_charging_db';
    """)
    for fk in fks:
        print(f"{fk['TABLE_NAME']}.{fk['COLUMN_NAME']} -> {fk['REFERENCED_TABLE_NAME']}.{fk['REFERENCED_COLUMN_NAME']} | ON DELETE: {fk['DELETE_RULE']} | ON UPDATE: {fk['UPDATE_RULE']}")

    # 5. Indexes
    print("\n--- INDEXES ---")
    idxs = query_all("""
        SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, COLUMN_NAME, SEQ_IN_INDEX
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = 'ev_charging_db'
        ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
    """)
    for idx in idxs:
        uniq = "UNIQUE" if idx['NON_UNIQUE'] == 0 else "NON-UNIQUE"
        print(f"{idx['TABLE_NAME']} | {idx['INDEX_NAME']} ({uniq}) -> {idx['COLUMN_NAME']} (#{idx['SEQ_IN_INDEX']})")

    # 6. Row counts in core tables
    print("\n--- EXACT ROW COUNTS ---")
    for tbl in ['Users', 'Vehicles', 'Stations', 'ChargingPoints', 'Bookings', 'ChargingSessions', 'Payments']:
        cnt = query_one(f"SELECT COUNT(*) as c FROM {tbl};")
        print(f"{tbl}: {cnt['c']} records")

if __name__ == '__main__':
    main()
