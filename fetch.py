import requests
import json, ijson
import sqlite3
from requests.exceptions import ConnectionError, Timeout
import sys
import time
from datetime import datetime

"""
------------------------------------------NOTE--------------------------------------------
I chose 10k for fetching a full year events (1k wasn't enough and it truncated the events)
For official NASA EONET maximum limit, I still can't find it.
Additionally, NASA EONET data can change over time so it may not be as accurate as you expected.
------------------------------------------------------------------------------------------
"""


# The first three functions check user inputs
def check_user_input():
    attempts_left = 3
    while attempts_left > 0:
        user = input('How many events do you want to fetch? (1-10000): ').strip()
        if not user : sys.exit(0)
            
        if user.isdecimal() and 1 <= int(user) <= 10000:
            return int(user)


        attempts_left -= 1
        if attempts_left > 0:
            print('Invalid Input! Please enter a number between 1 and 10000.')
        else:
            print('Invalid input, Try again next time!')
            sys.exit(0)



def check_status_input():
    attempts_left = 3
    while attempts_left > 0:
        status = input('Fetch which status? (open/closed/both): ').strip().lower()

        if status == "" or status == 'both':
            return 'all'
        if status in ('open', 'closed'):
            return status

        attempts_left -= 1
        if attempts_left > 0:
            print('Invalid input! Please type open, closed, both, or leave blank to skip.')
        else:
            print('Invalid input, Try again next time!')
            sys.exit(0)


def check_date_range(start_prompt, end_prompt):

    def check_date_input(prompt):
        attempts_left = 3
        while attempts_left > 0:
            user_date = input(prompt).strip()
            if user_date == '' or user_date.lower() == 'exit':
                sys.exit(0)

            try:
                datetime.strptime(user_date, '%Y-%m-%d')
                return user_date
            except ValueError:
                attempts_left -= 1
                if attempts_left > 0:
                    print('Invalid date format! Please use YYYY-MM-DD format, or leave blank to skip.')
                else:
                    print('Invalid input, Try again next time!')
                    sys.exit(0)

        return None

    attempts_left = 3
    while attempts_left > 0:
        start = check_date_input(start_prompt)
        end = check_date_input(end_prompt)

        # if either or both is None, skip it
        if start is None or end is None:
            return start, end

        if start <= end:
            return start, end

        attempts_left -= 1
        if attempts_left > 0:
            print(f'Start date ({start}) must be before or equal to end date ({end}). Please try again.')
        else:
            print('Invalid input, Try again next time!')
            sys.exit(0)

    return None, None


limit = check_user_input()
status = check_status_input()
start, end = check_date_range(
    'Start date (YYYY-MM-DD) [exit]: ',
    'End date (YYYY-MM-DD) [exit]: '
)


def build_query(limit, status=None, start=None, end=None):
    # params define what datatypes must be included, | means "or". Start dict with limit
    params: dict[str, str | int] = {'limit': limit}
    if status:
        params['status'] = status   
    if start:
        params['start'] = start
    if end:
        params['end'] = end

    return params

# example:
# https://eonet.gsfc.nasa.gov/api/v3/events?limit=10000&status=closed&start=2025-01-01&end=2025-12-31
params = build_query(limit, status, start, end)
query_string = '&'.join(f'{k}={v}' for k, v in params.items())
url = f'https://eonet.gsfc.nasa.gov/api/v3/events?{query_string}'


# session keeps one connection and reuses it multiple times
session = requests.Session()
session.headers.update({'User-Agent': 'EONET-Portfolio-Project (student research)'})

# this function deals with API error
def fetch_with_backoff(url, max_retries=4):
    delay = 3
    for attempt in range(max_retries):
        try:
            response = session.get(url, timeout=30, stream=True)
            if response.status_code in (429, 503):
                # we ask the server directly to ask how long we have to wait, the server give a number
                retry_after = response.headers.get('Retry-After')

                if retry_after:
                    wait = int(retry_after)
                else:
                    wait = delay

                print(f'Got {response.status_code} status code, waiting for {wait}s before retrying (attempt {attempt+1})...')
                time.sleep(wait)
                delay *= 2
                continue
            response.raise_for_status()
            return response
        except (Timeout, ConnectionError):
            print(f'Timed out, retrying in {delay}s...')
            time.sleep(delay)
            delay *= 2
    # safety guard, raises if max_retries achieved
    raise Exception('Max retries exceeded — fetching stopped to avoid further strain on the API')

