# utils/db_logger_pg.py


import psycopg2

import json

import os

from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()

IST = timezone(timedelta(hours=5, minutes=30))

DB_CONFIG = {

    "host": os.getenv("POSTGRES_HOST"),

    "port": os.getenv("POSTGRES_PORT"),

    "dbname": os.getenv("POSTGRES_DB"),

    "user": os.getenv("POSTGRES_USER"),

    "password": os.getenv("POSTGRES_PASSWORD"),

}
 
 
def get_pg_connection():

    return psycopg2.connect(**DB_CONFIG)

def create_tractor_valuation_table():
    """
    Create tractor_valuation_data table if it doesn't exist
    """
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        # Create table with proper schema
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS tractor_valuation_data (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            data_json JSONB NOT NULL,
            image_urls JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Create index on user_id for faster queries
        CREATE INDEX IF NOT EXISTS idx_tractor_valuation_user_id ON tractor_valuation_data(user_id);
        
        -- Create index on created_at for time-based queries
        CREATE INDEX IF NOT EXISTS idx_tractor_valuation_created_at ON tractor_valuation_data(created_at);
        """
        
        cursor.execute(create_table_sql)
        conn.commit()
        cursor.close()
        conn.close()
        
        print("[DB SUCCESS] tractor_valuation_data table created/verified successfully")
        return True
        
    except Exception as e:
        print(f"[DB ERROR - create_tractor_valuation_table]: {e}")
        return False
 
 
def log_message(user_id, api, message):

    try:

        conn = get_pg_connection()

        cursor = conn.cursor()

        cursor.execute(

            "INSERT INTO message_logs (user_id, api, message) VALUES (%s, %s, %s)",

            (user_id, api, message),

        )

        conn.commit()

        cursor.close()

        conn.close()

    except Exception as e:

        print("[DB ERROR - log_message]:", e)
 
 
def save_tractor_data(user_id, eval_data, image_urls=None):

    try:
        # Ensure table exists before inserting
        create_tractor_valuation_table()
        
        conn = get_pg_connection()
        cursor = conn.cursor()

        # Add image URLs to eval_data if provided
        if image_urls:
            eval_data['image_urls'] = image_urls

        # Insert into tractor_valuation_data table
        cursor.execute(
            "INSERT INTO tractor_valuation_data (user_id, data_json, image_urls) VALUES (%s, %s, %s)",
            (user_id, json.dumps(eval_data, ensure_ascii=False), json.dumps(image_urls) if image_urls else None),
        )

        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"[DB SUCCESS] Saved tractor data for user {user_id}")

    except Exception as e:
        print(f"[DB ERROR - save_tractor_data]: {e}")

def get_tractor_data(user_id):
    """
    Retrieve tractor valuation data for a specific user
    """
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT data_json, image_urls, created_at FROM tractor_valuation_data WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        )
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            data_json, image_urls, created_at = result
            return {
                'data_json': json.loads(data_json),
                'image_urls': json.loads(image_urls) if image_urls else [],
                'created_at': created_at
            }
        return None
        
    except Exception as e:
        print(f"[DB ERROR - get_tractor_data]: {e}")
        return None

def get_all_tractor_data():
    """
    Retrieve all tractor valuation data
    """
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT user_id, data_json, image_urls, created_at FROM tractor_valuation_data ORDER BY created_at DESC"
        )
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        data = []
        for row in results:
            user_id, data_json, image_urls, created_at = row
            data.append({
                'user_id': user_id,
                'data_json': json.loads(data_json),
                'image_urls': json.loads(image_urls) if image_urls else [],
                'created_at': created_at
            })
        
        return data
        
    except Exception as e:
        print(f"[DB ERROR - get_all_tractor_data]: {e}")
        return []

 

def save_user_activity(user_id=None, utm_source=None, image_url=None, stage=None):
    """
    Insert or update user_activity:
    - First visit → insert new row with created_at = updated_at = now()
    - Repeat visit → update record, preserve created_at, update updated_at
    - Append new image_url to existing image_url JSON array
    """
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
 
        # First, try to alter the existing table if user_id is INTEGER
        try:
            cursor.execute("""
                ALTER TABLE user_activity 
                ALTER COLUMN user_id TYPE VARCHAR(255);
            """)
            conn.commit()
            print("[DB INFO] Successfully altered user_activity.user_id to VARCHAR(255)")
        except Exception as alter_error:
            # If alter fails, the table might not exist or column might already be VARCHAR
            print(f"[DB INFO] Alter failed (expected if table doesn't exist or column is already VARCHAR): {alter_error}")
            
            # Create table if it doesn't exist
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS user_activity (
                user_id VARCHAR(255) PRIMARY KEY,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                utm_source VARCHAR(255),
                image_url JSONB,
                stage VARCHAR(100)
            );
            """
            cursor.execute(create_table_sql)
 
        now_ist = datetime.now(IST)
 
        cursor.execute("""
            SELECT created_at, image_url
            FROM user_activity
            WHERE user_id = %s;
        """, (user_id,))
        existing = cursor.fetchone()
 
        if existing:
            original_created_at, existing_image_url = existing
 
            if existing_image_url:
                try:
                    current_images = existing_image_url if isinstance(existing_image_url, list) else []
                except Exception:
                    current_images = []
            else:
                current_images = []
 
           
            if image_url:
                current_images.append(image_url)
 
           
            cursor.execute("""
                UPDATE user_activity
                SET updated_at = %s,
                    utm_source = %s,
                    image_url = %s,
                    stage = %s
                WHERE user_id = %s;
            """, (
                now_ist,
                utm_source,
                json.dumps(current_images),
                stage,
                user_id
            ))
 
            print(f"[DB INFO] Updated user {user_id} (preserved created_at={original_created_at})")
 
        else:
           
            cursor.execute("""
                INSERT INTO user_activity (
                    user_id, created_at, updated_at, utm_source, image_url, stage
                )
                VALUES (%s, %s, %s, %s, %s, %s);
            """, (
                user_id,
                now_ist,
                now_ist,
                utm_source,
                json.dumps([image_url]) if image_url else json.dumps([]),
                stage
            ))
            print(f"[DB INFO] Inserted new user {user_id}")
 
        conn.commit()
        cursor.close()
        conn.close()
 
        return user_id
 
    except Exception as e:
        print(f"[DB ERROR - save_user_activity]: {e}")
        return None

def get_user_activity(start_date=None, end_date=None):
    """
    Retrieve all user activity data from user_activity table
    Optionally filter by date range (start_date and end_date should be in 'YYYY-MM-DD' format)
    Filters are applied on the 'created_at' column
    """
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        # Build query with optional date filters on created_at
        query = "SELECT user_id, created_at, updated_at, utm_source, image_url, stage FROM user_activity"
        params = []
        
        # Add date filtering if provided (filters on created_at field)
        where_clauses = []
        if start_date:
            where_clauses.append("DATE(created_at) >= %s")
            params.append(start_date)
            print(f"[DB INFO] Filtering with start_date: {start_date}")
        if end_date:
            where_clauses.append("DATE(created_at) <= %s")
            params.append(end_date)
            print(f"[DB INFO] Filtering with end_date: {end_date}")
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += " ORDER BY created_at DESC"
        
        print(f"[DB INFO] Executing query: {query} with params: {params}")
        cursor.execute(query, params)
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        data = []
        for row in results:
            user_id, created_at, updated_at, utm_source, image_url, stage = row
            data.append({
                'user_id': user_id,
                'created_at': created_at.isoformat() if created_at else None,
                'updated_at': updated_at.isoformat() if updated_at else None,
                'utm_source': utm_source,
                'image_url': image_url if image_url else [],
                'stage': stage
            })
        
        print(f"[DB SUCCESS] Retrieved {len(data)} user activity records")
        return data
        
    except Exception as e:
        print(f"[DB ERROR - get_user_activity]: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_user_activity_by_id(user_id):
    """
    Retrieve user activity data for a specific user
    """
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT user_id, created_at, updated_at, utm_source, image_url, stage FROM user_activity WHERE user_id = %s",
            (user_id,)
        )
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            user_id, created_at, updated_at, utm_source, image_url, stage = result
            return {
                'user_id': user_id,
                'created_at': created_at.isoformat() if created_at else None,
                'updated_at': updated_at.isoformat() if updated_at else None,
                'utm_source': utm_source,
                'image_url': image_url if image_url else [],
                'stage': stage
            }
        return None
        
    except Exception as e:
        print(f"[DB ERROR - get_user_activity_by_id]: {e}")
        return None