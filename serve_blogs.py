# serve_blogs.py
"""
Lightweight local HTTP server for the InvoHydra SEO Blog Viewer Dashboard.
Serves a JSON API of generated blogs and renders the frontend app.
"""

import os
import json
import urllib.parse
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = 8000
BLOGS_DIR = os.path.join("data", "blogs")

class BlogViewerHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Quiet default requests logging to prevent console spam
        pass

    def do_GET(self):
        # API: List all blogs
        if self.path == "/api/blogs":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            blogs = []
            if os.path.exists(BLOGS_DIR):
                for filename in os.listdir(BLOGS_DIR):
                    filepath = os.path.join(BLOGS_DIR, filename)
                    if filename.endswith(".json"):
                        title = filename.replace(".json", "").replace("_", " ").title()
                        try:
                            with open(filepath, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                title = data.get("meta_title", title)
                        except Exception:
                            pass
                        blogs.append({
                            "filename": filename,
                            "title": title
                        })
                    elif filename.endswith(".md"):
                        title = filename.replace(".md", "").replace("_", " ").title()
                        try:
                            with open(filepath, "r", encoding="utf-8") as f:
                                first_line = f.readline().strip()
                                if first_line.startswith("# "):
                                    title = first_line.replace("# ", "")
                        except Exception:
                            pass
                        blogs.append({
                            "filename": filename,
                            "title": title
                        })
            self.wfile.write(json.dumps(blogs).encode("utf-8"))
            return
 
        # API: Get individual blog content
        elif self.path.startswith("/api/blog/"):
            filename = urllib.parse.unquote(self.path[10:])
            filepath = os.path.join(BLOGS_DIR, filename)
            
            if os.path.exists(filepath) and (filename.endswith(".json") or filename.endswith(".md")):
                self.send_response(200)
                content_type = "application/json; charset=utf-8" if filename.endswith(".json") else "text/markdown; charset=utf-8"
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        self.wfile.write(f.read().encode("utf-8"))
                except Exception as e:
                    self.send_error(500, f"Error reading file: {e}")
            else:
                self.send_error(404, "Blog post not found")
            return

        # Default handler to serve static dashboard files (like index.html)
        else:
            super().do_GET()

def run():
    print(f"Starting Blog Viewer Server on http://localhost:{PORT}...")
    server = HTTPServer(("localhost", PORT), BlogViewerHandler)
    
    # Auto-open browser
    webbrowser.open(f"http://localhost:{PORT}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.server_close()

if __name__ == "__main__":
    run()
