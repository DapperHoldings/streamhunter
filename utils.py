"""Utility functions for network scanning and file operations."""
import asyncio
import socket
import ipaddress
from typing import List, Set
import aiohttp
import logging
from asyncio import Semaphore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Limit concurrent connections
MAX_CONCURRENT_SCANS = 50
connection_semaphore = Semaphore(MAX_CONCURRENT_SCANS)

async def check_port(ip: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a port is open on the given IP with connection limiting."""
    async with connection_semaphore:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=timeout
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError) as e:
            logger.debug(f"Port {port} on {ip} is closed or unreachable: {str(e)}")
            return False

async def probe_url(url: str, session: aiohttp.ClientSession) -> bool:
    """Probe a URL to check if it's a valid streaming endpoint with connection limiting."""
    async with connection_semaphore:
        try:
            timeout = aiohttp.ClientTimeout(total=2)
            async with session.head(url, timeout=timeout, allow_redirects=True) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '')
                    return any(media_type in content_type.lower() 
                             for media_type in ['video', 'stream', 'mpegurl', 'application'])
                return False
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.debug(f"Failed to probe URL {url}: {str(e)}")
            return False

def get_local_ip() -> str:
    """Get the local IP address with improved error handling."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)
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