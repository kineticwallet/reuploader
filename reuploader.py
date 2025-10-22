from io import BytesIO
import json
import time
import requests

def warn(msg):
    print(f'\033[93m{msg}\033[0m')

def ratelimited_request(method: str, url: str, headers=None, data=None, files=None):
    try:
        response = requests.request(method, url, headers=headers, data=data, files=files)

        if response.status_code == 403 and 'x-csrf-token' in response.headers:
            csrf = str(response.headers.get('x-csrf-token', ''))
            globals()['csrf'] = csrf

            if headers is not None:
                headers['x-csrf-token'] = csrf
            
            warn(f'csrf token refreshed retrying {method} request to {url}')
            return ratelimited_request(method, url, headers, data, files)     

        remaining = response.headers.get('x-ratelimit-remaining')            
        reset = response.headers.get('x-ratelimit-reset')

        if response.status_code == 429 or (remaining is not None and reset is not None and int(remaining) == 0):
            warn(f'ratelimited waiting {reset}s before retrying {method} request to {url}')
            time.sleep(int(reset))
            return ratelimited_request(method, url, headers, data, files)

        return response   

    except requests.RequestException as e:
        warn(f'{method} request to {url} failed: {e}')

class Main():
    def init(self):
        cookie = open('cookie.txt', 'r')
        globals()['cookie'] = f'.ROBLOSECURITY={cookie.read()}'
        cookie.close()

        globals()['csrf'] = ''
        
        from_universe = int(input('Source Universe ID: '))        
        to_universe = int(input('Destination Universe ID: '))

        regional_pricing = bool(input('Enable Regional Pricing (y/n): ') == 'y')
        reupload_passes = bool(input('Reupload Passes (y/n): ').lower() == 'y')
        reupload_products = bool(input('Reupload Products (y/n): ').lower() == 'y')

        if not self.check_access_permissions(from_universe, to_universe):
            warn(f'missing access permission to {from_universe} or {to_universe}')
            return

        print('passed access check')    
        
        ids = {}

        if reupload_passes == True:
            passes = self.get_passes(from_universe)
            print('got all passes of source universe')

            if passes != None:
                infos = {}

                for gamepass in passes:
                    id = int(gamepass['id'])
                    infos[id] = self.get_pass_info(id)

                print('got all source pass infos')    

                image_urls = self.get_image_urls(*list(infos.values()))
                print('got all images for source passes')

                cnt = 0
                amt = len(passes)
                
                for gamepass in passes:
                    cnt += 1
                    id = int(gamepass['id'])
                    info = infos[id]
                    icon_image_asset_id = info.get('IconImageAssetId')
                    ##ids[str(id)] = self.upload_pass(str(gamepass['name']), str(info['Description']), gamepass['price'], image_urls.get(icon_image_asset_id, '') if icon_image_asset_id is not None else '', id, to_universe)
                    print(f'reuploaded {cnt}/{amt} passes', end='\r', flush=True)

                print(f'reuploaded all {amt} passes')

        if reupload_products == True:
            products = self.get_products(from_universe)
            print('got all products of source universe')

            if products != None:
                cnt = 0
                amt = len(products)
                ids = {}
                image_urls = self.get_image_urls(*products)
                print('got all images for source products')

                for product in products:
                    cnt += 1
                    id = int(product['ProductId'])
                    icon_image_asset_id = product.get('IconImageAssetId')
                    ##ids[str(id)] = self.upload_product(str(product['Name']), str(product['Description']), product['PriceInRobux'], image_urls.get(icon_image_asset_id, '') if icon_image_asset_id is not None else '', id, int(product['DeveloperProductId']), to_universe)       
                    print(f'reuploaded {cnt}/{amt} products', end='\r', flush=True)

                print(f'reuploaded all {amt} products')

        print(json.dumps(ids))
                    
    def get_headers(self):
        return {
            'Cookie': globals()['cookie'],
            'x-csrf-token':  globals()['csrf'],
        }        

    def check_access_permissions(self, *args):
        response = ratelimited_request("GET", f'https://develop.roblox.com/v1/universes/multiget/permissions?{'&'.join(f'ids={arg}' for arg in args)}', self.get_headers()) 

        if response.status_code != 200:
            warn(response.txt)       
            return False
        else:
            for universe in response.json().get('data', []):
                if not universe.get('canManage', False) or not universe.get('canCloudEdit', False):
                    return False

            return True              

    def get_passes(self, from_universe: int, cursor=None, passes=None):
        response = ratelimited_request("GET", f'https://games.roblox.com/v1/games/{from_universe}/game-passes?limit=100&sortOrder=1{f'&cursor={cursor}' if isinstance(cursor, str) else ''}', headers = self.get_headers())            

        if response.status_code != 200:
            warn(response.text)
            return
        else:
            json_response = response.json()
            data = json_response.get('data', [])
            next_page_cursor = json_response.get('nextPageCursor')

            if next_page_cursor != None:
                return self.getAllPasses(from_universe, next_page_cursor, data)
            else:
                if passes != None:
                    data.extend(passes)

                return data            

    def get_pass_info(self, id: int):
        response = ratelimited_request("GET", f'https://apis.roblox.com/game-passes/v1/game-passes/{id}/details', headers = self.get_headers())

        if response.status_code != 200:
            warn(response.text)
            return {}
        else:
            return response.json()
    
    def get_products(self, from_universe: int):
        response = ratelimited_request("GET", f'https://apis.roblox.com/developer-products/v2/universes/{from_universe}/developerproducts?limit=100000', headers = self.get_headers())

        if response.status_code != 200:
            warn(response.text)
            return
        else:
            return response.json().get('developerProducts', [])
        
    def get_image_urls(self, *args):
        response = ratelimited_request("GET", f'https://thumbnails.roblox.com/v1/assets?assetIds={','.join(f'{arg.get('iconImageAssetId') or arg.get('IconImageAssetId', 0)}' for arg in args if (id := arg.get('iconImageAssetId') or arg.get('IconImageAssetId')) is not None)}&returnPolicy=PlaceHolder&size=512x512&format=Png&isCircular=false', headers = self.get_headers())
        ## pass real
        if response.status_code != 200:
            warn(response.text)
            return {}
        else:
            image_urls = {}

            for image in response.json().get('data', []):
                target_id = image.get('targetId')
                image_url = image.get('imageUrl')

                if target_id and image_url:
                    image_urls[target_id] = image_url
                
            return image_urls    
        
    #def get_files(image: str):
    #    return {'File': BytesIO(ratelimited_request('GET', image).content)} if image != ''

    ##def upload_pass(self, name: str, description: str, price: int, image: str, pass_id: int, to_universe: int, regional_pricing: bool) -> int:
        
        ##response = ratelimited_request('POST', 'https://apis.roblox.com/game-passes/v1/game-passes', self.get_headers(), { 'Name': name, 'Description': description, 'UniverseId': to_universe }, self.get_files(image))
##
        ##if response.status_code == 200:
        ##    response = ratelimited_request('POST' f'https://apis.roblox.com/game-passes/v1/game-passes/{int(response.json().get('gamePassId'))}/details', self.get_headers(), { 'IsForSale': str(price != None).lower(), 'Price': str(price or '') }) ##regional pricing??
        ##    print(response.json())
        ##    if response.status_code != 200:
        ##        warn('')
        ##
        ##return 0 ## new id

    ##def upload_product(self, name: str, description: str, price: int, image: str, product_id: int, developer_product_id: int, to_universe: int, regional_pricing: bool) -> int:
        ##response = ratelimited_request('POST', f'''https://apis.roblox.com/developer-products/v1/universes/{to_universe}/developerproducts?name={name}&description={description}{f'&priceInRobux={price}' if price is not None else ''}''', self.get_headers())
##
        ##if response.status_code == 200:
        ##    response = ratelimited_request('GET', f'https://apis.roblox.com/developer-products/v1/developer-products/{developer_product_id}', self.get_headers())
        ##
        ##return 0 ## new id

if __name__ == '__main__':
    Main().init()