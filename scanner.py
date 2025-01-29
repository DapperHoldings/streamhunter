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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StreamScanner:
    def __init__(self, max_concurrent_hosts: int = 30):  # Increased concurrent hosts
        self.discovered_streams: Set[str] = set()
        self.active_streams: Dict[str, Dict] = {}
        self.scan_count = 0
        self.total_hosts = 0
        self.host_semaphore = Semaphore(max_concurrent_hosts)
        self.session_timeout = aiohttp.ClientTimeout(total=120)  # Reduced timeout
        self.successful_scans = 0
        self.failed_scans = 0
        self.retry_count = 3  # Reduced retries
        print("\033[92m=== Video Stream Scanner Started ===\033[0m")

    async def verify_active_stream(self, url: str, session: aiohttp.ClientSession) -> bool:
        """Verify if a stream is currently active by checking for video content."""
        try:
            timeout = aiohttp.ClientTimeout(total=5)  # Reduced timeout
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    chunk = await response.content.read(4096)  # Reduced chunk size
                    content_type = response.headers.get('content-type', '')

                    if is_video_content_type(content_type) or validate_protocol_response(chunk, 'video'):
                        print("\n" + "🎥 "*20)  # More visible border
                        print("\033[93m🎥 ACTIVE STREAM DETECTED! 🎥\033[0m")
                        print("\033[92m" + "="*50 + "\033[0m")  # Green separator
                        print("Stream Details:")
                        print(f"📌 URL: \033[96m{url}\033[0m")  # Cyan color for URL
                        print(f"📋 Content-Type: {content_type}")
                        print(f"📊 Initial Data Size: {len(chunk)} bytes")
                        print("\033[92m" + "="*50 + "\033[0m")  # Green separator
                        print("🎥 "*20 + "\n")  # More visible border

                        self.active_streams[url] = {
                            'first_seen': time.time(),
                            'last_active': time.time(),
                            'content_type': content_type,
                            'size': len(chunk)
                        }
                        return True
        except Exception as e:
            logger.debug(f"Error verifying stream {url}: {e}")
        return False

    async def scan_mobile_ports(self, ip: str, session: aiohttp.ClientSession) -> List[str]:
        """Scan ports commonly used by mobile streaming apps."""
        mobile_streams = []
        mobile_ports = [8080, 8000, 8888, 9000, 9001, 9002]  # Extended mobile ports
        mobile_paths = [
            # Basic paths
            'stream', 'live', 'video',
            # Mobile app specific paths
            'mobile/stream', 'mobile/live', 'mobile/video',
            'app/stream', 'app/live', 'app/video',
            # Popular streaming app paths
            'tiktok/live', 'tiktok/stream',
            'rewatch/live', 'rewatch/stream',
            'livestream', 'live_stream',
            'mobile_stream', 'app_stream',
            # Common mobile streaming paths
            'streaming', 'streams', 'videos',
            'cast', 'casting', 'screen',
            'mobile/cast', 'app/cast',
            # Additional mobile paths
            'mobile', 'app', 'live',
            'broadcast', 'webcast',
            'mobile/broadcast', 'app/broadcast',
            # Also check root path
            ''
        ]

        for port in mobile_ports:
            if await check_port(ip, port, timeout=2.0):  # Reduced timeout for faster scanning
                for path in mobile_paths:
                    for protocol in ['http', 'https']:
                        url = f"{protocol}://{ip}:{port}/{path}"
                        if await self.verify_active_stream(url, session):
                            mobile_streams.append(url)
                            print("\n" + "📱 "*20)  # More visible border
                            print("\033[96m📱 MOBILE STREAM DISCOVERED! 📱\033[0m")
                            print("\033[92m" + "="*50 + "\033[0m")  # Green separator
                            print("Mobile Stream Details:")
                            print(f"📌 URL: \033[93m{url}\033[0m")  # Yellow color for URL
                            print(f"📱 App Type: {path.split('/')[0] if '/' in path else 'Generic'}")
                            print("\033[92m" + "="*50 + "\033[0m")  # Green separator
                            print("📱 "*20 + "\n")  # More visible border

        return mobile_streams

    async def scan_host(self, ip: str, session: aiohttp.ClientSession) -> None:
        """Scan a single host for active video streaming URLs."""
        try:
            async with self.host_semaphore:
                all_streams = []

                # First check mobile streaming
                print(f"\r\033[K🔍 Checking {ip} for mobile streams...")
                mobile_streams = await self.scan_mobile_ports(ip, session)
                if mobile_streams:
                    all_streams.extend(mobile_streams)
                    self.successful_scans += 1
                    print(f"\033[92m✓ Found {len(mobile_streams)} streams on {ip}\033[0m")

                # Then check standard protocols
                for protocol, ports in COMMON_STREAMING_PORTS.items():
                    for port in ports:
                        try:
                            if await check_port(ip, port, timeout=3.0):  # Reduced timeout
                                print(f"\r\033[K🔍 Checking {protocol.upper()} on {ip}:{port}...")
                                streams = []
                                if protocol == 'rtsp':
                                    streams = await self.check_rtsp(ip, port)
                                elif protocol == 'hls':
                                    streams = await self.check_hls(ip, port, session)
                                elif protocol == 'rtmp':
                                    continue  # Skip RTMP for now
                                elif protocol in ['http', 'https']:
                                    video_paths = ['video', 'stream', 'live', 'content', '']
                                    for path in video_paths:
                                        url = f"{protocol}://{ip}:{port}/{path}"
                                        if await self.verify_active_stream(url, session):
                                            streams.append(url)

                                if streams:
                                    all_streams.extend(streams)
                                    self.successful_scans += 1

                        except Exception as e:
                            logger.debug(f"Error checking {protocol} on {ip}:{port}: {e}")

                if all_streams:
                    self.discovered_streams.update(all_streams)
                    print(f"\n\033[92m=== Found {len(all_streams)} streams on {ip} ===\033[0m")

        except Exception as e:
            logger.error(f"Error scanning host {ip}: {e}")
            self.failed_scans += 1
        finally:
            self.scan_count += 1
            self._print_progress()

    def _print_progress(self) -> None:
        """Print scan progress with success/failure stats."""
        progress = (self.scan_count / self.total_hosts) * 100
        status = f"\r\033[K🔍 Scanning progress: {progress:.1f}% ({self.scan_count}/{self.total_hosts}) "
        stats = f"[\033[92m✓ Found: {self.successful_scans}\033[0m, \033[91m✗ Failed: {self.failed_scans}\033[0m]"
        print(f"{status}{stats}", end="", flush=True)

        # Add additional feedback for long-running scans
        if self.scan_count % 10 == 0:  # Show activity indicator every 10 hosts
            try:
                network_range = get_network_range()
                current_ip = network_range[self.scan_count -1] #Corrected index
                print(f"\n\033[K🔍 Currently scanning: {current_ip} for mobile streams...", end="", flush=True)
            except (IndexError, ValueError) as e:
                logger.debug(f"Error getting current IP: {e}")

    async def scan_network(self) -> Set[str]:
        """Scan the local network for active video streaming URLs."""
        network_range = get_network_range()
        self.total_hosts = len(network_range)

        if not network_range:
            logger.error("No valid network range found")
            return set()

        print("\033[95m=== Starting Network Scan ===\033[0m")  # Purple text
        print(f"Scanning {self.total_hosts} hosts for video streams...")
        print("\033[93mLooking for mobile streaming apps (TikTok, Rewatch Live, etc)...\033[0m")

        async with aiohttp.ClientSession(timeout=self.session_timeout) as session:
            tasks = []
            for ip in network_range:
                task = asyncio.create_task(self.scan_host(ip, session))
                tasks.append(task)
                await asyncio.sleep(0.1)  # Reduced delay for faster scanning

            await asyncio.gather(*tasks)
            print("\n" + "="*80)
            print("\033[92m=== Scan Completed! ===\033[0m")
            if self.discovered_streams:
                print("\n\033[93mAll Discovered Streams:\033[0m")
                print("-"*80)
                print("Copy and paste any URL below to use it:")
                for url in sorted(self.discovered_streams):
                    print(f"\033[96m{url}\033[0m")  # Cyan color for URLs
                print("-"*80)
                print(f"Total streams found: {len(self.discovered_streams)}")
            else:
                print("\n\033[91mNo streams found. Make sure streaming apps are running.\033[0m")

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