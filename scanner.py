"""Network scanner for detecting streaming URLs."""
import asyncio
import aiohttp
import websockets
from typing import Set, Dict, List
import logging
from protocols import (
    get_protocol_ports, is_streaming_url, COMMON_STREAMING_PORTS,
    validate_protocol_response, get_protocol_timeout
)
from utils import check_port, probe_url, get_network_range
from asyncio import Semaphore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StreamScanner:
    def __init__(self, max_concurrent_hosts: int = 10):  # Reduced concurrent hosts for mobile
        self.discovered_streams: Set[str] = set()
        self.scan_count = 0
        self.total_hosts = 0
        self.host_semaphore = Semaphore(max_concurrent_hosts)
        self.session_timeout = aiohttp.ClientTimeout(total=120)  # Increased total timeout
        self.successful_scans = 0
        self.failed_scans = 0
        self.retry_count = 3
        self.protocol_timeouts = {
            'rtsp': 8.0,
            'hls': 10.0,
            'dash': 10.0,
            'rtmp': 8.0,
            'http': 10.0,
            'https': 10.0,
            'ws': 8.0,
            'wss': 8.0
        }

    async def check_ws_stream(self, ip: str, port: int) -> List[str]:
        """Check for WebSocket streaming endpoints."""
        streams = []
        paths = [
            'ws', 'stream', 'live', 'video', 'media',
            'mobile/stream', 'mobile/live', 'app/stream'
        ]

        for path in paths:
            for protocol in ['ws', 'wss']:
                url = f"{protocol}://{ip}:{port}/{path}"
                try:
                    async with websockets.connect(url, timeout=8) as ws:
                        try:
                            await ws.send('{"type":"subscribe"}')
                            data = await asyncio.wait_for(ws.recv(), timeout=2)
                            if data:  # Any response might indicate a stream
                                streams.append(url)
                                logger.info(f"Found WebSocket stream: {url}")
                        except asyncio.TimeoutError:
                            continue
                except Exception as e:
                    logger.debug(f"WebSocket connection failed for {url}: {e}")
                    await asyncio.sleep(0.5)
        return streams

    async def check_mobile_stream(self, ip: str, port: int, session: aiohttp.ClientSession) -> List[str]:
        """Check for mobile-specific streaming endpoints."""
        streams = []
        paths = [
            'mobile/stream', 'mobile/live', 'mobile/hls',
            'mobile/dash', 'app/stream', 'app/live',
            'm/stream', 'm/live', 'api/stream', 'api/live'
        ]

        for path in paths:
            url = f"http://{ip}:{port}/{path}"
            if await probe_url(url, session):
                streams.append(url)
                logger.info(f"Found mobile stream: {url}")
        return streams

    async def check_rtsp(self, ip: str, port: int) -> List[str]:
        """Check for RTSP streams with mobile paths."""
        streams = []
        common_paths = [
            'live', 'stream', 'cam', 'video0', 'video1',
            'h264', 'mpeg4', 'media', 'videoMain',
            'video1+audio1', 'primary', 'track1',
            'ch01', 'ch1', 'sub', 'main', 'av0_0',
            'mobile/stream', 'mobile/live', 'app/stream'
        ]
        timeout = self.protocol_timeouts['rtsp']

        for path in common_paths:
            url = f"rtsp://{ip}:{port}/{path}"
            for attempt in range(self.retry_count):
                try:
                    reader, writer = await asyncio.open_connection(ip, port)
                    writer.write(f"OPTIONS {url} RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode())
                    await writer.drain()

                    try:
                        data = await asyncio.wait_for(reader.read(1024), timeout=timeout)
                        if b"RTSP/1.0 200" in data or b"RTSP/1.1 200" in data:
                            streams.append(url)
                            logger.info(f"Found RTSP stream: {url}")
                            break
                    except asyncio.TimeoutError:
                        logger.debug(f"RTSP timeout for {url}")
                    finally:
                        writer.close()
                        await writer.wait_closed()
                        await asyncio.sleep(1)
                except (ConnectionRefusedError, OSError) as e:
                    logger.debug(f"RTSP connection failed for {url}: {e}")
                    await asyncio.sleep(1)
        return streams

    async def check_hls(self, ip: str, port: int, session: aiohttp.ClientSession) -> List[str]:
        """Check for HLS streams on the given IP and port with retries."""
        streams = []
        paths = [
            'hls', 'live', 'stream', 'streaming', 'playlist', 'channel',
            'live/stream', 'live/channel1', 'video', 'media', 'content',
            'stream1', 'stream2', 'ch1', 'ch2', 'feed1', 'feed2'
        ]
        timeout = aiohttp.ClientTimeout(total=self.protocol_timeouts['hls'])

        for path in paths:
            variants = [f"{path}/index.m3u8", f"{path}/playlist.m3u8", f"{path}/master.m3u8"]
            for variant in variants:
                url = f"http://{ip}:{port}/{variant}"
                for attempt in range(self.retry_count):
                    try:
                        async with session.get(url, timeout=timeout) as response:
                            if response.status == 200:
                                text = await response.text()
                                if '#EXTM3U' in text:
                                    streams.append(url)
                                    logger.info(f"Found HLS stream: {url}")
                                    break
                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        logger.debug(f"HLS check failed for {url}: {e}")
                        await asyncio.sleep(1)
        return streams

    async def check_dash(self, ip: str, port: int, session: aiohttp.ClientSession) -> List[str]:
        """Check for DASH streams on the given IP and port with retries."""
        streams = []
        paths = [
            'dash', 'stream', 'live', 'content', 'media', 'channel',
            'video', 'streaming', 'manifest', 'mpd', 'output'
        ]
        timeout = aiohttp.ClientTimeout(total=self.protocol_timeouts['dash'])

        for path in paths:
            variants = [f"{path}/manifest.mpd", f"{path}/stream.mpd", f"{path}/index.mpd"]
            for variant in variants:
                url = f"http://{ip}:{port}/{variant}"
                for attempt in range(self.retry_count):
                    try:
                        async with session.get(url, timeout=timeout) as response:
                            if response.status == 200:
                                text = await response.text()
                                if '<MPD' in text:
                                    streams.append(url)
                                    logger.info(f"Found DASH stream: {url}")
                                    break
                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        logger.debug(f"DASH check failed for {url}: {e}")
                        await asyncio.sleep(1)
        return streams

    async def check_http_stream(self, ip: str, port: int, protocol: str, session: aiohttp.ClientSession) -> List[str]:
        """Check for HTTP/HTTPS video streams."""
        paths = ['stream', 'live', 'hls', 'dash', 'channel', 'video']
        streams = []

        for path in paths:
            url = f"{protocol}://{ip}:{port}/{path}"
            if await probe_url(url, session):
                streams.append(url)
                logger.info(f"Found {protocol.upper()} stream: {url}")

        return streams

    async def check_rtmp(self, ip: str, port: int) -> List[str]:
        """Check for RTMP streams on the given IP and port with retries."""
        streams = []
        if await check_port(ip, port, timeout=self.protocol_timeouts['rtmp']):
            paths = [
                'live', 'stream', 'app', 'broadcast', 'channel',
                'streaming', 'live/stream', 'media', 'content'
            ]
            for path in paths:
                url = f"rtmp://{ip}:{port}/{path}"
                streams.append(url)
                logger.info(f"Found potential RTMP endpoint: {url}")
                await asyncio.sleep(0.5)
        return streams

    async def scan_host(self, ip: str, session: aiohttp.ClientSession) -> None:
        """Scan a single host for streaming URLs with improved mobile support."""
        try:
            async with self.host_semaphore:
                all_streams = []

                # Check all protocols including WebSocket and mobile-specific endpoints
                for protocol, ports in COMMON_STREAMING_PORTS.items():
                    for port in ports:
                        await asyncio.sleep(0.5)  # Increased delay for mobile networks
                        if await check_port(ip, port, timeout=5.0):  # Increased timeout
                            try:
                                streams = []
                                if protocol == 'rtsp':
                                    streams = await self.check_rtsp(ip, port)
                                elif protocol == 'ws' or protocol == 'wss':
                                    streams = await self.check_ws_stream(ip, port)
                                elif protocol in ['http', 'https']:
                                    # Check both regular and mobile streams
                                    http_streams = await self.check_http_stream(ip, port, protocol, session)
                                    mobile_streams = await self.check_mobile_stream(ip, port, session)
                                    streams = http_streams + mobile_streams
                                elif protocol == 'hls':
                                    streams = await self.check_hls(ip, port, session)
                                elif protocol == 'dash':
                                    streams = await self.check_dash(ip, port, session)
                                elif protocol == 'rtmp':
                                    streams = await self.check_rtmp(ip, port)
                                else:
                                    continue

                                if streams:
                                    all_streams.extend(streams)
                                    self.successful_scans += 1

                            except Exception as e:
                                logger.error(f"Error checking {protocol} on {ip}:{port}: {e}")
                                self.failed_scans += 1
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
        """Scan the local network for streaming URLs with extended timeouts."""
        network_range = get_network_range()
        self.total_hosts = len(network_range)

        if not network_range:
            logger.error("No valid network range found")
            return set()

        async with aiohttp.ClientSession(timeout=self.session_timeout) as session:
            tasks = []
            for ip in network_range:
                tasks.append(self.scan_host(ip, session))
                await asyncio.sleep(0.2)  # Add delay between creating tasks

            await asyncio.gather(*tasks)
            print("\nScan completed!")

        return self.discovered_streams