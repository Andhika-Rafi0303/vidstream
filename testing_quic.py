import asyncio
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration
from aioquic.h3.connection import H3_ALPN
from aioquic.h3.events import HeadersReceived, DataReceived
from urllib.parse import urlparse, urljoin
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import ssl

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'

class QUICClient:
    def __init__(self, source_ip=None):
        self.source_ip = source_ip
        self.configuration = QuicConfiguration(
            alpn_protocols=H3_ALPN,
            is_client=True,
            verify_mode=ssl.CERT_NONE  # For testing only, remove in production
        )
        if source_ip:
            self.configuration.local_address = (source_ip, 0)

    async def fetch(self, url, method="GET", headers=None, body=None):
        parsed = urlparse(url)
        host = parsed.netloc
        path = parsed.path or "/"
        
        if headers is None:
            headers = {}
        headers["user-agent"] = USER_AGENT
        headers[":method"] = method
        headers[":scheme"] = parsed.scheme
        headers[":authority"] = host
        headers[":path"] = path
        
        async with connect(
            host,
            parsed.port or 443,
            configuration=self.configuration,
            create_protocol=H3Connection,
        ) as protocol:
            stream_id = protocol.quic.get_next_available_stream_id()
            protocol.send_headers(stream_id=stream_id, headers=headers)
            if body:
                protocol.send_data(stream_id=stream_id, data=body)
            
            response_headers = {}
            response_body = b""
            response_status = None
            
            while True:
                event = await protocol.wait_for_event()
                if isinstance(event, HeadersReceived):
                    for header, value in event.headers:
                        if header == b":status":
                            response_status = int(value.decode())
                        elif isinstance(header, bytes) and isinstance(value, bytes):
                            response_headers[header.decode()] = value.decode()
                elif isinstance(event, DataReceived):
                    response_body += event.data
                if event.stream_ended:
                    break
            
            return {
                "status": response_status,
                "headers": response_headers,
                "content": response_body.decode(),
                "body": response_body
            }

class H3Connection:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._http = None
        
    def quic_event_received(self, event):
        if self._http is None:
            self._http = H3Connection(self._quic)
        self._http.handle_event(event)

def extract_links(html, base_url):
    pattern = r'<img[^>]+src=["\'](.*?)["\']|<script[^>]+src=["\'](.*?)["\']|<link[^>]+href=["\'](.*?)["\']'
    matches = re.findall(pattern, html, re.IGNORECASE)
    links = set()
    for match in matches:
        for link in match:
            if link:
                absolute_link = urljoin(base_url, link)
                links.add(absolute_link)
    return links

async def fetch_url_quic(client, url):
    try:
        start_time = time.time()
        response = await client.fetch(url)
        fetch_time = time.time() - start_time
        return len(response['body']), response['status'], fetch_time
    except Exception as e:
        print(f"💥 Error fetching {url}: {e}")
        return 0, None, 0

async def measure_performance_once_quic(client, url):
    try:
        start_rtt = time.time()
        response = await client.fetch(url)
        rtt = (time.time() - start_rtt) * 1000
        status_code = response['status']
    except Exception as e:
        print(f"💥 Error request: {e}")
        return None

    links = extract_links(response['content'], url)
    total_size = len(response['body'])

    start_fetch = time.time()
    
    # Run async tasks concurrently
    tasks = [fetch_url_quic(client, link) for link in links]
    results = await asyncio.gather(*tasks)
    
    for size, _, _ in results:
        total_size += size
    
    fetch_time = time.time() - start_fetch

    throughput = (total_size / 1024) / fetch_time if fetch_time > 0 else 0
    latency = fetch_time * 1000

    return {
        'rtt': rtt,
        'total_size_kb': total_size / 1024,
        'throughput_kbps': throughput,
        'latency_ms': latency,
        'status_code': status_code
    }

async def measure_multiple_requests_quic(url, source_ip, num_requests=10):
    client = QUICClient(source_ip)
    
    results = []
    tasks = [measure_performance_once_quic(client, url) for _ in range(num_requests)]
    results = await asyncio.gather(*tasks)
    
    valid_results = [r for r in results if r is not None]
    
    if not valid_results:
        print("No successful requests")
        return
    
    avg_rtt = sum(r['rtt'] for r in valid_results) / len(valid_results)
    avg_size = sum(r['total_size_kb'] for r in valid_results) / len(valid_results)
    avg_throughput = sum(r['throughput_kbps'] for r in valid_results) / len(valid_results)
    avg_latency = sum(r['latency_ms'] for r in valid_results) / len(valid_results)

    print(f"\n🔥 Total Request: {len(valid_results)}")
    print(f"⚡ Rata-rata RTT: {avg_rtt:.2f} ms")
    print(f"📦 Rata-rata Size: {avg_size:.2f} KB")
    print(f"🚀 Rata-rata Throughput: {avg_throughput:.2f} KB/s")
    print(f"⏱️ Rata-rata Latency: {avg_latency:.2f} ms")

if __name__ == "__main__":
    url = 'https://12.12.12.2/index1.html'  # Note: QUIC typically uses HTTPS
    source_ip = '10.45.0.0'
    
    # Run the async function
    asyncio.run(measure_multiple_requests_quic(url, source_ip, num_requests=10))
