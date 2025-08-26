import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from config import Config
import logging

# Pool de connexions
connection_pool = None

def init_db():
    """Initialise le pool de connexions"""
    global connection_pool
    try:
        connection_pool = SimpleConnectionPool(
            1, 20,  # min et max connexions
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            database=Config.DB_NAME,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD
        )
        logging.info("Pool de connexions PostgreSQL initialisé")
    except Exception as e:
        logging.error(f"Erreur initialisation DB: {e}")
        raise

def get_db_cursor():
    """Obtient une connexion et un curseur depuis le pool"""
    conn = connection_pool.getconn()
    return conn, conn.cursor(cursor_factory=RealDictCursor)

def release_connection(conn):
    """Retourne la connexion au pool"""
    connection_pool.putconn(conn)

def execute_query(query, params=None, fetch_one=False, fetch_all=False, commit=False):
    """Exécute une requête SQL"""
    conn = None
    try:
        conn, cursor = get_db_cursor()
        cursor.execute(query, params)
        
        if commit:
            conn.commit()
            
        if fetch_one:
            result = cursor.fetchone()
        elif fetch_all:
            result = cursor.fetchall()
        else:
            result = cursor.rowcount
            
        cursor.close()
        return result
        
    except Exception as e:
        if conn:
            conn.rollback()
        logging.error(f"Erreur requête SQL: {e}")
        raise
    finally:
        if conn:
            release_connection(conn)
