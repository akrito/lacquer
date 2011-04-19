import httplib
import redis
from urllib import quote as url_quote
from utils import parse_headers

def build_backend_request(self, addr, port, request):
    """
    Based on Ian Bicking's WSGIProxy (http://pythonpaste.org/wsgiproxy/)

    HTTP proxying WSGI application that proxies the exact request
    given in the environment.  All controls are passed through the
    environment.

    This connects to the server given in addr:port, and
    sends the Host header in HTTP_HOST -- they do not have to match.

    FIXME: Does not add X-Forwarded-For or other standard headers
    """
    env = request['env']
    headers = {}
    for key, value in env.items():
        if key.startswith('HTTP_'):
            key = key[5:].replace('_', '-').title()
            headers[key] = value
    path = (url_quote(env.get('SCRIPT_NAME', ''))
            + url_quote(env.get('PATH_INFO', '')))
    if env.get('QUERY_STRING'):
        path += '?' + env['QUERY_STRING']
    if env.get('CONTENT_TYPE'):
        headers['Content-Type'] = env['CONTENT_TYPE']
    if not path.startswith("/"):
        path = "/" + path
    request['path'] = path
    request['headers'] = headers
    return request

def send_backend_request(addr, port, request):
    body = request['body']
    env = request['env']
    path = request['path']
    headers = request['headers']
    conn = httplib.HTTPConnection('%s:%s' % (addr, port))
    conn.request(env['REQUEST_METHOD'],
                 path, body, headers)
    res = conn.getresponse()
    headers_out = parse_headers(res.msg)
    status = '%s %s' % (res.status, res.reason)
    length = res.getheader('content-length')
    # TODO: This shouldn't really read in all the content at once
    if length is not None:
        body = res.read(int(length))
    else:
        body = res.read()
    conn.close()
    return (status, headers_out, body)

def route(cls, request):
    routes = {
        'localhost:8444': ('localhost', 8000)
    }
    env = request['env']
    if env['HTTP_HOST'] in routes:
        return routes[env['HTTP_HOST']]
    return None

def get_cache(env):
    # if the request is a GET:
    #   if there are no cookies:
    #     get the thing
    #     if it's timed out:
    #       if grace is allowed:
    #         set the timeout to the future
    #         disallow grace
    #       return none
    #     else:
    #       return it
    return None

def set_cache(response):
    # set the object, timeout, and allow grace
    return None

