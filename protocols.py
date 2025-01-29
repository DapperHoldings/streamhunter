"""Protocol definitions and detection logic for video streaming URLs."""
import re
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COMMON_STREAMING_PORTS = {
    'rtsp': [554, 8554],
    'http': [80, 8080, 8000, 8800, 8888],  # Common video streaming ports
    'https': [443, 8443],
    'hls': [8081, 1935],  # HLS specific ports
    'rtmp': [1935, 1936]  # RTMP specific ports
}

# Video-focused streaming patterns
STREAMING_PATTERNS = {
    'rtsp': re.compile(r'rtsp://[^/]+(:\d+)?(/[^?]*)?(\?.*)?$'),
    'hls': re.compile(r'.*\.(m3u8|m3u)(\?.*)?$'),
    'dash': re.compile(r'.*\.mpd(\?.*)?$'),
    'rtmp': re.compile(r'rtmp://[^/]+(:\d+)?(/[^?]*)?(\?.*)?$'),
    'direct_video': re.compile(r'.*\.(mp4|ts|mkv|avi|mov)(\?.*)?$'),
    'adaptive_video': re.compile(r'.*/manifest(\?.*)?$|.*/playlist(\?.*)?$|.*/stream(\?.*)?$|.*/live(\?.*)?$')
}

# Video-specific content types
VIDEO_CONTENT_TYPES = [
    'video/',  # Any video type
    'application/x-mpegurl',  # HLS
    'application/vnd.apple.mpegurl',  # HLS (Apple)
    'application/dash+xml',  # DASH
    'application/x-rtsp',  # RTSP
    'application/x-rtmp',  # RTMP
    'video/mp4',
    'video/webm',
    'video/x-matroska',  # MKV
    'video/quicktime',  # MOV
    'video/x-flv',  # FLV
    'application/x-mpegURL'  # HLS variant
]

# Video streaming protocol headers
PROTOCOL_HEADERS = {
    'hls': b'#EXTM3U',
    'dash': b'<?xml',
    'rtsp': b'RTSP/1.0',
    'rtmp': b'<policy-file-request/>',
    'video': b'mdat'  # Common MP4 box marker
}

def is_streaming_url(url: str) -> bool:
    """Check if a URL matches known video streaming patterns."""
    for pattern in STREAMING_PATTERNS.values():
        if pattern.match(url):
            return True
    return False

def get_protocol_ports() -> List[int]:
    """Get a list of all common video streaming ports."""
    return list(set([port for ports in COMMON_STREAMING_PORTS.values() for port in ports]))

def classify_url(url: str) -> str:
    """Classify the video streaming URL type."""
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
    """Validate video protocol-specific response data."""
    if not data:
        return False

    # Check for protocol-specific headers
    expected_header = PROTOCOL_HEADERS.get(protocol)
    if expected_header and expected_header in data[:len(expected_header)]:
        return True

    # Protocol-specific validation
    if protocol == 'rtsp':
        return b'RTSP/1.0' in data or b'RTSP/1.1' in data
    elif protocol == 'hls':
        return b'#EXTM3U' in data and (b'#EXT-X-STREAM-INF' in data or b'#EXTINF' in data)
    elif protocol == 'dash':
        return b'<?xml' in data and (b'MPD' in data or b'manifest' in data.lower())
    elif protocol == 'rtmp':
        return True  # RTMP validation is connection-based

    # Check for binary video content
    video_signatures = [
        b'ftyp',  # MP4 signature
        b'moov',  # MP4 movie header
        b'mdat',  # MP4 media data
        b'webm',  # WebM signature
        b'matroska',  # MKV signature
        b'FLV'   # Flash Video signature
    ]
    return any(sig in data[:1024] for sig in video_signatures)

def get_protocol_timeout(protocol: str) -> float:
    """Get recommended timeout value for specific video protocol."""
    timeouts = {
        'rtsp': 15.0,    # Increased for mobile networks
        'hls': 20.0,     # Increased for mobile networks
        'dash': 20.0,    # Increased for mobile networks
        'rtmp': 15.0,    # Increased for mobile networks
        'http': 20.0,    # Increased for mobile networks
        'https': 20.0    # Increased for mobile networks
    }
    return timeouts.get(protocol, 10.0)  # Default timeout