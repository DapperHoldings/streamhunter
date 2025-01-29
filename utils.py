"""Utility functions for network scanning and file operations."""
import asyncio
import socket
import ipaddress
from typing import List, Set
import aiohttp
import logging
from asyncio import Semaphore
from protocols import is_video_content_type

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Increased concurrent connections for faster scanning
MAX_CONCURRENT_SCANS = 20  # Increased from 5
connection_semaphore = Semaphore(MAX_CONCURRENT_SCANS)

async def check_port(ip: str, port: int, timeout: float = 2.0) -> bool:  # Reduced timeout
    """Check if a port is open on the given IP with connection limiting and retries."""
    async with connection_semaphore:
        for attempt in range(2):  # Reduced retries for faster scanning
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port),
                    timeout=timeout
                )
                writer.close()
                await writer.wait_closed()
                return True
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError) as e:
                logger.debug(f"Port {port} on {ip} check failed (attempt {attempt + 1}/2): {str(e)}")
                if attempt < 1:  # Don't sleep after the last attempt
                    await asyncio.sleep(0.5)  # Reduced delay between retries
        return False

async def probe_url(url: str, session: aiohttp.ClientSession) -> bool:
    """Probe a URL to check if it's a valid streaming endpoint with retries."""
    async with connection_semaphore:
        for attempt in range(3):  # Reduced retries for faster scanning
            try:
                timeout = aiohttp.ClientTimeout(total=5)  # Reduced timeout
                async with session.head(url, timeout=timeout, allow_redirects=True) as response:
                    if response.status == 200:
                        content_type = response.headers.get('content-type', '')
                        if is_video_content_type(content_type):
                            return True

                # If HEAD doesn't work, try GET for the first few bytes
                if response.status != 404:  # Skip if definitely not found
                    async with session.get(url, timeout=timeout) as response:
                        if response.status == 200:
                            data = await response.content.read(1024)
                            content_type = response.headers.get('content-type', '')

                            if (is_video_content_type(content_type) or
                                any(sig in data for sig in [b'ftyp', b'moov', b'#EXT', b'<?xml'])):
                                return True
                return False
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.debug(f"Failed to probe URL {url} (attempt {attempt + 1}/3): {str(e)}")
                if attempt < 2:  # Don't sleep after the last attempt
                    await asyncio.sleep(0.5)  # Reduced delay between retries
        return False

def get_local_ip() -> str:
    """Get the local IP address with improved error handling."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5.0)  # Increased timeout
        sock.connect(("8.8.8.8", 80))
        local_ip = sock.getsockname()[0]
        sock.close()
        return local_ip
    except Exception as e:
        logger.error(f"Failed to get local IP: {e}")
        return "127.0.0.1"

def get_network_range() -> List[str]:
    """Get the list of IPs in the local network range with validation."""
    try:
        local_ip = get_local_ip()
        network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
        return [str(ip) for ip in network.hosts()]
    except ValueError as e:
        logger.error(f"Invalid network address: {e}")
        return []

async def save_streams(streams: Set[str], filename: str = "streams.txt"):
    """Save discovered streaming URLs to a file with error handling."""
    try:
        with open(filename, 'w') as f:
            for stream in sorted(streams):
                f.write(f"{stream}\n")
        logger.info(f"Saved {len(streams)} streams to {filename}")
    except IOError as e:
        logger.error(f"Failed to save streams to {filename}: {e}")
        raise