import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'

class SourceIPAdapter(HTTPAdapter):
    def __init__(self, source_address, **kwargs):
        self.source_address = source_address
        super(SourceIPAdapter, self).__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs['source_address'] = (self.source_address, 0)
        return super(SourceIPAdapter, self).init_poolmanager(*args, **kwargs)

def fetch_video(session, url):
    try:
        start = time.time()
        response = session.get(url, timeout=10)
        rtt = (time.time() - start) * 1000
        size_kb = len(response.content) / 1024
        status_code = response.status_code
        return {'url': url, 'rtt': rtt, 'size_kb': size_kb, 'status_code': status_code}
    except requests.exceptions.RequestException as e:
        print(f"💥 Error fetching {url}: {e}")
        return {'url': url, 'rtt': 0, 'size_kb': 0, 'status_code': None}

def generate_traffic(base_url, segments, source_ip, num_requests_per_segment=10):
    session = requests.Session()
    session.mount('http://', SourceIPAdapter(source_ip))
    session.mount('https://', SourceIPAdapter(source_ip))
    session.headers.update({'User-Agent': USER_AGENT})

    urls = [f"{base_url}/segment_{i:03d}.mp4" for i in range(1, segments + 1)]
    all_results = []

    with ThreadPoolExecutor(max_workers=segments * num_requests_per_segment) as executor:
        futures = []
        for url in urls:
            for _ in range(num_requests_per_segment):
                futures.append(executor.submit(fetch_video, session, url))

        for future in as_completed(futures):
            result = future.result()
            if result:
                all_results.append(result)

    # Statistik
    valid_results = [r for r in all_results if r['status_code'] == 200]
    if not valid_results:
        print("❌ Tidak ada response sukses.")
        return

    avg_rtt = sum(r['rtt'] for r in valid_results) / len(valid_results)
    avg_size = sum(r['size_kb'] for r in valid_results) / len(valid_results)

    print(f"\n📺 Total Request Sukses: {len(valid_results)}")
    print(f"⚡ Rata-rata RTT: {avg_rtt:.2f} ms")
    print(f"📦 Rata-rata Size: {avg_size:.2f} KB")

if __name__ == "__main__":
    base_url = "http://12.12.12.2/output"
    source_ip = "10.60.0.3"
    generate_traffic(base_url, segments=2, source_ip=source_ip, num_requests_per_segment=10)
