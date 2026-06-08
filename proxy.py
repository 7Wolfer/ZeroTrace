"""
Local MITM proxy that intercepts HTTPS traffic to assetdelivery.roblox.com
and blocks specific asset IDs while forwarding everything else.

Requires the `cryptography` package for certificate generation.
On first use, install the self-signed CA via the UI (needs admin rights once).
"""

import socket
import ssl
import threading
import re
import os
import subprocess
import ctypes
import logging
from pathlib import Path

try:
    import winreg
    WINREG_OK = True
except ImportError:
    WINREG_OK = False

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import datetime
    CRYPTO_OK = True
except ImportError:
    CRYPTO_OK = False

PROXY_HOST = '127.0.0.1'
PROXY_PORT = 8888
INTERCEPT_HOSTS = {'assetdelivery.roblox.com'}
CERTS_DIR = Path(os.environ.get('APPDATA', '.')) / 'ZeroTrace' / 'certs'

log = logging.getLogger('zerotrace.proxy')


# ─── Certificate Management ──────────────────────────────────────────────────

class CertManager:
    CA_CN = 'ZeroTrace Asset Blocker CA'

    def __init__(self):
        CERTS_DIR.mkdir(parents=True, exist_ok=True)
        self._ca_key_path = CERTS_DIR / 'ca.key'
        self._ca_cert_path = CERTS_DIR / 'ca.crt'
        self.ca_key = None
        self.ca_cert = None
        if CRYPTO_OK:
            self._init_ca()

    def _init_ca(self):
        if self._ca_key_path.exists() and self._ca_cert_path.exists():
            with open(self._ca_key_path, 'rb') as f:
                self.ca_key = serialization.load_pem_private_key(f.read(), password=None)
            with open(self._ca_cert_path, 'rb') as f:
                self.ca_cert = x509.load_pem_x509_certificate(f.read())
        else:
            self._generate_ca()

    def _generate_ca(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, self.CA_CN),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'ZeroTrace'),
        ])
        now = datetime.datetime.utcnow()
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True, content_commitment=False,
                    key_encipherment=False, data_encipherment=False,
                    key_agreement=False, key_cert_sign=True,
                    crl_sign=True, encipher_only=False, decipher_only=False,
                ),
                critical=True,
            )
            .sign(key, hashes.SHA256())
        )
        with open(self._ca_key_path, 'wb') as f:
            f.write(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            ))
        with open(self._ca_cert_path, 'wb') as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        self.ca_key = key
        self.ca_cert = cert

    def host_cert(self, hostname: str) -> tuple[str, str]:
        """Return (cert_path, key_path) for hostname, generating if needed."""
        safe = hostname.replace('.', '_')
        crt = CERTS_DIR / f'{safe}.crt'
        key = CERTS_DIR / f'{safe}.key'
        if not crt.exists():
            k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
            now = datetime.datetime.utcnow()
            c = (
                x509.CertificateBuilder()
                .subject_name(name)
                .issuer_name(self.ca_cert.subject)
                .public_key(k.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now)
                .not_valid_after(now + datetime.timedelta(days=825))
                .add_extension(
                    x509.SubjectAlternativeName([x509.DNSName(hostname)]),
                    critical=False,
                )
                .sign(self.ca_key, hashes.SHA256())
            )
            with open(key, 'wb') as f:
                f.write(k.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.TraditionalOpenSSL,
                    serialization.NoEncryption(),
                ))
            with open(crt, 'wb') as f:
                f.write(c.public_bytes(serialization.Encoding.PEM))
        return str(crt), str(key)

    @property
    def ca_cert_path(self) -> str:
        return str(self._ca_cert_path)

    def is_installed(self) -> bool:
        r = subprocess.run(
            ['certutil', '-verifystore', 'ROOT', self.CA_CN],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        return r.returncode == 0

    def install(self) -> bool:
        r = subprocess.run(
            ['certutil', '-addstore', '-f', 'ROOT', self._ca_cert_path],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        return r.returncode == 0

    def uninstall(self) -> bool:
        r = subprocess.run(
            ['certutil', '-delstore', 'ROOT', self.CA_CN],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        return r.returncode == 0


# ─── Asset ID extraction ─────────────────────────────────────────────────────

_ID_PATTERNS = [
    re.compile(r'[?&]id=(\d+)', re.IGNORECASE),
    re.compile(r'/assetId/(\d+)', re.IGNORECASE),
    re.compile(r'/(\d{6,})(?:[/?]|$)'),
]


def _extract_asset_id(path_and_query: str) -> str | None:
    for p in _ID_PATTERNS:
        m = p.search(path_and_query)
        if m:
            return m.group(1)
    return None


# ─── Proxy connection handler ─────────────────────────────────────────────────

def _pipe(src, dst, stop_event: threading.Event):
    try:
        while not stop_event.is_set():
            try:
                data = src.recv(32768)
            except (OSError, ssl.SSLError):
                break
            if not data:
                break
            try:
                dst.sendall(data)
            except (OSError, ssl.SSLError):
                break
    finally:
        stop_event.set()


def _bidirectional_pipe(a, b):
    ev = threading.Event()
    t1 = threading.Thread(target=_pipe, args=(a, b, ev), daemon=True)
    t2 = threading.Thread(target=_pipe, args=(b, a, ev), daemon=True)
    t1.start()
    t2.start()
    ev.wait()


def _close_graceful(sock):
    """Shutdown send side first so the peer reads all data before RST."""
    try:
        sock.shutdown(socket.SHUT_WR)
    except OSError:
        pass
    try:
        sock.settimeout(1.0)
        while sock.recv(4096):
            pass
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def _recv_header(sock) -> bytes:
    """Read until \\r\\n\\r\\n."""
    buf = b''
    while b'\r\n\r\n' not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
        if len(buf) > 65536:
            break
    return buf


class _ConnectionHandler(threading.Thread):
    def __init__(self, client: socket.socket, blocked: set, certs: CertManager | None):
        super().__init__(daemon=True)
        self._client = client
        self._blocked = blocked
        self._certs = certs

    def run(self):
        try:
            self._dispatch()
        except Exception as e:
            log.debug('Handler error: %s', e)
        finally:
            _close_graceful(self._client)

    def _dispatch(self):
        raw = _recv_header(self._client)
        if not raw:
            return
        first_line = raw.split(b'\r\n', 1)[0].decode('latin-1', errors='replace')
        parts = first_line.split(' ')
        if len(parts) < 2:
            return
        method = parts[0].upper()
        if method == 'CONNECT':
            self._handle_connect(parts[1])
        else:
            self._handle_plain_http(method, parts[1], raw)

    # ── CONNECT (HTTPS) ────────────────────────────────────────────────────

    def _handle_connect(self, target: str):
        host, _, port_s = target.rpartition(':')
        host = host or target
        port = int(port_s) if port_s.isdigit() else 443

        if host in INTERCEPT_HOSTS and CRYPTO_OK and self._certs and self._certs.ca_key:
            self._handle_mitm(host, port)
        else:
            self._tunnel_connect(host, port)

    def _tunnel_connect(self, host: str, port: int):
        try:
            srv = socket.create_connection((host, port), timeout=15)
        except OSError:
            self._client.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
            return
        self._client.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
        try:
            _bidirectional_pipe(self._client, srv)
        finally:
            srv.close()

    def _handle_mitm(self, host: str, port: int):
        try:
            crt_path, key_path = self._certs.host_cert(host)
        except Exception as e:
            log.error('Cert gen failed for %s: %s', host, e)
            self._tunnel_connect(host, port)
            return

        self._client.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')

        ctx_srv = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx_srv.load_cert_chain(crt_path, key_path)
        try:
            ssl_client = ctx_srv.wrap_socket(self._client, server_side=True)
        except ssl.SSLError as e:
            log.debug('Client SSL handshake failed: %s', e)
            return

        try:
            self._intercept_https(ssl_client, host, port)
        finally:
            try:
                ssl_client.close()
            except OSError:
                pass

    def _intercept_https(self, ssl_client: ssl.SSLSocket, host: str, port: int):
        # Read first request from client
        raw = _recv_header(ssl_client)
        if not raw:
            return

        first_line = raw.split(b'\r\n', 1)[0].decode('latin-1', errors='replace')
        parts = first_line.split(' ')
        path = parts[1] if len(parts) >= 2 else '/'

        asset_id = _extract_asset_id(path)
        if asset_id and asset_id in self._blocked:
            log.info('Blocked asset ID %s', asset_id)
            ssl_client.sendall(
                b'HTTP/1.1 404 Not Found\r\n'
                b'Content-Length: 0\r\n'
                b'Connection: close\r\n\r\n'
            )
            return

        # Forward: connect to real server, send first request, then pipe
        ctx = ssl.create_default_context()
        try:
            raw_srv = socket.create_connection((host, port), timeout=15)
            ssl_srv = ctx.wrap_socket(raw_srv, server_hostname=host)
        except OSError as e:
            log.debug('Cannot reach %s:%d — %s', host, port, e)
            ssl_client.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
            return

        try:
            ssl_srv.sendall(raw)
            _bidirectional_pipe(ssl_client, ssl_srv)
        finally:
            ssl_srv.close()

    # ── Plain HTTP ─────────────────────────────────────────────────────────

    def _handle_plain_http(self, method: str, url: str, raw: bytes):
        try:
            from urllib.parse import urlparse
            p = urlparse(url)
            host = p.hostname or ''
            port = p.port or 80
            path = p.path + (('?' + p.query) if p.query else '')
        except Exception:
            self._client.sendall(b'HTTP/1.1 400 Bad Request\r\n\r\n')
            return

        if host in INTERCEPT_HOSTS:
            asset_id = _extract_asset_id(path)
            if asset_id and asset_id in self._blocked:
                log.info('Blocked HTTP asset ID %s', asset_id)
                self._client.sendall(
                    b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                )
                return

        try:
            srv = socket.create_connection((host, port), timeout=15)
        except OSError:
            self._client.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
            return
        try:
            srv.sendall(raw)
            _bidirectional_pipe(self._client, srv)
        finally:
            srv.close()


# ─── Proxy server ─────────────────────────────────────────────────────────────

class AssetBlockerProxy:
    def __init__(self):
        self._blocked: set[str] = set()
        self._certs = CertManager() if CRYPTO_OK else None
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._running

    @property
    def crypto_available(self) -> bool:
        return CRYPTO_OK

    def set_blocked(self, asset_ids: list):
        self._blocked = {str(a) for a in asset_ids}

    def start(self) -> bool:
        if self._running:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((PROXY_HOST, PROXY_PORT))
            s.listen(100)
            self._server = s
            self._running = True
            self._thread = threading.Thread(target=self._accept_loop, daemon=True)
            self._thread.start()
            _set_system_proxy(PROXY_HOST, PROXY_PORT)
            return True
        except OSError as e:
            log.error('Proxy start failed: %s', e)
            self._running = False
            return False

    def stop(self):
        self._running = False
        _clear_system_proxy()
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None

    def ca_installed(self) -> bool:
        return self._certs.is_installed() if self._certs else False

    def install_ca(self) -> bool:
        return self._certs.install() if self._certs else False

    def uninstall_ca(self) -> bool:
        return self._certs.uninstall() if self._certs else False

    # ── Internal ──────────────────────────────────────────────────────────

    def _accept_loop(self):
        self._server.settimeout(1.0)
        while self._running:
            try:
                client, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            _ConnectionHandler(client, self._blocked, self._certs).start()


# ─── Windows proxy registry helpers ──────────────────────────────────────────

def _set_system_proxy(host: str, port: int):
    if not WINREG_OK:
        return
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Internet Settings',
            0, winreg.KEY_WRITE,
        )
        winreg.SetValueEx(key, 'ProxyServer', 0, winreg.REG_SZ, f'{host}:{port}')
        winreg.SetValueEx(key, 'ProxyEnable', 0, winreg.REG_DWORD, 1)
        # Bypass localhost so Windows apps aren't blocked
        winreg.SetValueEx(
            key, 'ProxyOverride', 0, winreg.REG_SZ,
            'localhost;127.*;10.*;172.16.*;192.168.*;<local>',
        )
        winreg.CloseKey(key)
        _notify_proxy_change()
    except OSError as e:
        log.error('Set proxy registry: %s', e)


def _clear_system_proxy():
    if not WINREG_OK:
        return
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Internet Settings',
            0, winreg.KEY_WRITE,
        )
        winreg.SetValueEx(key, 'ProxyEnable', 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        _notify_proxy_change()
    except OSError as e:
        log.error('Clear proxy registry: %s', e)


def _notify_proxy_change():
    try:
        wininet = ctypes.windll.wininet
        wininet.InternetSetOptionW(None, 39, None, 0)  # SETTINGS_CHANGED
        wininet.InternetSetOptionW(None, 37, None, 0)  # REFRESH
    except Exception:
        pass
