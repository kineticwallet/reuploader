from io import BytesIO
import json
from pathlib import Path
import time
import requests

session = requests.session()
session.headers.update({
    'Cookie': f'.ROBLOSECURITY={Path('cookie.txt').read_text()}',
    'x-csrf-token': ''
})

ignore = json.loads(Path('ignore.json').read_text())

from_universe = int(input('Source Universe ID: '))        
to_universe = int(input('Destination Universe ID: '))    

def yes_or_no(prompt: str) -> bool:
    return bool(input(prompt).lower() == 'y')

regional_pricing = yes_or_no('Enable Regional Pricing (y/n): ')
reupload_passes = yes_or_no('Reupload Passes (y/n): ')
reupload_products = yes_or_no('Reupload Products (y/n): ')

def warn(*args):
    print('\033[93m', *args, '\033[0m')

def ratelimited_request(method: str, url: str, data=None, files=None):
    try:
        response = session.request(method, url, data=data, files=files)
        csrf = response.headers.get('x-csrf-token')

        if response.status_code == 403 and csrf:
            session.headers['x-csrf-token'] = csrf
            warn(f'csrf token refreshed retrying {method} request to {url}')
            return ratelimited_request(method, url, data, files)     

        remaining = response.headers.get('x-ratelimit-remaining')         
        reset = response.headers.get('x-ratelimit-reset')

        if response.status_code == 429 or (remaining is not None and reset is not None and int(remaining) == 0):
            warn(f'ratelimited waiting {reset}s before retrying {method} request to {url}')
            time.sleep(int(reset))
            return ratelimited_request(method, url, data, files)

        if response.status_code != 200:
            warn(response.status_code, json.dumps(response.json(), indent=4))    
            return ratelimited_request(method, url, data, files)

        return response  

    except requests.RequestException as e:
        warn(f'{method} request to {url} failed: {e}') 

def get_access_permissions(self, *args) -> bool:
    response = ratelimited_request('GET', f'https://develop.roblox.com/v1/universes/multiget/permissions?{'&'.join(f'ids={arg}' for arg in args)}') 

    if response.status_code == 200:
        for universe in response.json().get('data', []):
                if not universe.get('canManage', False) or not universe.get('canCloudEdit', False):
                    return False

        return True                     

    return False

def get_all(url: str, key: str, cursor=None, all=None):
    response = ratelimited_request('GET', f'{url}{f'&cursor={cursor}' if isinstance(cursor, str) else ''}')

    if response.status_code == 200:
        json = response.json()
        data = json.get(key, [])
        next_page_cursor = json.get('nextPageCursor')

        if all:
            data.extend(all)

        if next_page_cursor:
            return get_all(url, key, next_page_cursor, data)

        return data    

def get_details(url: str, key: str, *args):
    details = {}

    for arg in args:
        id = arg.get(key)
        response = ratelimited_request('Get', url.format(id))

        if response.status_code == 200:
            details[id] = response.json() 
            continue

    return details        

def get_image_urls(key: str, *args):
    response = ratelimited_request('GET', f'https://thumbnails.roblox.com/v1/assets?assetIds={','.join(str(arg.get(key)) for arg in args if (id := arg.get(key)) is not None)}&returnPolicy=PlaceHolder&size=512x512&format=Png&isCircular=false')

    if response.status_code == 200:
        image_urls = {}

        for image in response.json().get('data', []):
            target_id = image.get('targetId')
            image_url = image.get('imageUrl')

            if target_id and image_url:
                image_urls[int(target_id)] = image_url

        return image_urls     

def get_image_bytes(image: str):
    if image != '':
        response = ratelimited_request('GET', image)

        if response.status_code == 200:
            return { 'file': BytesIO(response.content) }

def get_regional_pricing(details, key: str) -> bool:
    if not regional_pricing:
        return False

    try:
        return isinstance(details.get(key).get('enabledFeatures').index('RegionalPricing'), int)
    except: 
        return False

def upload_pass(details, image_url: str) -> int:
    response = ratelimited_request('POST', 'https://apis.roblox.com/game-passes/v1/game-passes', {
        'name': details['name'],
        'description': details['description'],
        'universeId': to_universe,
    }, get_image_bytes(image_url))
    
    if response.status_code == 200:
        data = { 'isForSale': details['isForSale'] }
        id = response.json()['gamePassId']

        if bool(details['isForSale']) == True:
            data['price'] = details['priceInformation']['defaultPriceInRobux']
            data['isRegionalPricingEnabled'] = get_regional_pricing(details, 'priceInformation')

        response = ratelimited_request('POST', f'https://apis.roblox.com/game-passes/v1/game-passes/{id}/details', data)

        if response.status_code == 200:
            return id

def upload_product(product, details, image_url: str) -> int: 
    
    ##print(product['ProductId'], get_regional_pricing(details, 'PriceInformation'), get_image_bytes(image_url, 'imageFile')) 
    return 0

if  get_access_permissions(from_universe, to_universe):
    if reupload_passes == True:
        passes = get_all(f'https://games.roblox.com/v1/games/{from_universe}/game-passes?limit=100', 'data')

        if passes:
            details = get_details('https://apis.roblox.com/game-passes/v1/game-passes/{}/details', 'id', *passes)
            image_urls = get_image_urls('iconAssetId', *list(details.values()))

            if details and image_urls:
                for info in details:
                     print(upload_pass(info, image_urls.get(int(info['iconAssetId']), '')))
                
    if reupload_products == True:   
        products = get_all(f'https://apis.roblox.com/developer-products/v2/universes/{from_universe}/developerproducts?limit=100', 'developerProducts')

        if products:
            details = get_details('https://apis.roblox.com/developer-products/v1/developer-products/{}/creator-details', 'ProductId', *products)
            image_urls = get_image_urls('IconImageAssetId', *list(details.values()))

            if details and image_urls:
                for product in products:
                    id = int(product['ProductId'])
                    info = details.get(id)

                    if info:
                        upload_product(product, info, image_urls.get(int(info['IconImageAssetId']), ''))
else:
    warn(f'missing access permission to {from_universe} or {to_universe}')

session.close()    
print('123')