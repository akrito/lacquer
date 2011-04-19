import cPickle
import redis
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

def ohash(bereq):
    return bereq['env']['HTTP_HOST'] + bereq['path']

def cache_get(bereq):
    # if the request is a GET:
    if bereq['env']['REQUEST_METHOD'] == 'GET':
        # if there are no cookies:
        if 'Cookie' not in bereq['headers']:
            # get the thing
            obj_hash = ohash(bereq)
            print obj_hash
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
            obj = r[obj_hash]
            if obj is not None:
                return cPickle.loads(obj)
    return None
    #     if it's timed out:
    #       if grace is allowed:
    #         set the timeout to the future
    #         disallow grace
    #       return none
    #     else:
    #       return it

def cache_set(status, headers, body, bereq):
    if status == '200 OK':
        # set the object, timeout, and allow grace
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
        r[ohash(bereq)] = cPickle.dumps({
            'status': status,
            'headers': headers,
            'body': body,
            })
