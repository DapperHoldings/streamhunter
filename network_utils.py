import socket
import ipaddress
import threading
from queue import Queue
import logging

class NetworkScanner:
    def __init__(self):
        self.ports = [554, 8554, 1935, 8080, 80, 443] # Common streaming ports
        self.active_hosts = Queue()
        self.lock = threading.Lock()
        
    def get_local_ip(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            local_ip = sock.getsockname()[0]
            sock.close()
            return local_ip
        except Exception as e:
            logging.error(f"Error getting local IP: {e}")
            return "127.0.0.1"

    def scan_host(self, ip, timeout=1):
        open_ports = []
        for port in self.ports:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((str(ip), port))
            if result == 0:
                open_ports.append(port)
            sock.close()
        
        if open_ports:
            with self.lock:
                self.active_hosts.put((str(ip), open_ports))

    def scan_network(self, subnet):
        try:
            network = ipaddress.ip_network(subnet, strict=False)
            threads = []
            
            for ip in network.hosts():
                thread = threading.Thread(target=self.scan_host, args=(ip,))
                thread.start()
                threads.append(thread)
                
                # Limit concurrent threads
                if len(threads) >= 50:
                    for t in threads:
                        t.join()
                    threads = []
            
            # Wait for remaining threads
            for t in threads:
                t.join()
                
        except Exception as e:
            logging.error(f"Error scanning network: {e}")

    def get_active_hosts(self):
        hosts = []
        while not self.active_hosts.empty():
            hosts.append(self.active_hosts.get())
        return hosts
