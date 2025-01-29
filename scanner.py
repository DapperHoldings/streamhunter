"""Network scanner for detecting video streaming URLs."""
import asyncio
import aiohttp
from typing import Set, Dict, List
import logging
from protocols import (
    get_protocol_ports, is_streaming_url, COMMON_STREAMING_PORTS,
    validate_protocol_response, get_protocol_timeout, is_video_content_type
)
from utils import check_port, probe_url, get_network_range
from asyncio import Semaphore
import time
import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StreamScanner:
    def __init__(self, max_concurrent_hosts: int = 5):  # Reduced for mobile devices
        self.discovered_streams: Set[str] = set()
        self.active_streams: Dict[str, Dict] = {}  # Track active streams
        self.scan_count = 0
        self.total_hosts = 0
        self.host_semaphore = Semaphore(max_concurrent_hosts)
        self.session_timeout = aiohttp.ClientTimeout(total=300)  # 5 minutes timeout
        self.successful_scans = 0
        self.failed_scans = 0
        self.retry_count = 5  # Increased retries

    async def verify_active_stream(self, url: str, session: aiohttp.ClientSession) -> bool:
        """Verify if a stream is currently active by checking for video content."""
        try:
            # Try multiple times with increased timeout
            for attempt in range(3):
                try:
                    timeout = aiohttp.ClientTimeout(total=20)  # Increased timeout for mobile networks
                    async with session.get(url, timeout=timeout) as response:
                        if response.status == 200:
                            # Read larger initial chunk to verify video content
                            chunk = await response.content.read(16384)  # Increased chunk size
                            content_type = response.headers.get('content-type', '')

                            # Check both content type and data for video signatures
                            if is_video_content_type(content_type) or validate_protocol_response(chunk, 'video'):
                                # Save stream metadata with more details
                                self.active_streams[url] = {
                                    'first_seen': time.time(),
                                    'last_active': time.time(),
                                    'content_type': content_type,
                                    'size': len(chunk),
                                    'headers': dict(response.headers),
                                    'status': 'active'
                                }
                                return True
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.debug(f"Attempt {attempt + 1} failed for {url}: {e}")
                    if attempt < 2:
                        await asyncio.sleep(2)
        except Exception as e:
            logger.debug(f"Error verifying stream {url}: {e}")
        return False

    async def scan_mobile_ports(self, ip: str, session: aiohttp.ClientSession) -> List[str]:
        """Scan ports commonly used by mobile streaming apps."""
        mobile_streams = []
        mobile_ports = [8080, 8000, 8888, 9000, 8081, 8082, 8083, 8084, 8085]  # Extended mobile ports
        mobile_paths = [
            'mobile/stream', 'mobile/live', 'mobile/video',
            'app/stream', 'app/live', 'app/video',
            'stream/mobile', 'live/mobile', 'video/mobile',
            'm/stream', 'm/live', 'm/video',
            'streaming', 'streams', 'videos',
            'cast', 'casting', 'screen'
        ]

        for port in mobile_ports:
            if await check_port(ip, port, timeout=5.0):
                for path in mobile_paths:
                    for protocol in ['http', 'https']:
                        url = f"{protocol}://{ip}:{port}/{path}"
                        if await self.verify_active_stream(url, session):
                            mobile_streams.append(url)
                            logger.info(f"Found mobile stream: {url}")

        return mobile_streams

    async def scan_host(self, ip: str, session: aiohttp.ClientSession) -> None:
        """Scan a single host for active video streaming URLs."""
        try:
            async with self.host_semaphore:
                all_streams = []

                # First check mobile streaming
                mobile_streams = await self.scan_mobile_ports(ip, session)
                if mobile_streams:
                    all_streams.extend(mobile_streams)
                    self.successful_scans += 1

                # Then check standard protocols
                for protocol, ports in COMMON_STREAMING_PORTS.items():
                    for port in ports:
                        await asyncio.sleep(1)  # Rate limiting
                        try:
                            if await check_port(ip, port, timeout=5.0):
                                streams = []
                                if protocol == 'rtsp':
                                    streams = await self.check_rtsp(ip, port)
                                elif protocol == 'hls':
                                    streams = await self.check_hls(ip, port, session)
                                elif protocol == 'rtmp':
                                    continue  # Skip RTMP for now
                                elif protocol in ['http', 'https']:
                                    video_paths = ['video', 'stream', 'live', 'content']
                                    for path in video_paths:
                                        url = f"{protocol}://{ip}:{port}/{path}"
                                        if await self.verify_active_stream(url, session):
                                            streams.append(url)

                                if streams:
                                    all_streams.extend(streams)
                                    self.successful_scans += 1
                        except Exception as e:
                            logger.error(f"Error checking {protocol} on {ip}:{port}: {e}")
                            continue

                if all_streams:
                    self.discovered_streams.update(all_streams)

        except Exception as e:
            logger.error(f"Error scanning host {ip}: {e}")
            self.failed_scans += 1
        finally:
            self.scan_count += 1
            self._print_progress()

    def _print_progress(self) -> None:
        """Print scan progress with success/failure stats."""
        progress = (self.scan_count / self.total_hosts) * 100
        print(f"\rScanning progress: {progress:.1f}% ({self.scan_count}/{self.total_hosts}) "
              f"[Success: {self.successful_scans}, Failed: {self.failed_scans}]", end="")

    async def scan_network(self) -> Set[str]:
        """Scan the local network for active video streaming URLs."""
        network_range = get_network_range()
        self.total_hosts = len(network_range)

        if not network_range:
            logger.error("No valid network range found")
            return set()

        async with aiohttp.ClientSession(timeout=self.session_timeout) as session:
            tasks = []
            for ip in network_range:
                task = asyncio.create_task(self.scan_host(ip, session))
                tasks.append(task)
                await asyncio.sleep(0.5)  # Rate limiting

            await asyncio.gather(*tasks)
            print("\nScan completed!")

        return self.discovered_streams

    async def check_rtsp(self, ip: str, port: int) -> List[str]:
        """Check for RTSP video streams with common paths."""
        streams = []
        video_paths = [
            'video', 'live', 'stream', 'cam',
            'video0', 'video1', 'h264', 'mpeg4',
            'media', 'videoMain', 'channel1',
            'ch01', 'ch1', 'main',
            'mobile/video', 'app/video'
        ]

        for path in video_paths:
            url = f"rtsp://{ip}:{port}/{path}"
            try:
                reader, writer = await asyncio.open_connection(ip, port)
                writer.write(f"OPTIONS {url} RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode())
                await writer.drain()

                try:
                    data = await asyncio.wait_for(reader.read(1024), timeout=15.0)
                    if b"RTSP/1.0 200" in data or b"RTSP/1.1 200" in data:
                        # Track active stream
                        self.active_streams[url] = {
                            'first_seen': time.time(),
                            'last_active': time.time(),
                            'protocol': 'rtsp'
                        }
                        streams.append(url)
                        logger.info(f"Found active RTSP video stream: {url}")
                except asyncio.TimeoutError:
                    logger.debug(f"RTSP timeout for {url}")
                finally:
                    writer.close()
                    await writer.wait_closed()
            except (ConnectionRefusedError, OSError) as e:
                logger.debug(f"RTSP connection failed for {url}: {e}")
                await asyncio.sleep(2)
        return streams

    async def check_hls(self, ip: str, port: int, session: aiohttp.ClientSession) -> List[str]:
        """Check for active HLS video streams."""
        streams = []
        timeout = aiohttp.ClientTimeout(total=20.0)

        video_paths = [
            'video', 'live', 'stream', 'hls',
            'channel1', 'channel2', 'media',
            'mobile/video', 'app/video', 'live/hls'
        ]

        for path in video_paths:
            variants = [f"{path}/index.m3u8", f"{path}/playlist.m3u8", f"{path}/master.m3u8"]
            for variant in variants:
                url = f"http://{ip}:{port}/{variant}"
                try:
                    async with session.get(url, timeout=timeout) as response:
                        if response.status == 200:
                            text = await response.text()
                            # Verify it's an active HLS stream
                            if '#EXTM3U' in text and ('#EXT-X-STREAM-INF' in text or '#EXTINF' in text):
                                # Track active stream
                                self.active_streams[url] = {
                                    'first_seen': time.time(),
                                    'last_active': time.time(),
                                    'protocol': 'hls',
                                    'segments': text.count('#EXTINF')
                                }
                                streams.append(url)
                                logger.info(f"Found active HLS video stream: {url}")
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.debug(f"HLS check failed for {url}: {e}")
                    await asyncio.sleep(2)
        return streams