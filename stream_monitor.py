"""Real-time video stream monitoring and capture."""
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Set, Optional
import aiohttp
from protocols import is_video_content_type, validate_protocol_response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StreamMonitor:
    def __init__(self):
        self.active_streams: Dict[str, Dict] = {}
        self.stream_history: Set[str] = set()
        self.monitor_running = False

    async def monitor_stream(self, url: str, session: aiohttp.ClientSession) -> None:
        """Monitor a single stream for activity and save metadata."""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '')
                    if is_video_content_type(content_type):
                        # Read initial chunk to verify video content
                        chunk = await response.content.read(8192)
                        if validate_protocol_response(chunk, 'video'):
                            stream_info = {
                                'url': url,
                                'content_type': content_type,
                                'first_seen': datetime.now().isoformat(),
                                'last_active': datetime.now().isoformat(),
                                'size': len(chunk),
                                'active': True
                            }
                            self.active_streams[url] = stream_info
                            await self.save_stream_info(stream_info)
                            logger.info(f"New active stream detected: {url}")
        except Exception as e:
            logger.debug(f"Error monitoring stream {url}: {e}")

    async def save_stream_info(self, stream_info: Dict) -> None:
        """Save stream information to both active and history files."""
        try:
            # Save to active streams file
            active_file = "active_streams.json"
            history_file = "stream_history.json"

            # Update active streams
            try:
                with open(active_file, 'r') as f:
                    active_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                active_data = {'streams': []}

            # Update or add new stream
            stream_urls = [s['url'] for s in active_data['streams']]
            if stream_info['url'] not in stream_urls:
                active_data['streams'].append(stream_info)
            
            with open(active_file, 'w') as f:
                json.dump(active_data, f, indent=2)

            # Update history
            try:
                with open(history_file, 'r') as f:
                    history_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                history_data = {'streams': []}

            # Add to history if not already present
            if stream_info['url'] not in {s['url'] for s in history_data['streams']}:
                history_data['streams'].append(stream_info)
                with open(history_file, 'w') as f:
                    json.dump(history_data, f, indent=2)

            logger.info(f"Saved stream info for: {stream_info['url']}")
        except Exception as e:
            logger.error(f"Error saving stream info: {e}")

    async def start_monitoring(self, initial_streams: Optional[Set[str]] = None) -> None:
        """Start monitoring streams for activity."""
        self.monitor_running = True
        async with aiohttp.ClientSession() as session:
            while self.monitor_running:
                try:
                    streams_to_monitor = initial_streams or set()
                    streams_to_monitor.update(self.active_streams.keys())

                    if streams_to_monitor:
                        tasks = [self.monitor_stream(url, session) for url in streams_to_monitor]
                        await asyncio.gather(*tasks)

                    # Clean up inactive streams
                    current_time = datetime.now()
                    for url in list(self.active_streams.keys()):
                        last_active = datetime.fromisoformat(self.active_streams[url]['last_active'])
                        if (current_time - last_active).seconds > 300:  # 5 minutes timeout
                            self.active_streams[url]['active'] = False
                            await self.save_stream_info(self.active_streams[url])
                            del self.active_streams[url]

                    await asyncio.sleep(10)  # Check every 10 seconds
                except Exception as e:
                    logger.error(f"Error in monitor loop: {e}")
                    await asyncio.sleep(5)

    def stop_monitoring(self) -> None:
        """Stop the stream monitoring."""
        self.monitor_running = False
