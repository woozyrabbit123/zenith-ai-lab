"""Finite scripted chat-completions fixture, bound only to loopback."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading


class Model:
    def __init__(self, calls):
        self.calls, self.requests, self.metadata, self.errors = calls, [], [], []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers['Content-Length']))
                body = json.loads(raw)
                if self.path == '/api/show':
                    owner.metadata.append(self.path)
                    self.send_error(404, 'Not Ollama')
                    return
                index = len(owner.requests)
                tools = [m for m in body.get('messages', []) if m.get('role') == 'tool']
                owner.requests.append({'request_bytes': len(raw), 'tool_results_seen': len(tools),
                                       'tool_content_bytes': sum(len(m.get('content', '').encode()) for m in tools),
                                       'model': body.get('model'), 'stream': body.get('stream', False)})
                if self.path != '/v1/chat/completions' or index > len(owner.calls):
                    owner.errors.append('unexpected request')
                    self.send_error(400)
                    return
                message, finish = {'role': 'assistant', 'content': 'Scripted end; filesystem evidence decides success.'}, 'stop'
                if index < len(owner.calls):
                    name, args = owner.calls[index]
                    message = {'role': 'assistant', 'content': None, 'tool_calls': [{
                        'id': 'call_' + str(index), 'type': 'function',
                        'function': {'name': name, 'arguments': json.dumps(args)}}]}
                    finish = 'tool_calls'
                result = {'id': 'synthetic-completion', 'created': 1, 'object': 'chat.completion',
                          'model': 'fastpath-scripted', 'choices': [{'index': 0, 'message': message, 'finish_reason': finish}],
                          'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}
                kind = 'application/json'
                if body.get('stream'):
                    if 'tool_calls' in message:
                        message['tool_calls'][0]['index'] = 0
                    first = {**result, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': message, 'finish_reason': None}]}
                    last = {**first, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]}
                    output = ('data: ' + json.dumps(first) + '\n\ndata: ' + json.dumps(last) + '\n\ndata: [DONE]\n\n').encode()
                    kind = 'text/event-stream'
                else:
                    output = json.dumps(result).encode()
                self.send_response(200)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(output)))
                self.end_headers()
                self.wfile.write(output)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server.server_port}/v1'

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