print('Loading...')
try:
    response = fetch_with_backoff(url)
except Exception as e:
    print('There was an error during the API request:', e, '\n\nWait a while then try again!')
    sys.exit(0)



# Connect and create tables for data to be stored
conn = sqlite3.connect('raw_data.sqlite')
cur = conn.cursor()
cur.executescript('''
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        title TEXT,
        description TEXT,
        link TEXT,
        closed TEXT
    );

    CREATE TABLE IF NOT EXISTS event_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT,
        category_id TEXT,
        title TEXT,
        UNIQUE(event_id, category_id),                  --prevent duplicates
        FOREIGN KEY (event_id) REFERENCES events(id)
    );

    CREATE TABLE IF NOT EXISTS event_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT,
        source_id TEXT,
        url TEXT,
        UNIQUE(event_id, source_id),
        FOREIGN KEY (event_id) REFERENCES events(id)
    );

    CREATE TABLE IF NOT EXISTS event_geometry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT,
        magnitude_value REAL,
        magnitude_unit TEXT,
        date TEXT,
        type TEXT,
        lon REAL,
        lat REAL,
        coords TEXT,
        UNIQUE(event_id, date, lon, lat, coords),
        FOREIGN KEY (event_id) REFERENCES events(id)
    );
''')



success = True
event_count = 0
# Get each key-value pairs to be inserted into tables
try:
    for event in ijson.items(response.raw, 'events.item'):
        event_id = event['id']
        title = event.get('title')
        desc = event.get('description')
        link = event.get('link')
        closed = event.get('closed')

        event_count += 1

        cur.execute('INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?)',
                    (event_id, title, desc, link, closed))
 
        for cat in event['categories']:
            cat_id = cat['id']
            cat_title = cat['title']
            
            #   this parenthesis defines columns name must be and in what order ━━━━↴
            cur.execute('''INSERT OR IGNORE INTO event_categories (event_id, category_id, title)
                        VALUES (?, ?, ?)''', (event_id, cat_id, cat_title))


        for src in event['sources']:
            src_id = src['id']
            src_url = src['url']

            cur.execute('INSERT OR IGNORE INTO event_sources (event_id, source_id, url) VALUES (?, ?, ?)',
                        (event_id, src_id, src_url))


        for geo in event['geometry']:
            try:
                mag_val = float(geo.get('magnitudeValue')) # float(None)
            except TypeError:
                mag_val = None
            mag_un = geo.get('magnitudeUnit')
            date = geo['date']
            geo_type = geo['type']


            if geo_type.lower() == 'point':
                lon = float(geo['coordinates'][0])
                lat = float(geo['coordinates'][1])
                coords = None
            elif geo_type.lower() == 'polygon':
                lon = None
                lat = None
                coords = json.dumps(geo['coordinates'][0])
            else:
                print(f'Unknown geometry type: {geo_type}')
                continue


            cur.execute('''INSERT OR IGNORE INTO event_geometry
                        (event_id, magnitude_value, magnitude_unit, date, type, lon, lat, coords) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (event_id, mag_val, mag_un, date, geo_type, lon, lat, coords))


    #print(f'Debug: event_count = {event_count}') --for future debug if something wrong

except Exception as e:
    success = False
    print('Data stream was incomplete:', e)

finally:
    conn.commit()
    cur.close()
    conn.close()

# A warning -> It's ambiguous, can be the data is truly that many or real data got cut off by user limit 
if event_count == limit:
    print(f'Warning! returned {event_count} events, which equals your limit ({limit})')
    print('Data may be truncated — consider re-running with a higher limit for this date range\n' )

if success:
    print('Fetching Success! Go to raw_data.sqlite to see the result\n')
    print('-'*10, 'Go to parse.py to parse them further', 10*'-')
    print('For more accurate result, please wait for a few seconds before fetching again')
else:
    print('Fetching Failed! Try again next time')
