import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import sqlite3
import traceback
import os

conn = sqlite3.connect('parsed_data.sqlite')
cur = conn.cursor()


def country_ranking():

    cur.execute('''
    SELECT territory, COUNT(DISTINCT event_id) AS event_count
    FROM coordinates
    WHERE territory NOT IN ('Antarctica', 'high seas')
    GROUP BY territory
    ORDER BY event_count DESC
    LIMIT 10
    ''')

    rows = cur.fetchall()

    countries = [row[0] for row in rows]
    accumulations = [row[1] for row in rows]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(30, 7))

    # Linear scale
    bars1 = ax1.barh(countries, accumulations)
    ax1.invert_yaxis()
    ax1.set_xlabel('Number of Events', fontsize=12)
    ax1.set_title('Linear Scale (Actual data)', fontsize=15)
    ax1.bar_label(bars1, labels=[str(accul) for accul in accumulations], padding=4)

    # Log scale
    bars2 = ax2.barh(countries, accumulations)
    ax2.invert_yaxis()
    ax2.set_xscale('log')
    ax2.set_xlabel('Number of Events (log scale)', fontsize=12)
    ax2.set_title('Log Scale (Balanced view)', fontsize=15)
    ax2.bar_label(bars2, labels=[str(accul) for accul in accumulations], padding=4)


    fig.suptitle('Distribution of Natural Events Across Top 10 Countries', fontweight='bold', fontsize=20)
    plt.tight_layout()
    plt.savefig(f'{file_output}/country_ranking.png', dpi=150)
    plt.close()


def category_ranking():

    cur.execute('''
    SELECT title, COUNT(DISTINCT event_id) AS event_count
    FROM categories
    GROUP BY title
    ORDER BY event_count DESC
    LIMIT 5
    ''')

    rows = cur.fetchall()

    titles = [row[0] for row in rows]
    accumulations = [row[1] for row in rows]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(25, 6))

    # Linear scale
    bars1 = ax1.barh(titles, accumulations)
    ax1.invert_yaxis()
    ax1.set_xlabel('Number of Events', labelpad=15, fontsize=12)
    ax1.set_title('Linear Scale (Actual data)', fontsize=15)
    ax1.bar_label(bars1, labels=[str(accul) for accul in accumulations], padding=4)

    # Log scale
    bars2 = ax2.barh(titles, accumulations)
    ax2.invert_yaxis()
    ax2.set_xscale('log')
    ax2.set_xlabel('Number of Events (log scale)', labelpad=10, fontsize=12)
    ax2.set_title('Log Scale (Balanced view)', fontsize=15)
    ax2.bar_label(bars2, labels=[str(accul) for accul in accumulations], padding=4)


    fig.suptitle('Top 5 Natural Event Categories by Frequency', fontweight='bold', fontsize=20)
    plt.tight_layout()
    plt.savefig(f'{file_output}/category_ranking.png', dpi=150)
    plt.close()


def events_over_time():

    cur.execute('''
    SELECT title, strftime('%Y-%m', date) AS month, COUNT(DISTINCT event_id) AS event_count
    FROM timelines
    GROUP BY title, month
    ORDER BY title, month
    ''')
    rows = cur.fetchall()

    # Reshape into dict for easier graphing
    category_data = {}
    for title, month, count in rows:
        if title not in category_data:
            category_data[title] = {}

        category_data[title][month] = count


    category_colors = {
    'Wildfires': 'firebrick',
    'Floods': 'darkblue',
    'Severe Storms': 'indigo',
    'Sea and Lake Ice': 'royalblue',
    'Volcanoes': 'darkgoldenrod',
    'Drought': 'sienna',
    'Dust and Haze': 'grey',
    'Earthquakes': 'darkkhaki',
    'Landslides': 'saddlebrown',
    'Temperature Extremes': 'darkmagenta',
    'Water Color': 'seagreen',
    'Manmade': 'black',
    'Snow': 'skyblue'
    }


    #-----------------------------------------------FUNCTIONS---------------------------------------------------


    # Get default color cycle for new categories
    default_colors = plt.rcParams['axes.prop_cycle'].by_key()['color']
    color_counter = 0

    # check if title exists in category_color, if not generate, store then return new color
    def get_category_color(title):
    
        nonlocal color_counter

        if title in category_colors:
            return category_colors[title]

        # Pick then store new color (wrap color_counter to stays bounded)
        color = default_colors[color_counter % len(default_colors)]
        category_colors[title] = color
        color_counter = (color_counter + 1) % len(default_colors)

        return color

    # Extract title, YYYY-MM, and counts from category_data | dt = date
    def get_sorted(title):
        dates_counts = category_data[title]
        sorted_dates = sorted(dates_counts.keys())
        datatypes_dt = [datetime.strptime(dt, '%Y-%m') for dt in sorted_dates]
        counts = [dates_counts[dt] for dt in sorted_dates]

        return datatypes_dt, counts

    # Modify x-axis
    def apply_date_format(ax):
        locator = mdates.AutoDateLocator() # decides tick spacing based on data range
        formatter = mdates.ConciseDateFormatter(locator) # decides how verbose each label needs to be
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(formatter)


    #-----------------------------------------------------------------------------------------------------------


    unique_categories = sorted(category_data.keys())

    # INDIVIDUAL CHARTS
    for title in unique_categories:
        dates_dt, counts = get_sorted(title)
        color = get_category_color(title)

        fig, ax = plt.subplots(figsize=(16, 5))
        x = mdates.date2num(dates_dt) # Convert datetime to numbers
        ax.plot(x, counts, color=color, marker='o', markersize=3)
        ax.xaxis_date() # Tells apply_date_format() that x is datetime

        ax.set_title(f'Monthly Trend: {title}', fontweight='bold', fontsize=14)
        ax.set_xlabel('Date')
        ax.set_ylabel('Event Count')
        apply_date_format(ax)

        plt.tight_layout()
        safe_name = title.lower().replace(' ', '_')        
        plt.savefig(f'{file_output}/timeline_{safe_name}.png', dpi=150)
        plt.close(fig)



    # TRELLIS CHART | n refers to subplots
    n_categories = len(unique_categories)

    fig, axes = plt.subplots(
    n_categories, 1,
    figsize=(16, 3 * n_categories),
    sharex=True
    )

    if n_categories == 1:
        axes = [axes]


    for ax, title in zip(axes, unique_categories):
        dates_dt, counts = get_sorted(title)
        color = get_category_color(title)

        x = mdates.date2num(dates_dt)
        ax.plot(x, counts, color=color, marker='o', markersize=3)
        ax.xaxis_date()

        ax.set_title(title, fontsize=12)
        ax.set_ylabel('Event Count')
        apply_date_format(ax)

    axes[-1].set_xlabel('Date')
    fig.suptitle('Monthly Event Trends by Category', fontweight='bold', fontsize=18)
    plt.tight_layout(rect=(0, 0, 1, 0.97))
    plt.savefig(f'{file_output}/timeline_trellis.png', dpi=150)
    plt.close()


file_output = 'result_graphs'
os.makedirs(file_output, exist_ok=True)

try:
    print('Loading...')
    country_ranking()
    category_ranking()
    events_over_time()
    print(f'Data Graphing Success! Go to the {file_output} file to see the results')
    conn.commit()
except Exception as e:
    print('Undetected problem:', e)
    traceback.print_exc()
except KeyboardInterrupt:
    print('Program stopped by user')
finally:    
    cur.close()
    conn.close()