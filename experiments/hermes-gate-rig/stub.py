"""Scripted loopback-only chat-completions server. No LLM and no API account."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading


class ScriptedModel:
    def __init__(self, calls):
        self.calls, self.requests, self.errors = calls, [], []
        self.metadata_requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path == '/api/show':
                    # Hermes probes loopback providers for Ollama context metadata at startup.
                    # This is not an agent conversation and must not consume a scripted turn.
                    owner.metadata_requests.append(self.path)
                    self.send_error(404, 'Not an Ollama endpoint')
                    return
                index = len(owner.requests)
                # Record only transcript progress, never request headers or prompts.
                results = [m for m in body.get('messages', []) if m.get('role') == 'tool']
                owner.requests.append({'tool_results': results, 'stream': body.get('stream', False),
                                       'model': body.get('model'),
                                       'tool_names': [t.get('function', {}).get('name') for t in body.get('tools', [])],
                                       'roles': [m.get('role') for m in body.get('messages', [])],
                                       'path': self.path})
                if self.path != '/v1/chat/completions' or index > len(owner.calls):
                    owner.errors.append('unexpected path or excess model request')
                    self.send_error(400)
                    return
                message = {'role': 'assistant', 'content': 'done'}
                finish = 'stop'
                if index < len(owner.calls):
                    name, args = owner.calls[index]
                    message = {'role': 'assistant', 'content': None, 'tool_calls': [{
                        'id': 'call_' + str(index), 'type': 'function',
                        'function': {'name': name, 'arguments': json.dumps(args)}}]}
                    finish = 'tool_calls'
                response = {'id': 'synthetic-completion', 'object': 'chat.completion', 'created': 1,
                            'model': 'rig-scripted', 'choices': [{'index': 0, 'message': message,
                                                                 'finish_reason': finish}],
                            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}
                if body.get('stream'):
                    # The public API path may request streaming: implement that protocol too.
                    delta = dict(message)
                    if 'tool_calls' in delta:
                        delta['tool_calls'][0]['index'] = 0
                    chunk = {**response, 'object': 'chat.completion.chunk',
                             'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]}
                    end = {**chunk, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]}
                    raw = ('data: ' + json.dumps(chunk) + '\n\ndata: ' + json.dumps(end) +
                           '\n\ndata: [DONE]\n\n').encode()
                    content_type = 'text/event-stream'
                else:
                    raw, content_type = json.dumps(response).encode(), 'application/json'
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server.server_port}/v1'

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
