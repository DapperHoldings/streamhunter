"""Main entry point for the streaming URL scanner."""
import asyncio
import logging
from scanner import StreamScanner
from utils import save_streams

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    try:
        print("Starting network scan for streaming URLs...")
        scanner = StreamScanner()
        streams = await scanner.scan_network()
        
        if streams:
            print(f"\nFound {len(streams)} streaming URLs:")
            for stream in sorted(streams):
                print(f"- {stream}")
            
            await save_streams(streams)
        else:
            print("\nNo streaming URLs found in the network.")
            
    except KeyboardInterrupt:
        print("\nScan interrupted by user.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
