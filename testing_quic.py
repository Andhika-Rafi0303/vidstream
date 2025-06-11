import asyncio
import socket
from typing import Dict, Optional, cast
from aioquic.asyncio import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import HeadersReceived, DataReceived, H3Event
from aioquic.asyncio.client import connect

class HttpQuicClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._http: Optional[H3Connection] = None
        self._request_events: Dict[int, asyncio.Event] = {}
        self._request_response: Dict[int, bytes] = {}
        self._request_headers: Dict[int, Dict] = {}

    async def get(self, url: str, headers: Dict = None):
        if headers is None:
            headers = {}
            
        # Parse URL components
        url_parts = url.split("/")
        host = url_parts[2]
        path = "/" + "/".join(url_parts[3:]) if len(url_parts) > 3 else "/"

        # Get next available stream ID
        stream_id = self._quic.get_next_available_stream_id()
        
        # Initialize HTTP/3 connection if not exists
        if self._http is None:
            self._http = H3Connection(self._quic)
        
        # Send request headers
        self._http.send_headers(
            stream_id=stream_id,
            headers=[
                (b":method", b"GET"),
                (b":scheme", b"https"),
                (b":authority", host.encode()),
                (b":path", path.encode()),
                *[(k.encode(), v.encode()) for k, v in headers.items()],
            ],
        )
        
        # End the stream
        self._quic.send_stream_data(stream_id, b"", end_stream=True)
        
        # Wait for response
        event = asyncio.Event()
        self._request_events[stream_id] = event
        await event.wait()
        
        # Return response
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
            # Store response headers
            headers = {}
            for header, value in event.headers:
                headers[header.decode()] = value.decode()
            self._request_headers[event.stream_id] = headers
            
        elif isinstance(event, DataReceived):
            # Store response data
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
    retries: int = 3,
):
    if headers is None:
        headers = {}

    # QUIC configuration
    configuration = QuicConfiguration(
        is_client=True,
        alpn_protocols=H3_ALPN,
        verify_mode=False  # Disable cert verification for testing
    )
    
    # Parse host from URL
    host = url.split("/")[2]
    
    last_error = None
    for attempt in range(retries):
        try:
            # Create UDP socket with SO_REUSEADDR
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((local_ip, 0))  # Bind to local IP with random port
            
            try:
                async with connect(
                    host=host,
                    port=443,
                    configuration=configuration,
                    create_protocol=HttpQuicClientProtocol,
                    local_port=sock.getsockname()[1],
                ) as client:
                    client = cast(HttpQuicClientProtocol, client)
                    
                    try:
                        response = await asyncio.wait_for(
                            client.get(url, headers),
                            timeout=timeout,
                        )
                        return response
                    except asyncio.TimeoutError:
                        print(f"Attempt {attempt + 1}: Request timeout")
                        last_error = "Timeout"
                    except Exception as e:
                        print(f"Attempt {attempt + 1}: Request failed - {str(e)}")
                        last_error = str(e)
            finally:
                sock.close()
                
        except OSError as e:
            print(f"Attempt {attempt + 1}: Socket error - {str(e)}")
            last_error = str(e)
            await asyncio.sleep(1)  # Wait before retry
            continue
            
    print(f"All {retries} attempts failed. Last error: {last_error}")
    return None

async def main():
    url = "https://12.12.12.2/index1.html"  # Replace with your target URL
    local_ip = "192.168.1.161"    # Replace with your local IP
    
    print(f"Making QUIC request to {url} from {local_ip}")
    
    response = await make_quic_request(url, local_ip)
    
    if response:
        print("\nResponse Headers:")
        for key, value in response["headers"].items():
            print(f"{key}: {value}")
        
        print("\nResponse Content:")
        print(response["content"].decode())
    else:
        print("Failed to get response")

if __name__ == "__main__":
    asyncio.run(main())
