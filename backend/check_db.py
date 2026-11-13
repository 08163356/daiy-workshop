import sqlite3

conn = sqlite3.connect('reading_system.db')

# List all tables
print("=== All tables ===")
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cursor.fetchall()]
for t in tables:
    print(f"  {t}")

# Check time_logs if exists
if 'time_logs' in tables:
    print("\n=== time_logs columns ===")
    cursor = conn.execute("PRAGMA table_info(time_logs)")
    for col in cursor.fetchall():
        print(f"  {col[1]:20s} {col[2]:20s} nullable={not col[3]} default={col[4]}")

    print("\n=== time_logs records ===")
    cursor = conn.execute("SELECT COUNT(*) FROM time_logs")
    count = cursor.fetchone()[0]
    print(f"  Total records: {count}")
else:
    print("\ntime_logs table does not exist!")

conn.close()
