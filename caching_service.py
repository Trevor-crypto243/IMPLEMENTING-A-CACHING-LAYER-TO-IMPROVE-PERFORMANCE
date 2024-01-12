from flask import current_app, make_response,Flask, jsonify, request
import redis
import json
from Utils import LocalConfigParser
from flask_restful import Resource, reqparse
import configparser
import jsonpickle


    # [BETNAREREDIS]
    # ussd_games_cache_period = 300
    # games_query_limit = 50
    # redis_host = localhost
    # redis_port = 6379
    # redis_db = 0
    # ; redis_password = 08b99124-b6ad-4c07-900a-040ff363a6b9
    # expiration = 500
    # caching_service_enabled = 1
    # jackpot_expiration = 3600
    # smartsoft_caching_enabled=1
    # smartsoft_expiration = 86400


class RedisCache:
    def __init__(self, config_section):
        redis_config = LocalConfigParser.parse_configs(config_section)
        self.redis_client = redis.Redis(
            host=redis_config['redis_host'],
            port=redis_config['redis_port'],
            db=redis_config['redis_db'],
            password=redis_config['redis_password']
        )
        self.expiration = redis_config['expiration']
        self.carousel_expiration = redis_config['carousel_images_expiration_period']

        self.smartsoft_expiration=redis_config['smartsoft_expiration']
        self.jackpot_expiration=redis_config['jackpot_expiration']

        self.universal_keys = {}
        self.smartsoft_enabled=redis_config['smartsoft_caching_enabled']
        self.cache_service_status = redis_config['caching_service_enabled']

    def set(self, name, value):
        if value:
            current_app.logger.info(f"Setting data in cache for key '{name}'")
            self.redis_client.set(name=name, value=json.dumps(value), ex=int(self.expiration))
    
    def set_carousel_images(self, name, value):
        if value:
            current_app.logger.info(f"Setting Carousel Images in cache for key '{name}'")
            self.redis_client.set(name=name, value=json.dumps(value), ex=int(self.carousel_expiration))
            
    def setSmartSoft(self, name, value):
        if value:
            current_app.logger.info(f"Setting data in cache for key '{name}'")
            self.redis_client.set(name=name, value=json.dumps(value), ex=int(self.smartsoft_expiration))

    def get(self, name, callback):
        cached_data = self.redis_client.get(name)
        if cached_data is not None:
            data = json.loads(cached_data)
            current_app.logger.info(f"Data found in cache for key '{name}'")
            # return make_response(json.dumps(data), 200, {'content-type': 'application/json'})
            return data
        else:
            current_app.logger.info(f"Data not found in cache for key '{name}', fetching from the source")
            return callback()
    
    def status(self):
        return self.cache_service_status
    
    def status_smartsoft(self):
        return self.smartsoft_enabled

    #***********************CACHING A SINGLE MATCH**********************************
    def set_cached_data_single(self, data, match_id):
        if match_id:
            current_app.logger.info(f"Match id received {match_id}")
            self.set(name="match_id", value=data)
            
    
    def get_cached_data_single(self, match_id,search_query,callback):
        if search_query:
            current_app.logger.info("*************Search query present - fetching from database")
            return callback()
        cached_match_id = self.redis_client.get(match_id)
        

        if cached_match_id is not None:
            data = json.loads(cached_match_id)
            current_app.logger.info("********FROM CACHE - SINGLE MATCH**************")          
            return data
        else:
            return callback()



    def get_cached_by_query(self, search_query, data):
        if data is not None:
            for dat in data:
                for key, value in dat.items():
                    if isinstance(value, str) and search_query.lower() in value.lower():
                        return True
            return False
        else:
            return False
    
    #*******************CACHING ALL MATCHES***********************
    def set_cached_data_all(self, limit, match_id, sport_id, tab, sub_type_id, data):
        current_app.logger.info("Setting cached data")
        # global self.universal_keys
        timeout = self.expiration

        # Create the universal key
        to_cache = {}
        to_cache["cached_limit"] = limit
        to_cache["cached_sport_id"] = sport_id
        to_cache["cached_tab"] = tab
        to_cache["cached_sub_type_id"] = sub_type_id
        universal_key = ''.join(str(value) for value in to_cache.values())

        if universal_key in self.universal_keys:
            current_app.logger.info("The key already exists")
        else:
            current_app.logger.info("The key doesn't exist")
            self.universal_keys[universal_key] = data

        self.set(name="match_id", value=match_id)
        self.set(name="cached_params", value=to_cache)
        self.set(name="cached_data", value=data)
        self.set(name="universal_keys", value=self.universal_keys)

        #set stand alone key
        self.set(name=universal_key,value=data)

        current_app.logger.info("Universal keys %r " % self.universal_keys.keys())
        current_app.logger.info("Universal keys sent to cache without converting to json %r " % self.universal_keys.keys())
        return data
    
    def get_cached_data_all(self, limit, sport_id, tab, sub_type_id, search_query,callback):
        if search_query:
            current_app.logger.info("*************Search query present - fetching from database")
            return callback()
         
        current_app.logger.info("***********From the cache***********")
        current_app.logger.info("+++++++++++++The status of the caching service is %r " % self.cache_service_status)

        
        params = {}
        params["limit"] = limit
        params["sport_id"] = sport_id
        params["tab"] = tab
        params["sub_type_id"] = sub_type_id
        # params["search_query"] = search_query


        # universal_key = ''.join(str(value) for value in to_cache.values())
        universal_key = ''.join(str(value) for value in params.values()) #was srequest
        cached_universal_keys = self.redis_client.get(universal_key)

        if cached_universal_keys is not None:
            data = json.loads(cached_universal_keys)
            return data
        else:
            return callback()   
       

    
        
