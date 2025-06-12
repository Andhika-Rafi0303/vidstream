import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
import time

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'

class SourceIPAdapter(HTTPAdapter):
    def __init__(self, source_address, **kwargs):
        self.source_address = source_address
        super(SourceIPAdapter, self).__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs['source_address'] = (self.source_address, 0)
        return super(SourceIPAdapter, self).init_poolmanager(*args, **kwargs)

def fetch_video_segment(session, url):
    try:
        start_time = time.time()
        response = session.get(url, timeout=10)
        rtt = (time.time() - start_time) * 1000
        size_kb = len(response.content) / 1024
        status_code = response.status_code

        print(f"✅ {url} | Status: {status_code} | RTT: {rtt:.2f} ms | Size: {size_kb:.2f} KB")
        return {'url': url, 'rtt': rtt, 'size_kb': size_kb, 'status_code': status_code}
    except requests.exceptions.RequestException as e:
        print(f"❌ {url} | Error: {e}")
        return {'url': url, 'rtt': 0, 'size_kb': 0, 'status_code': None}

def generate_sequential_traffic(base_url, start_segment, end_segment, source_ip):
    session = requests.Session()
    session.mount('http://', SourceIPAdapter(source_ip))
    session.mount('https://', SourceIPAdapter(source_ip))
    session.headers.update({'User-Agent': USER_AGENT})

    results = []

    for i in range(start_segment, end_segment + 1):
        segment_name = f"segment_{i:03d}.mp4"
        full_url = f"{base_url}/{segment_name}"
        result = fetch_video_segment(session, full_url)
        results.append(result)

    valid_results = [r for r in results if r['status_code'] == 200]

    if valid_results:
        avg_rtt = sum(r['rtt'] for r in valid_results) / len(valid_results)
        avg_size = sum(r['size_kb'] for r in valid_results) / len(valid_results)

        print("\n📊 Rekap Hasil:")
        print(f"📺 Total Berhasil: {len(valid_results)} dari {len(results)} segment")
        print(f"⚡ Rata-rata RTT: {avg_rtt:.2f} ms")
        print(f"📦 Rata-rata Size: {avg_size:.2f} KB")
    else:
        print("\n❌ Tidak ada segment yang berhasil diakses.")

if __name__ == "__main__":
    base_url = "http://12.12.12.2/output"
    source_ip = "10.60.0.3"
    generate_sequential_traffic(base_url, start_segment=0, end_segment=2, source_ip=source_ip)
