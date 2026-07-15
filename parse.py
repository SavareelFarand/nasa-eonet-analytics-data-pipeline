import sqlite3
import pandas as pd
import geopandas as gpd
import json
import re
import sys
import traceback

conn = sqlite3.connect('raw_data.sqlite')
cur = conn.cursor()

pars_conn = sqlite3.connect('parsed_data.sqlite')
pars_cur = pars_conn.cursor()

# Helper function for category() and timeline()
def clear_category(title, category_id):

    def is_blank(value):
        return value is None or value.strip() == ""


    try:
        if is_blank(title) and is_blank(category_id):
            return 'Unknown'
        elif not is_blank(title):
            return title.strip().title()
        else: 
            return re.sub(r'(?<!^)(?=[A-Z])', ' ', category_id).title() # separate word to make it readable
    except Exception as e:
        print('Datahelp error:', e)
        traceback.print_exc()
        sys.exit(1)



def territory():
    world = gpd.read_file('EEZ_land_union_v4_202410/EEZ_land_union_v4_202410.shp')

    pars_cur.execute('''
        CREATE TABLE IF NOT EXISTS coordinates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT,
            lon REAL,
            lat REAL,
            coords TEXT,
            territory TEXT,
            UNIQUE(event_id, lon, lat, coords)
        )
    ''')

    cur.execute('SELECT event_id, lon, lat, coords FROM event_geometry')


    try:
        data_points = cur.fetchall()
        points_data = []

        for event_id, lon, lat, coords in data_points:
            # Check if polygon
            if coords is not None:
                # parse to json
                polygon_points = json.loads(coords)

                if polygon_points:
                    center_lon = sum((p[0] for p in polygon_points)) / len(polygon_points)
                    center_lat = sum((p[1] for p in polygon_points)) / len(polygon_points)

                    polygon_json = coords
                else:
                    continue # Skip empty polygons

            else:
                center_lon = lon
                center_lat = lat
                polygon_json = None

            points_data.append((event_id, center_lon, center_lat, polygon_json))
        

        df = pd.DataFrame(points_data, columns=['event_id', 'lon', 'lat', 'polygon_coords'])
        gdf_points = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=world.crs)
        joins = gpd.sjoin(gdf_points, world, how='left', predicate='within')


        rows_to_insert = []

        for row in joins.itertuples():

            if pd.isna(row.SOVEREIGN1):
                if pd.to_numeric(row.lat) <= -60.0:
                    territory = 'Antarctica'
                else:
                    territory = 'high seas'

            else:
                territory = row.SOVEREIGN1

            rows_to_insert.append((row.event_id, row.lon, row.lat, row.polygon_coords, territory))

        pars_cur.executemany('''INSERT OR IGNORE INTO coordinates (event_id, lon, lat, coords, territory)
                                VALUES (?, ?, ?, ?, ?)''', rows_to_insert)
        pars_cur.execute('CREATE INDEX IF NOT EXISTS idx_coordinates_territory ON coordinates (territory)')

    except (sqlite3.OperationalError, Exception) as e:
            print('Dataparse1 error:', e)
            traceback.print_exc()
            sys.exit(1)


def category():
    pars_cur.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT,
            category_id TEXT,           -- Added this if I need to debug it elsewhere
            title TEXT,
            UNIQUE(event_id, category_id)
        )
    ''')

    cur.execute('SELECT event_id, category_id, title FROM event_categories')


    try:#  EONET_20558 |  wildfires  | Wildfires
        rows_to_insert = []
        for event_id,   category_id,   title in cur.fetchall():
            pars_title = clear_category(title, category_id)
            rows_to_insert.append((event_id, category_id, pars_title))

        pars_cur.executemany('''INSERT OR IGNORE INTO categories (event_id, category_id, title) 
                            VALUES (?, ?, ?)''', rows_to_insert)
        pars_cur.execute('CREATE INDEX IF NOT EXISTS idx_categories_title ON categories (title)')
    except (sqlite3.OperationalError, Exception) as e:
            print('Dataparse2 error:', e)
            traceback.print_exc()
            sys.exit(1)


def timeline():

    pars_cur.execute('''
        CREATE TABLE IF NOT EXISTS timelines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT,
            title TEXT,
            date TEXT,
            UNIQUE(event_id, date)
        )
    ''')

    cur.execute('''
        SELECT eg.event_id, ec.category_id, ec.title,
        SUBSTR(eg.date, 1, 10) AS date                  -- Take date format for ex. 2026-07-21
        FROM event_geometry AS eg
        JOIN event_categories AS ec ON eg.event_id = ec.event_id
    ''')

    try:    
        rows_to_insert = []
        for event_id, category_id, title, date in cur.fetchall():
            pars_title = clear_category(title, category_id)
            rows_to_insert.append((event_id, pars_title, date))

        pars_cur.executemany('INSERT OR IGNORE INTO timelines (event_id, title, date) VALUES (?, ?, ?)',
                            rows_to_insert)
        pars_cur.execute('CREATE INDEX IF NOT EXISTS idx_timelines_title_date ON timelines (title, date)')
    except (sqlite3.OperationalError, Exception) as e:
        print('Dataparse3 error', e)
        traceback.print_exc()
        sys.exit(1)


try:
    print('Loading...')
    territory()
    category()
    timeline()
    print('Parsing Success! Go to parse_data.sqlite to see the data')
    print('-'*10, 'Go to graph.py to see the graph of the data', 10*'-')
    pars_conn.commit()
except Exception as e:
    print('SQL Table Error:', e)
    traceback.print_exc()
except KeyboardInterrupt:
    print('Program stopped by the user')
finally:
    pars_cur.close()
    pars_conn.close()
    cur.close()
    conn.close()