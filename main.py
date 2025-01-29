"""Main entry point for the streaming URL scanner."""
import asyncio
import logging
from scanner import StreamScanner
from stream_monitor import StreamMonitor
from utils import save_streams

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    try:
        print("\n" + "🔍 "*20)
        print("\033[95m=== Mobile Stream Scanner Started ===\033[0m")
        print("\033[93mScanning for streaming apps like TikTok, Rewatch Live, etc...\033[0m")
        print("🔍 "*20 + "\n")

        scanner = StreamScanner()
        streams = await scanner.scan_network()

        if streams:
            print(f"\n\033[92mSuccess! Found {len(streams)} streaming URLs!\033[0m")
            print("\nStreams found (copy and paste to use):")
            for stream in sorted(streams):
                print(f"\033[96m{stream}\033[0m")  # Cyan color for better visibility

            await save_streams(streams)
            print("\n\033[93mAll streams have been saved to streams.txt\033[0m")

            # Start monitoring the discovered streams
            print("\n\033[95mStarting stream monitoring...\033[0m")
            monitor = StreamMonitor()
            try:
                await monitor.start_monitoring(initial_streams=streams)
            except KeyboardInterrupt:
                monitor.stop_monitoring()
                print("\nStream monitoring stopped.")
        else:
            print("\n\033[91mNo streaming URLs found in the network.")
            print("Make sure streaming apps are running and try again.\033[0m")

    except KeyboardInterrupt:
        print("\n\033[93mScan interrupted by user.\033[0m")
    except Exception as e:
        logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())