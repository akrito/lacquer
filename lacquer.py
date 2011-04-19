from gevent import fork, monkey, pywsgi, spawn
monkey.patch_all()
from gevent_zeromq import zmq
import marshal
import os
import redis
import sys

C = zmq.Context()


class Master(object):

    def __init__(self, addr, port, cmd_addr, cmd_port):
        self.server = pywsgi.WSGIServer((addr, port), handle_wsgi)
        self.server.pre_start()
        self.addr = addr
        self.port = port
        self.cmd_addr = cmd_addr
        self.cmd_port = cmd_port
        self.workers = []

    def listen(self):
        socket = C.socket(zmq.REP)
        socket.bind('tcp://%s:%s' % (self.cmd_addr, self.cmd_port))
        while True:
            bits = socket.recv_pyobj()
            if not isinstance(bits, list):
                continue
            cmd, args = bits[0], bits[1:]
            method = getattr(self, 'cmd_%s' % cmd, None)
            if callable(method):
                socket.send_pyobj(method.__call__(*args))
                continue
            socket.send_pyobj(None)

    def start(self):
        self.greenlet = spawn(self.listen)

    def wait(self):
        self.greenlet.join()

    def cmd_start_workers(self, num_workers):
        worker_pids = []
        for i in range(num_workers):
            pid = fork()
            if pid == 0:
                # I've been forked
                w = Worker(self.server)
                print 'Serving on https://%s:%s' % (self.addr, self.port)
                w.start()
            if pid:
                # I'm the main process
                worker_pids.append(pid)

    def cmd_restart_workers(self):
        pass


class Worker(object):

    def __init__(self, server):
        self.server = server

    def start(self):
        self.server.start()
        socket = C.socket(zmq.REP)
        socket.bind('inproc://worker%s' % os.getpid())
        while True:
            bits = socket.recv_pyobj()
            if not isinstance(bits, list):
                continue
            cmd, args = bits[0], bits[1:]
            method = getattr(self, 'cmd_%s' % cmd, None)
            if callable(method):
                method.__call__(self, *args)


class BackendManager(object):
    """
    Simple connection manager. Sends request to the backend in the same greenlet
    """

    @classmethod
    def send(self, addr, port, package):
        """
        Based on Ian Bicking's WSGIProxy (http://pythonpaste.org/wsgiproxy/)
    
        HTTP proxying WSGI application that proxies the exact request
        given in the environment.  All controls are passed through the
        environment.
    
        This connects to the server given in addr:port, and
        sends the Host header in HTTP_HOST -- they do not have to match.
    
        FIXME: Does not add X-Forwarded-For or other standard headers
        """
        import httplib
        from urllib import quote as url_quote

        environ = package['env']
    
        scheme = environ['wsgi.url_scheme']
        if scheme == 'http':
            ConnClass = httplib.HTTPConnection
        elif scheme == 'https':
            ConnClass = httplib.HTTPSConnection
        else:
            raise ValueError(
                "Unknown scheme: %r" % scheme)
        conn = ConnClass('%s:%s' % (addr, port))
        headers = {}
        for key, value in environ.items():
            if key.startswith('HTTP_'):
                key = key[5:].replace('_', '-').title()
                headers[key] = value
        path = (url_quote(environ.get('SCRIPT_NAME', ''))
                + url_quote(environ.get('PATH_INFO', '')))
        if environ.get('QUERY_STRING'):
            path += '?' + environ['QUERY_STRING']
        if environ.get('CONTENT_TYPE'):
            headers['Content-Type'] = environ['CONTENT_TYPE']
        if not path.startswith("/"):
            path = "/" + path
        try:
            body = package['body']
            conn.request(environ['REQUEST_METHOD'],
                         path, body, headers)
        except socket.error, exc:
            if exc.args[0] == -2:
                # Name or service not known
                exc = httpexceptions.HTTPBadGateway(
                    "Name or service not known (bad domain name: %s)"
                    % environ['SERVER_NAME'])
                return exc(environ, start_response)
            raise
        res = conn.getresponse()
        headers_out = BackendManager.parse_headers(res.msg)
        status = '%s %s' % (res.status, res.reason)
        length = res.getheader('content-length')
        # TODO: This shouldn't really read in all the content at once
        if length is not None:
            body = res.read(int(length))
        else:
            body = res.read()
        conn.close()
        return (status, headers_out, body)

    @staticmethod
    def parse_headers(message):
        """
        Turn a Message object into a list of WSGI-style headers.
        """
        filtered_headers = (
            'transfer-encoding',
            )
        headers_out = []
        for full_header in message.headers:
            if not full_header:
                # Shouldn't happen, but we'll just ignore
                continue
            if full_header[0].isspace():
                # Continuation line, add to the last header
                if not headers_out:
                    raise ValueError(
                        "First header starts with a space (%r)" % full_header)
                last_header, last_value = headers_out.pop()
                value = last_value + ', ' + full_header.strip()
                headers_out.append((last_header, value))
                continue
            try:
                header, value = full_header.split(':', 1)
            except:
                raise ValueError("Invalid header: %r" % full_header)
            value = value.strip()
            if header.lower() not in filtered_headers:
                headers_out.append((header, value))
        return headers_out


class Router(object):
    """
    A stupidly simple router
    """

    ROUTES = {
        'localhost:8444': ('localhost', 8000)
        }

    @classmethod
    def route(cls, package):
        env = package['env']
        if env['HTTP_HOST'] in Router.ROUTES:
            addr, port = Router.ROUTES[env['HTTP_HOST']]
            return BackendManager.send(addr, port, package)
        return None, None, None


class Cache(object):
    """
    Dummy cache
    """

    @classmethod
    def fetch(cls, env):
        return None

def handle_wsgi(env, start_response):

    r = Cache.fetch(env)
    if r is not None:
        start_response(r.status, r.headers)
        return r.body

    try:
        content_length = int(env.get('CONTENT_LENGTH', '0'))
    except ValueError:
        content_length = 0
    if content_length:
        body = env['wsgi.input'].read(content_length)
    else:
        body = ''
    headers = {'Content-Length': content_length}

    request_package = {
        'env': env,
        'is_file': False,
        'content_length': content_length,
        'body': body,
        }

    status, headers, body = Router.route(request_package)
    start_response(status, headers)
    return [body]

def main():
    # TODO Optionparser
    initial_workers = 6
    cmd_addr = '127.0.0.1'
    cmd_port = 10102
    bind_addr = '0.0.0.0'
    bind_port = 8444

    m = Master(addr=bind_addr, port=bind_port, cmd_addr=cmd_addr, cmd_port=cmd_port)
    m.start()

    s = C.socket(zmq.REQ)
    s.connect('tcp://%s:%s' % (cmd_addr, cmd_port))
    s.send_pyobj(['start_workers', initial_workers])

    m.wait()
    
if __name__ == '__main__':
    sys.exit(main())
