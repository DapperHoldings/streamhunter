# Network Streaming URL Scanner for Termux

A Python-based network scanner that detects and lists active streaming URLs from outside the Termux environment. The scanner supports various streaming protocols including RTSP, HLS, DASH, and RTMP.

## Features

- Scans local network for active streaming endpoints
- Supports multiple streaming protocols:
  - RTSP (Real Time Streaming Protocol)
  - HLS (HTTP Live Streaming)
  - DASH (Dynamic Adaptive Streaming over HTTP)
  - RTMP (Real-Time Messaging Protocol)
- Protocol-specific scanning for better accuracy
- Concurrent scanning for improved performance
- Progress tracking during scan
- Saves discovered streams to a file

## Installation in Termux

1. Install Termux from [F-Droid](https://f-droid.org/packages/com.termux/)

2. Install required packages in Termux:
```bash
pkg update && pkg upgrade
pkg install python
```

3. Install Python dependencies:
```bash
pip install aiohttp requests
```

4. Download the scanner files:
```bash
curl -O https://raw.githubusercontent.com/yourusername/network-scanner/main/{main.py,scanner.py,protocols.py,utils.py}
```

## Usage

1. Run the scanner:
```bash
python main.py
```

The scanner will:
- Automatically detect your local network
- Scan for active streaming URLs
- Display progress in real-time
- Save discovered streams to `streams.txt`

### Output Example

During scanning, you'll see:
```
Starting network scan for streaming URLs...
Scanning progress: 45.2% (115/254)
Found RTSP stream: rtsp://192.168.1.100:554/live
Found HLS stream: http://192.168.1.150:8081/stream/index.m3u8
...
Scan completed!

Found 3 streaming URLs:
- http://192.168.1.100:8080/stream
- rtsp://192.168.1.150:554/live
- http://192.168.1.200:1935/hls/stream
```

### Results

All discovered streaming URLs are saved to `streams.txt`, which you can view using:
```bash
cat streams.txt
```

## Supported Protocols and Ports

The scanner checks these protocols on their standard ports:
- RTSP: 554, 8554
- HTTP/HTTPS: 80, 443, 8080, 8000, 8443
- HLS: 8081, 1935
- RTMP: 1935

## Troubleshooting

1. **Scan is slow**
   - The scanner checks multiple ports and protocols
   - A full network scan can take several minutes
   - Progress percentage is shown to track status

2. **No streams found**
   - Verify streaming services are running
   - Check if your device has proper network access
   - Ensure you're on the correct network
   - Some devices may block scanning attempts

3. **Permission errors**
   - Ensure Termux has network access permission
   - Try running in a network where you have proper access

4. **Connection errors**
   - Check your internet connection
   - Verify you're connected to the target network
   - Some networks may block scanning activities

## Notes

- The scanner is designed for local network use
- It uses non-intrusive methods to detect streams
- Results are automatically saved to `streams.txt`
- Some networks may block scanning activities
- Always ensure you have permission to scan the network

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is open source and available under the MIT License.