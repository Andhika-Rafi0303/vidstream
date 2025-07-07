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

def fetch_video_segment(session, url, record_start=False):
    try:
        if record_start:
            start_request_time = time.time()
        else:
            start_request_time = None

        start_time = time.time()
        response = session.get(url, timeout=10)
        rtt = (time.time() - start_time)
        size_kb = len(response.content) / 1024
        status_code = response.status_code
        throughput = size_kb / rtt if rtt > 0 else 0  # KB/s

        print(f"✅ {url} | Status: {status_code} | RTT: {rtt * 1000:.2f} ms | Size: {size_kb:.2f} KB | Throughput: {throughput:.2f} KB/s")
        return {
            'url': url,
            'rtt': rtt,
            'size_kb': size_kb,
            'status_code': status_code,
            'throughput': throughput,
            'start_request_time': start_request_time
        }
    except requests.exceptions.RequestException as e:
        print(f"❌ {url} | Error: {e}")
        return {
            'url': url,
            'rtt': 0,
            'size_kb': 0,
            'status_code': None,
            'throughput': 0,
            'start_request_time': start_request_time
        }

def generate_sequential_traffic(start_segment, end_segment, source_ip):
    base_url = "http://12.12.12.2/output"

    session = requests.Session()
    session.mount('http://', SourceIPAdapter(source_ip))
    session.mount('https://', SourceIPAdapter(source_ip))
    session.headers.update({'User-Agent': USER_AGENT})

    results = []

    program_start_time = time.time()
    first_request_start_time = None

    for i in range(start_segment, end_segment + 1):
        segment_name = f"segment_{i:03d}.mp4"
        full_url = f"{base_url}/{segment_name}"

        # Cuma set True buat request pertama
        record_start = True if first_request_start_time is None else False

        result = fetch_video_segment(session, full_url, record_start=record_start)

        if result.get('start_request_time') and first_request_start_time is None:
            first_request_start_time = result['start_request_time']

        results.append(result)

    startup_delay = (first_request_start_time - program_start_time) if first_request_start_time else 0

    valid_results = [r for r in results if isinstance(r, dict) and r.get('status_code') == 200]

    if valid_results:
        avg_rtt = sum(r['rtt'] for r in valid_results) / len(valid_results) * 1000  # ms
        avg_size = sum(r['size_kb'] for r in valid_results) / len(valid_results)
        avg_throughput = sum(r['throughput'] for r in valid_results) / len(valid_results)

        print("\n📊 Rekap Hasil:")
        print(f"⏱️ Startup Delay: {startup_delay:.2f} detik")
        print(f"📺 Total Berhasil: {len(valid_results)} dari {len(results)} segment")
        print(f"⚡ Rata-rata RTT: {avg_rtt:.2f} ms")
        print(f"📦 Rata-rata Size: {avg_size:.2f} KB")
        print(f"🚀 Rata-rata Throughput: {avg_throughput:.2f} KB/s")
    else:
        print("\n❌ Tidak ada segment yang berhasil diakses.")
        
if __name__ == "__main__":
    source_ip = input("Masukkan Source IP: ").strip()
    start_segment = int(input("Masukkan Start Segment: "))
    end_segment = int(input("Masukkan End Segment: "))

    generate_sequential_traffic(start_segment, end_segment, source_ip)
