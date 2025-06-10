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
    sock = None  # Deklarasikan di sini untuk memastikan bisa diakses di blok finally
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

        # Bind to specific IP dengan socket reuse
        local_addr = (source_ip, 0)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Ini yang penting!
        sock.bind(local_addr)

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

    except Exception as e:
        print(f"💥 Error during request: {e}")
        return None
    finally:
        if sock is not None:  # Pastikan socket selalu ditutup
            sock.close()

def measure_multiple_requests(url, source_ip, num_requests=5):
    results = []

    async def runner():
        tasks = []
        for _ in range(num_requests):
            task = asyncio.create_task(http3_qos_request(url, source_ip))
            tasks.append(task)
        
        for task in tasks:
            result = await task
            if result:
                results.append(result)
            await asyncio.sleep(1)  # Jeda antara request

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
    url = "https://12.12.12.2/index10.html"
    source_ip = "10.45.0.10"
    measure_multiple_requests(url, source_ip, num_requests=5)
