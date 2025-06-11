import asyncio
import socket
from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived
from aioquic.asyncio.client import connect
from aioquic.h3.connection import H3_ALPN
from aioquic.h3.events import HeadersReceived, DataReceived, H3Event
from typing import Dict, Optional

class HttpQuicClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._http: Optional[H3Connection] = None
        self._request_events: Dict[int, asyncio.Event] = {}
        self._request_response: Dict[int, bytes] = {}
        self._request_headers: Dict[int, Dict] = {}

    async def get(self, url: str, headers: Dict = {}):
        # Buat stream baru
        stream_id = self._quic.get_next_available_stream_id()
        
        # Inisialisasi HTTP/3 connection jika belum ada
        if self._http is None:
            self._http = H3Connection(self._quic)
        
        # Kirim request headers
        self._http.send_headers(
            stream_id=stream_id,
            headers=[
                (b":method", b"GET"),
                (b":scheme", b"https"),
                (b":authority", url.split("/")[2].encode()),
                (b":path", url.split("/")[3].encode()),
                *[(k.encode(), v.encode()) for k, v in headers.items()],
            ],
        )
        
        # Akhiri stream
        self._quic.send_stream_data(stream_id, b"", end_stream=True)
        
        # Tunggu response
        event = asyncio.Event()
        self._request_events[stream_id] = event
        await event.wait()
        
        # Kembalikan response
        return {
            "headers": self._request_headers.pop(stream_id),
            "content": self._request_response.pop(stream_id),
        }

    def quic_event_received(self, event):
        if self._http is not None:
            for h3_event in self._http.handle_event(event):
                self.h3_event_received(h3_event)
        
    def h3_event_received(self, event: H3Event):
        if isinstance(event, HeadersReceived):
            # Simpan headers response
            headers = {}
            for header, value in event.headers:
                headers[header.decode()] = value.decode()
            self._request_headers[event.stream_id] = headers
            
        elif isinstance(event, DataReceived):
            # Simpan data response
            if event.stream_id not in self._request_response:
                self._request_response[event.stream_id] = b""
            self._request_response[event.stream_id] += event.data
            
            if event.stream_ended:
                self._request_events[event.stream_id].set()
                self._request_events.pop(event.stream_id)

async def make_quic_request(
    url: str,
    local_ip: str,
    headers: Dict = None,
    timeout: float = 10.0,
):
    # Konfigurasi QUIC
    configuration = QuicConfiguration(
        is_client=True,
        alpn_protocols=H3_ALPN,
        verify_mode=False  # Nonaktifkan verifikasi sertifikat untuk contoh
    )
    
    # Buat socket dengan binding ke IP lokal
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((local_ip, 0))  # Binding ke IP lokal, port acak
    
    # Buat koneksi QUIC
    async with connect(
        host=url.split("/")[2],
        port=443,
        configuration=configuration,
        create_protocol=HttpQuicClientProtocol,
        local_port=sock.getsockname()[1],
    ) as client:
        client = cast(HttpQuicClientProtocol, client)
        
        # Lakukan request dengan timeout
        try:
            response = await asyncio.wait_for(
                client.get(url, headers or {}),
                timeout=timeout,
            )
            return response
        except asyncio.TimeoutError:
            print("Request timeout")
            return None

if __name__ == "__main__":
    url = "https://example.com/path"  # Ganti dengan URL target
    local_ip = "192.168.1.100"  # Ganti dengan IP lokal yang ingin digunakan
    
    loop = asyncio.get_event_loop()
    response = loop.run_until_complete(make_quic_request(url, local_ip))
    
    if response:
        print("Headers:", response["headers"])
        print("Content:", response["content"].decode())
