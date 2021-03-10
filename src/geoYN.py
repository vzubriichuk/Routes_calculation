
from datetime import timedelta
from db_connect import DBConnect
from requests.packages.urllib3.exceptions import InsecureRequestWarning

import requests
import time
import warnings
import pandas as pd

# Get api_key from config
with open('config.ini', 'r') as f:
    for line in f:
        if line.startswith('api_key'):
            API_KEY = line[line.index(':') + 1:].strip()


def not_valid_response(text):
    ''' Function to catch API errors or empty responce.
    '''
    if not text:
        return True
    if text.find('Fatal error') != -1:
        return True
    if text.find('unexpected error') != -1:
        return True
    if text.find('ZERO_RESULTS') != -1:
        return True


def get_km_time(latA, lonA, latB, lonB, id_=None):
    ''' Returns km and time.
    Input: coordinates.
    Output: all route options (km, time) and selects fastest and shortest.
    '''
    global ERROR_COUNT
    if latA == latB and lonA == lonB:
        return [(0, 0), (0, 0)]  # the same object geographically
    url = f'https://maps.googleapis.com/maps/api/directions/json?units=metric' \
          f'&origin={latA}, {lonA}' \
          f'&destination={latB}%2C{lonB}' \
          f'&alternatives=true' \
          f'&key={API_KEY}'
    # hide warnings under unsecured ssl requests (corporate firewall return insecure ssl)
    warnings.simplefilter('ignore', InsecureRequestWarning)
    response = requests.get(url, verify=False, timeout=15)
    assert response.status_code == 200, 'Response status is {}'.format(
        response.status_code)
    try:
        data = response.json()
        routes = []
        # in response, there may be several options, we limit it to five
        for n in range(5):
            try:
                route = data['routes'][n]['legs'][0]['distance'], \
                        data['routes'][n]['legs'][0]['duration']
                row = [route[0]['value'] / 1000, route[1]['value']]
                routes.append(row)
            except IndexError:
                break

        matrix = pd.DataFrame(routes, columns=('KM', 'TIME'))
        shortest_route = matrix.loc[matrix['KM'].idxmin()]
        fastest_route = matrix.loc[matrix['TIME'].idxmin()]

    except TypeError:  # sometimes we have invalid response
        # if response is empty or API error
        if response.json()['status'] != "OK":
            with open('JSONerrors.txt', 'a') as f:
                f.write('{} {}\n'.format(id_, response.json()['status']))
        ERROR_COUNT = 0
        return [(0, 0), (0, 0)]
    return [(fastest_route[0], fastest_route[1]),
            (shortest_route[0], shortest_route[1])]


def geoYN(args, db_params):
    ''' Function that provides data translation between functions
        and contains main cycle for performing queries to API and
        updating data on server.
    '''
    # storage for distance and travel time
    with DBConnect(**db_params) as sql:
        if args.count:
            print("Кол-во маршрутов без расстояния: ", sql.count_empty_rows())
            return

    start = time.localtime()
    print(
        'Script started at {}.'.format(time.strftime("%d-%m-%Y %H:%M", start)))

    while True:
        try:
            with DBConnect(**db_params) as sql:
                # Row without distance
                row = sql.empty_dist()
                if not row:
                    break  # if no rows - we're done
                id_, _pointA, latA, lonA, _pointB, latB, lonB = row

                km_time = get_km_time(latA, lonA, latB, lonB, id_)
                # run update distance on server (fastest route, shortest route)
                sql.update_dist(id_, km_time)

                # tracking because script appeares to be frozen sometimes
                print(
                    "id = {}; fastest: km = {}; time = {}; shortest: km = {}; time = {}"
                    .format(id_, *km_time[0], *km_time[1]))
        except Exception as e:
            print('Row: ', row)
            print(e)
            time.sleep(3)

    end = time.localtime()
    print('Script ended at {}.'.format(time.strftime("%d-%m-%Y %H:%M", end)))
    print('Total duration: {}.'.format(
        timedelta(seconds=time.mktime(end) - time.mktime(start))))


if __name__ == '__main__':
    data = get_km_time(50.387212, 30.783950, 50.387212, 30.783950)
    msg = 'Please, ensure that {} returned by API is correct'
    assert float(data[0][0]) > 20, msg.format('distance')
    assert int(data[0][1]) > 100, msg.format('time')
    input('End\nPress "Enter" to exit...')