class FlushCache(Resource):
    def __init__(self):
        self.redis_cache = RedisCache(config_section="BETNAREREDIS")
        
    def get(self):
        current_app.logger.info("Flushing all cache ")
        try:
            self.redis_cache.redis_client.flushall()
            return {"message": "Cache flushed successfully."}
        except Exception as e:
            return {"error": str(e)}
                
class FlushKey(Resource):
    def __init__(self):
        self.redis_cache = RedisCache(config_section="BETNAREREDIS")
    
    def post(self):
        current_app.logger.info("The payload received is %r " %request.json)
        try:
            key = request.json.get('key')
            self.redis_cache.redis_client.delete(key)
            # return {"message":f"Cache Key '{key}' flushed successfully"}
            return make_response(json.dumps({"message":"Cache Key flushed successfully"}),
                    200,
                    {'content-type':'application/json'})

        except Exception as e:
            return make_response(json.dumps({"error": str(e)}),
                                 200,
                    {'content-type':'application/json'})
            
class EditTimeOut(Resource):
    def update_config_expiration(self,new_expiration):

        try:
            config = configparser.ConfigParser()
            #config.read('configs/configs.local.ini')
            config.read('configs/configs.ini')

            # Change the expiration value under [REDIS]
            config.set('BETNAREREDIS', 'expiration', str(new_expiration))

            # Save the modified INI file
            with open('configs/configs.ini', 'w') as configfile:
                config.write(configfile)
            return True
        except Exception as e:
            return str(e)

    # Flask endpoint to edit the expiration in the configs
    def post(self):
        try:
            current_app.logger.info("The request is %r" %request.json.get('new_expiration'))

            new_expiration = int(request.json.get('new_expiration'))
            success = self.update_config_expiration(new_expiration)
            if success:
                # return jsonify({"message": "Expiration time updated successfully."}), 200
                return "Success"
            else:
                # return jsonify({"error": "Failed to update expiration time in config file."}), 500
                return {"error": "Failed to update expiration time in config file."}
        except ValueError:
            # return jsonify({"error": "Invalid expiration time."}), 400
            return {"error": "Invalid expiration time."}


