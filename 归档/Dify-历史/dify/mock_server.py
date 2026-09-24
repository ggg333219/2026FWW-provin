import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time

class DifyMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        """Handle POST requests (chat-messages endpoint)"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            request_data = json.loads(body)
        except:
            self.send_error(400, "Invalid JSON")
            return
        
        # Mock response
        if self.path == "/api/v1/chat-messages":
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Transfer-Encoding', 'chunked')
            self.end_headers()
            
            # Simulate SSE stream
            message = "这是来自Dify模拟服务的回答。"
            for i, char in enumerate(message):
                event = f'data: {{"answer": "{char}"}}\n\n'
                self.wfile.write(event.encode())
                time.sleep(0.05)
            
            # Final response
            final = 'data: {"answer": "", "end": true}\n\n'
            self.wfile.write(final.encode())
        else:
            self.send_error(404, "Not Found")
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        return

def run_mock_server(port=18001):
    server = HTTPServer(('0.0.0.0', port), DifyMockHandler)
    print(f"✅ Dify Mock Server running at http://localhost:{port}")
    server.serve_forever()

if __name__ == "__main__":
    run_mock_server()
