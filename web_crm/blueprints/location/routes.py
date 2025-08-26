from . import location_bp
from flask import jsonify
from database.db import get_db_cursor, release_connection

# --- Liste des pays ---
@location_bp.route("/countries")
def get_countries():
    conn, cur = get_db_cursor()
    try:
        cur.execute("SELECT iso2, name FROM countries ORDER BY name")
        rows = cur.fetchall()
        return jsonify([{"code": r["iso2"], "name": r["name"]} for r in rows])
    finally:
        cur.close()
        release_connection(conn)

# --- Liste des régions/admin1 par pays ---
@location_bp.route("/regions/<country_code>")
def get_regions(country_code):
    conn, cur = get_db_cursor()
    try:
        cur.execute(
            "SELECT code, name FROM admin1 WHERE country_code = %s ORDER BY name",
            (country_code,)
        )
        rows = cur.fetchall()
        return jsonify([{"code": r["code"], "name": r["name"]} for r in rows])
    finally:
        cur.close()
        release_connection(conn)

# --- Liste des villes par pays + région ---
@location_bp.route("/cities/<country_code>/<admin1_code>")
def get_cities(country_code, admin1_code):
    conn, cur = get_db_cursor()
    try:
        cur.execute(
            """
            SELECT geonameid, name
            FROM cities
            WHERE country_code = %s AND admin1_code = %s
            ORDER BY population DESC
            """,
            (country_code, admin1_code)
        )
        rows = cur.fetchall()
        return jsonify([{"id": r["geonameid"], "name": r["name"]} for r in rows])
    finally:
        cur.close()
        release_connection(conn)
