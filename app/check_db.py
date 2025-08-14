# check_db.py
import psycopg2
import os

# Direct connection parameters
DB_PARAMS = {
    "host": "dpg-d2e1kvbuibrs738im6s0-a.singapore-postgres.render.com",
    "port": 5432,
    "dbname": "thanyaaura_entitlement",
    "user": "thanyaaura_admin",
    "password": "YdIb7eiPjpYS5VcYfEltdEA2hIrME3mC",  # embedded for check
    "sslmode": "require",
}

def check_connection():
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        result = cur.fetchone()
        print(f"✅ DB connected successfully, SELECT 1 returned: {result[0]}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ DB connection failed: {e}")

if __name__ == "__main__":
    check_connection()
