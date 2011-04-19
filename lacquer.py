from gevent import fork, monkey, pywsgi, spawn
monkey.patch_all()
from gevent_zeromq import zmq
import imp
import os
import sys

C = zmq.Context()


class Script(object):
    """ load a python file or module """

    def __init__(self, script_uri):
        self.script_uri = script_uri

    def load(self):
        if os.path.exists(self.script_uri):
            script = imp.load_source('_route', self.script_uri)
        else:
            script = __import__(self.script_uri)
        return script


class Master(object):

    def __init__(self, addr, port, cmd_addr, cmd_port, script):
        self.addr = addr
        self.port = port
        self.cmd_addr = cmd_addr
        self.cmd_port = cmd_port
        self.worker_pids = []
        self.script = script

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
        for i in range(num_workers):
            self.start_worker()

    def start_worker(self):
        w = Worker(self.addr, self.port)
        pid = fork()
        if pid:
            self.worker_pids.append(pid)
            return
        w.start()
        print 'Serving on https://%s:%s' % (self.addr, self.port)

    def cmd_restart_workers(self):
        pass


class Worker(object):

    def __init__(self, addr, port):
        self.server = pywsgi.WSGIServer((addr, port), self.handle_wsgi)
        self.server.pre_start()

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
    
        request = {
            'env': env,
            'is_file': False,
            'content_length': content_length,
            'body': body,
            }
    
        status, headers, body = Router.route(request)
        start_response(status, headers)
        return [body]

def main():
    # TODO Optionparser
    initial_workers = 6
    cmd_addr = '127.0.0.1'
    cmd_port = 10102
    bind_addr = '0.0.0.0'
    bind_port = 8444
    conf = 'simple.py'

    script = Script(conf)
    m = Master(addr=bind_addr, port=bind_port, cmd_addr=cmd_addr, cmd_port=cmd_port, script=script)
    m.start()

    s = C.socket(zmq.REQ)
    s.connect('tcp://%s:%s' % (cmd_addr, cmd_port))
    s.send_pyobj(['start_workers', initial_workers])

    m.wait()
    
if __name__ == '__main__':
    sys.exit(main())
