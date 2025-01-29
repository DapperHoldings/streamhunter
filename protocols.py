"""Protocol definitions and detection logic for streaming URLs."""
import re
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COMMON_STREAMING_PORTS = {
    'rtsp': [554, 8554],
    'http': [80, 8080, 8000, 8800, 8888],  # Added more common HTTP ports
    'https': [443, 8443],
    'hls': [8081, 1935, 8082],
    'rtmp': [1935, 1936]  # Added backup RTMP port
}

STREAMING_PATTERNS = {
    'rtsp': re.compile(r'rtsp://[^/]+(:\d+)?(/[^?]*)?(\?.*)?$'),
    'hls': re.compile(r'.*\.(m3u8|m3u)(\?.*)?$'),
    'dash': re.compile(r'.*\.mpd(\?.*)?$'),
    'rtmp': re.compile(r'rtmp://[^/]+(:\d+)?(/[^?]*)?(\?.*)?$'),
    'http_stream': re.compile(r'.*\.(ts|mp4|flv|m4s|webm|mkv|avi|mov)(\?.*)?$'),
    'adaptive_stream': re.compile(r'.*/manifest(\?.*)?$|.*/playlist(\?.*)?$|.*/stream(\?.*)?$'),
    'ws_stream': re.compile(r'ws://[^/]+(:\d+)?(/[^?]*)?(\?.*)?$|wss://[^/]+(:\d+)?(/[^?]*)?(\?.*)?$')
}

# Extended content types for video streams
VIDEO_CONTENT_TYPES = [
    'video/',
    'application/x-mpegurl',
    'application/vnd.apple.mpegurl',
    'application/dash+xml',
    'application/x-rtsp',
    'application/x-rtmp',
    'application/octet-stream',  # Some streams use this
    'binary/octet-stream',
    'application/x-flv',
    'video/mp4',
    'video/webm',
    'video/x-matroska',
    'video/quicktime'
]

PROTOCOL_HEADERS = {
    'hls': b'#EXTM3U',
    'dash': b'<?xml',
    'rtsp': b'RTSP/1.0',
    'rtmp': b'<policy-file-request/>',
    'adaptive': b'#EXT'  # For adaptive streaming formats
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

def is_video_content_type(content_type: str) -> bool:
    """Check if the content type is related to video streaming."""
    content_type = content_type.lower()
    return any(vct in content_type for vct in VIDEO_CONTENT_TYPES)

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
        return (b'#EXTM3U' in data or b'#EXT-X-VERSION' in data or 
                b'#EXT-X-STREAM-INF' in data)
    elif protocol == 'dash':
        return b'<?xml' in data and (b'MPD' in data or b'manifest' in data.lower())
    elif protocol == 'rtmp':
        return True  # RTMP validation is connection-based
    elif protocol == 'adaptive':
        return (b'#EXT' in data or b'BANDWIDTH' in data or 
                b'RESOLUTION' in data or b'CODECS' in data)

    # Check for binary video content
    return any(header in data[:1024] for header in [b'ftyp', b'moov', b'mdat'])

def get_protocol_timeout(protocol: str) -> float:
    """Get recommended timeout value for specific protocol."""
    timeouts = {
        'rtsp': 5.0,
        'hls': 8.0,
        'dash': 8.0,
        'rtmp': 5.0,
        'http': 8.0,
        'https': 8.0,
        'ws': 5.0
    }
    return timeouts.get(protocol, 2.0)