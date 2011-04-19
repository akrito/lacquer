from bsddb3 import db
import cPickle
import os
import shutil

dirname = '/Users/alex/bdb'
filename = '/Users/alex/bdbcache'

db_env = db.DBEnv()
db_env.set_lk_detect(db.DB_LOCK_YOUNGEST)
db_env.open(dirname, db.DB_INIT_LOCK|db.DB_CREATE| db.DB_INIT_MPOOL)
        
cache = db.DB(db_env)
cache.open(filename, None, db.DB_HASH, db.DB_CREATE)
    
def ohash(bereq):
    return bereq['env']['HTTP_HOST'] + bereq['path']

def cache_get(bereq):
    # if the request is a GET:
    if bereq['env']['REQUEST_METHOD'] == 'GET':
        # if there are no cookies:
        if 'Cookie' not in bereq['headers']:
            # get the thing
            obj_hash = ohash(bereq)
            if obj_hash in cache:
                obj = cache[obj_hash]
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
        cache[ohash(bereq)] = cPickle.dumps({
            'status': status,
            'headers': headers,
            'body': body,
            })
