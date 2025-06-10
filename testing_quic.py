import asyncio
import time
import socket
import ssl
from urllib.parse import urlparse
from aioquic.asyncio.client import connect
from aioquic.quic.configuration import QuicConfiguration
from aioquic.h3.connection import H3_ALPN

USER_AGENT = b"aioquic-client"

async def http3_qos_request(url, source_ip='0.0.0.0'):
    sock = None
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        path = parsed.path if parsed.path else "/"
        port = parsed.port or 443

        configuration = QuicConfiguration(
            is_client=True,
            alpn_protocols=H3_ALPN,
            verify_mode=ssl.CERT_NONE
        )

        # Setup socket dengan reuse address dan port
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass  # SO_REUSEPORT tidak tersedia di semua sistem

        sock.bind((source_ip, 0))

        # Gunakan timeout untuk socket
        sock.settimeout(10)

        # Measure RTT
        start_rtt = time.time()

        async with connect(
            host,
            port,
            configuration=configuration,
            create_protocol=lambda: None,
            local_port=sock.getsockname()[1],
        ) as client:
            rtt = (time.time() - start_rtt) * 1000

            h3 = client._http
            stream_id = h3.get_next_available_stream_id()

            h3.send_headers(
                stream_id,
                [
                    (b":method", b"GET"),
                    (b":scheme", b"https"),
                    (b":authority", host.encode()),
                    (b":path", path.encode()),
                    (b"user-agent", USER_AGENT),
                ],
                end_stream=True,
            )

            body = b""
            start_latency = time.time()

            while True:
                try:
                    event = await asyncio.wait_for(client.wait_for_event(), timeout=10)
                    if event is None:
                        break
                    if hasattr(event, "data") and event.data:
                        body += event.data
                except asyncio.TimeoutError:
                    print("Timeout saat menunggu event")
                    break

            latency = (time.time() - start_latency) * 1000
            total_kb = len(body) / 1024
            throughput = total_kb / (latency / 1000) if latency > 0 else 0

            return {
                "rtt_ms": rtt,
                "latency_ms": latency,
                "total_size_kb": total_kb,
                "throughput_kbps": throughput,
            }

    except Exception as e:
        print(f"💥 Error: {str(e)}")
        return None
    finally:
        if sock:
            try:
                sock.close()
            except:
                pass

async def run_requests(url, source_ip, num_requests):
    results = []
    for i in range(num_requests):
        print(f"🚀 Menjalankan request {i+1}/{num_requests}")
        result = await http3_qos_request(url, source_ip)
        if result:
            results.append(result)
        await asyncio.sleep(1)  # Jeda antar request
    return results

def measure_multiple_requests(url, source_ip, num_requests=5):
    try:
        loop = asyncio.get_event_loop()
    except:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    results = loop.run_until_complete(run_requests(url, source_ip, num_requests))

    if results:
        avg = lambda key: sum(r[key] for r in results) / len(results)
        print(f"\n📊 Hasil Pengujian:")
        print(f"🔥 Total Request Berhasil: {len(results)}/{num_requests}")
        print(f"⚡ Rata-rata RTT: {avg('rtt_ms'):.2f} ms")
        print(f"⏱️ Rata-rata Latency: {avg('latency_ms'):.2f} ms")
        print(f"📦 Rata-rata Ukuran: {avg('total_size_kb'):.2f} KB")
        print(f"🚀 Rata-rata Throughput: {avg('throughput_kbps'):.2f} KB/s")
    else:
        print("❌ Tidak ada request yang berhasil")

if __name__ == "__main__":
    # Konfigurasi pengujian
    TEST_URL = "https://quic.nginx.org/"  # Server test QUIC
    # TEST_URL = "https://cloudflare-quic.com/"  # Alternatif
    SOURCE_IP = "0.0.0.0"  # Gunakan IP lokal yang sesuai jika perlu
    REQUEST_COUNT = 5
    
    print("🔧 Memulai pengujian HTTP/3...")
    measure_multiple_requests(TEST_URL, SOURCE_IP, REQUEST_COUNT)
    print("✅ Pengujian selesai")
