import requests
import logging
from urllib.parse import urlparse
import socket

class URLValidator:
    def __init__(self):
        self.streaming_paths = [
            '/stream',
            '/live',
            '/hls',
            '/dash',
            '/rtsp',
            '/streaming',
            '/video',
            '/media'
        ]
        
    def validate_url(self, ip, port):
        valid_urls = []
        protocols = ['http', 'https', 'rtsp'] if port not in [443] else ['https']
        
        for protocol in protocols:
            for path in self.streaming_paths:
                url = f"{protocol}://{ip}:{port}{path}"
                try:
                    if protocol in ['http', 'https']:
                        response = requests.head(url, timeout=2, allow_redirects=True)
                        if response.status_code == 200:
                            valid_urls.append(url)
                    elif protocol == 'rtsp':
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(2)
                        result = sock.connect_ex((ip, port))
                        if result == 0:
                            valid_urls.append(url)
                        sock.close()
                except Exception as e:
                    logging.debug(f"Failed to validate {url}: {e}")
                    continue
                    
        return valid_urls

    def check_content_type(self, url):
        try:
            response = requests.head(url, timeout=2, allow_redirects=True)
            content_type = response.headers.get('content-type', '')
            return any(media_type in content_type.lower() for media_type in 
                      ['video', 'application/vnd.apple.mpegurl', 'application/dash+xml'])
        except:
            return False
