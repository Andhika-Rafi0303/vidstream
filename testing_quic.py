import asyncio
import time
import socket
from urllib.parse import urlparse
from aioquic.asyncio.client import connect
from aioquic.quic.configuration import QuicConfiguration
from aioquic.h3.connection import H3_ALPN

USER_AGENT = b"aioquic-client"

async def http3_qos_request(url, source_ip='10.60.0.3'):
    parsed = urlparse(url)
    host = parsed.hostname
    path = parsed.path if parsed.path else "/"
    port = parsed.port or 443

    configuration = QuicConfiguration(is_client=True, alpn_protocols=H3_ALPN)

    # Bind to specific IP
    local_addr = (source_ip, 0)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(local_addr)

    # Measure RTT
    start_rtt = time.time()

    async with connect(
        host,
        port,
        configuration=configuration,
        create_connection=lambda: sock,
        local_port=sock.getsockname()[1],
        local_host=source_ip,
    ) as client:

        rtt = (time.time() - start_rtt) * 1000

        h3 = client.http
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
            event = await client.wait_for_event()
            if event is None:
                break
            if hasattr(event, "data") and event.data:
                body += event.data

        latency = (time.time() - start_latency) * 1000
        total_kb = len(body) / 1024
        throughput = total_kb / (latency / 1000) if latency > 0 else 0

        return {
            "rtt_ms": rtt,
            "latency_ms": latency,
            "total_size_kb": total_kb,
            "throughput_kbps": throughput,
        }

def measure_multiple_requests(url, source_ip, num_requests=5):
    results = []

    async def runner():
        for _ in range(num_requests):
            try:
                result = await http3_qos_request(url, source_ip)
                if result:
                    results.append(result)
            except Exception as e:
                print(f"💥 Error: {e}")

    asyncio.run(runner())

    if results:
        avg = lambda key: sum(r[key] for r in results) / len(results)
        print(f"\n🔥 Total Request: {len(results)}")
        print(f"⚡ Rata-rata RTT: {avg('rtt_ms'):.2f} ms")
        print(f"⏱️ Rata-rata Latency: {avg('latency_ms'):.2f} ms")
        print(f"📦 Rata-rata Size: {avg('total_size_kb'):.2f} KB")
        print(f"🚀 Rata-rata Throughput: {avg('throughput_kbps'):.2f} KB/s")
    else:
        print("❌ Tidak ada hasil yang berhasil.")

if __name__ == "__main__":
    url = "https://cloudflare-quic.com/"
    source_ip = "10.60.0.3"
    measure_multiple_requests(url, source_ip, num_requests=5)
