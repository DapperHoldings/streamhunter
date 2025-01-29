"""Protocol definitions and detection logic for streaming URLs."""
import re
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COMMON_STREAMING_PORTS = {
    'rtsp': [554, 8554],
    'http': [80, 8080, 8000],
    'https': [443, 8443],
    'hls': [8081, 1935],
    'rtmp': [1935]
}

STREAMING_PATTERNS = {
    'rtsp': re.compile(r'rtsp://[^/]+(:\d+)?(/[^?]*)?(\?.*)?$'),
    'hls': re.compile(r'.*\.(m3u8|m3u)(\?.*)?$'),
    'dash': re.compile(r'.*\.mpd(\?.*)?$'),
    'rtmp': re.compile(r'rtmp://[^/]+(:\d+)?(/[^?]*)?(\?.*)?$'),
    'http_stream': re.compile(r'.*\.(ts|mp4|flv)(\?.*)?$')
}

PROTOCOL_HEADERS = {
    'hls': b'#EXTM3U',
    'dash': b'<?xml',
    'rtsp': b'RTSP/1.0',
    'rtmp': b'<policy-file-request/>'
}

def is_streaming_url(url: str) -> bool:
    """Check if a URL matches known streaming patterns."""
    for pattern in STREAMING_PATTERNS.values():
        if pattern.match(url):
            return True
    return False

def get_protocol_ports() -> List[int]:
    """Get a list of all common streaming ports."""
    return list(set([port for ports in COMMON_STREAMING_PORTS.values() for port in ports]))

def classify_url(url: str) -> str:
    """Classify the streaming URL type with improved accuracy."""
    for protocol, pattern in STREAMING_PATTERNS.items():
        if pattern.match(url):
            logger.debug(f"URL {url} classified as {protocol}")
            return protocol
    return 'unknown'

def validate_protocol_response(data: bytes, protocol: str) -> bool:
    """Validate protocol-specific response data."""
    if not data:
        return False

    expected_header = PROTOCOL_HEADERS.get(protocol)
    if expected_header and expected_header in data[:len(expected_header)]:
        return True

    # Protocol-specific validation
    if protocol == 'rtsp':
        return b'RTSP/1.0' in data or b'RTSP/1.1' in data
    elif protocol == 'hls':
        return b'#EXTM3U' in data or b'#EXT-X-VERSION' in data
    elif protocol == 'dash':
        return b'<?xml' in data and (b'MPD' in data or b'manifest' in data.lower())
    elif protocol == 'rtmp':
        # RTMP validation is connection-based
        return True

    return False

def get_protocol_timeout(protocol: str) -> float:
    """Get recommended timeout value for specific protocol."""
    timeouts = {
        'rtsp': 2.0,
        'hls': 3.0,
        'dash': 3.0,
        'rtmp': 2.0,
        'http': 3.0,
        'https': 3.0
    }
    return timeouts.get(protocol, 2.0)