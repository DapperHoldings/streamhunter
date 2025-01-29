"""Network scanner for detecting streaming URLs."""
import asyncio
import aiohttp
from typing import Set, Dict, List
import logging
from protocols import get_protocol_ports, is_streaming_url, COMMON_STREAMING_PORTS
from utils import check_port, probe_url, get_network_range
from asyncio import Semaphore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StreamScanner:
    def __init__(self, max_concurrent_hosts: int = 20):
        self.discovered_streams: Set[str] = set()
        self.scan_count = 0
        self.total_hosts = 0
        self.host_semaphore = Semaphore(max_concurrent_hosts)
        self.session_timeout = aiohttp.ClientTimeout(total=60)
        self.successful_scans = 0
        self.failed_scans = 0
        self.retry_count = 3
        self.protocol_timeouts = {
            'rtsp': 5.0,
            'hls': 8.0,
            'dash': 8.0,
            'rtmp': 5.0,
            'http': 8.0,
            'https': 8.0
        }

    async def check_rtsp(self, ip: str, port: int) -> List[str]:
        """Check for RTSP streams on the given IP and port with retries."""
        streams = []
        common_paths = [
            'live', 'stream', 'cam', 'video0', 'video1', 'h264', 'mpeg4',
            'media', 'videoMain', 'video1+audio1', 'primary', 'track1',
            'ch01', 'ch1', 'sub', 'main', 'av0_0', 'av0_1', 'streaming'
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
                        logger.debug(f"RTSP timeout for {url} (attempt {attempt + 1}/{self.retry_count})")
                    finally:
                        writer.close()
                        await writer.wait_closed()
                        await asyncio.sleep(1)  # Add delay between retries
                except (ConnectionRefusedError, OSError) as e:
                    logger.debug(f"RTSP connection failed for {url}: {e}")
                    await asyncio.sleep(1)  # Add delay between retries
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
                        await asyncio.sleep(1)  # Add delay between retries
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
                        await asyncio.sleep(1)  # Add delay between retries
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
                await asyncio.sleep(0.5)  # Add small delay between checks
        return streams

    async def scan_host(self, ip: str, session: aiohttp.ClientSession) -> None:
        """Scan a single host for streaming URLs using protocol-specific methods."""
        try:
            async with self.host_semaphore:
                protocol_tasks = []

                for protocol, ports in COMMON_STREAMING_PORTS.items():
                    for port in ports:
                        # Add delay between port checks
                        await asyncio.sleep(0.2)
                        if await check_port(ip, port, timeout=2.0):
                            if protocol == 'rtsp':
                                task = self.check_rtsp(ip, port)
                            elif protocol == 'hls':
                                task = self.check_hls(ip, port, session)
                            elif protocol == 'rtmp':
                                task = self.check_rtmp(ip, port)
                            else:  # HTTP/HTTPS
                                paths = ['stream', 'live', 'hls', 'dash', 'channel', 'video']
                                task = asyncio.gather(*[
                                    probe_url(f"{protocol}://{ip}:{port}/{path}", session)
                                    for path in paths
                                ])
                            protocol_tasks.append(asyncio.create_task(task))

                if protocol_tasks:
                    results = await asyncio.gather(*protocol_tasks, return_exceptions=True)
                    streams = []
                    for result in results:
                        if isinstance(result, list):
                            streams.extend(result)
                        elif isinstance(result, Exception):
                            logger.error(f"Error during protocol scan: {result}")
                            self.failed_scans += 1
                        elif result:  # Boolean result from probe_url
                            self.successful_scans += 1

                    self.discovered_streams.update(streams)

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
        """Scan the local network for streaming URLs."""
        network_range = get_network_range()
        self.total_hosts = len(network_range)

        if not network_range:
            logger.error("No valid network range found")
            return set()

        async with aiohttp.ClientSession(timeout=self.session_timeout) as session:
            tasks = [self.scan_host(ip, session) for ip in network_range]
            await asyncio.gather(*tasks)
            print("\nScan completed!")

        return self.discovered_streams