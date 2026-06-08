"""
Asset Blocker — hosts-file redirect + local HTTPS server.

Flow:
  1. Resolve real IP of assetdelivery.roblox.com  (before touching DNS)
  2. Write  127.0.0.1  assetdelivery.roblox.com  to the hosts file
  3. Start a local TLS server on 127.0.0.1:443 presenting our fake cert
  4. Roblox connects thinking it's the real CDN
  5. Blocked ID → 404.  Not blocked → forward to the real IP directly.

Requires administrator rights (port 443 + hosts file write).
"""

import ctypes
import datetime
import logging
import os
import re
import socket
import ssl
import subprocess
import threading
from pathlib import Path

try:
    import winreg
    _WINREG = True
except ImportError:
    _WINREG = False

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    CRYPTO_OK = True
except ImportError:
    CRYPTO_OK = False

INTERCEPT_HOST = 'assetdelivery.roblox.com'
SERVER_ADDR    = '127.0.0.1'
SERVER_PORT    = 443
PROXY_PORT     = SERVER_PORT          # kept so ui.py can import it

HOSTS_PATH  = Path(r'C:\Windows\System32\drivers\etc\hosts')
HOSTS_MARK  = '# ZeroTrace'
CERTS_DIR   = Path(os.environ.get('APPDATA', '.')) / 'ZeroTrace' / 'certs'

log = logging.getLogger('zerotrace.proxy')


# ─── Admin check ─────────────────────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ─── Hosts file ──────────────────────────────────────────────────────────────

class HostsManager:
    def add(self, host: str) -> bool:
        try:
            text = HOSTS_PATH.read_text(encoding='utf-8', errors='replace')
            if f'{host} {HOSTS_MARK}' in text:
                return True
            # Remove any existing line for this host (without our marker)
            clean = '\n'.join(
                ln for ln in text.splitlines()
                if host not in ln.split() or HOSTS_MARK in ln
            )
            entry = f'\n127.0.0.1 {host} {HOSTS_MARK}\n'
            HOSTS_PATH.write_text(clean.rstrip('\n') + entry, encoding='utf-8')
            self._flush()
            return True
        except PermissionError:
            return False
        except Exception as e:
            log.error('hosts add: %s', e)
            return False

    def remove(self, host: str) -> None:
        try:
            lines = HOSTS_PATH.read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)
            kept = [ln for ln in lines if not (host in ln and HOSTS_MARK in ln)]
            HOSTS_PATH.write_text(''.join(kept), encoding='utf-8')
            self._flush()
        except Exception as e:
            log.error('hosts remove: %s', e)

    def is_active(self, host: str) -> bool:
        try:
            txt = HOSTS_PATH.read_text(encoding='utf-8', errors='replace')
            return host in txt and HOSTS_MARK in txt
        except Exception:
            return False

    @staticmethod
    def _flush():
        subprocess.run(
            ['ipconfig', '/flushdns'],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )


# ─── Certificate manager ─────────────────────────────────────────────────────

class CertManager:
    CA_CN = 'ZeroTrace Asset Blocker CA'

    def __init__(self):
        CERTS_DIR.mkdir(parents=True, exist_ok=True)
        self._ca_key_path  = CERTS_DIR / 'ca.key'
        self._ca_cert_path = CERTS_DIR / 'ca.crt'
        self.ca_key  = None
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
        key  = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME,          self.CA_CN),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME,    'ZeroTrace'),
        ])
        now  = datetime.datetime.utcnow()
        cert = (
            x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ), critical=True)
            .sign(key, hashes.SHA256())
        )
        with open(self._ca_key_path, 'wb') as f:
            f.write(key.private_bytes(serialization.Encoding.PEM,
                                       serialization.PrivateFormat.TraditionalOpenSSL,
                                       serialization.NoEncryption()))
        with open(self._ca_cert_path, 'wb') as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        self.ca_key  = key
        self.ca_cert = cert

    def host_cert(self, hostname: str) -> tuple[str, str]:
        safe = hostname.replace('.', '_')
        crt  = CERTS_DIR / f'{safe}.crt'
        key  = CERTS_DIR / f'{safe}.key'
        if not crt.exists():
            k    = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
            now  = datetime.datetime.utcnow()
            c    = (
                x509.CertificateBuilder()
                .subject_name(name).issuer_name(self.ca_cert.subject)
                .public_key(k.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now)
                .not_valid_after(now + datetime.timedelta(days=825))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
                .sign(self.ca_key, hashes.SHA256())
            )
            with open(key, 'wb') as f:
                f.write(k.private_bytes(serialization.Encoding.PEM,
                                         serialization.PrivateFormat.TraditionalOpenSSL,
                                         serialization.NoEncryption()))
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


# ─── Helpers ─────────────────────────────────────────────────────────────────

_ID_PATTERNS = [
    re.compile(r'[?&]id=(\d+)',       re.IGNORECASE),
    re.compile(r'/assetId/(\d+)',     re.IGNORECASE),
    re.compile(r'/(\d{6,})(?:[/?]|$)'),
]


def _extract_asset_id(path: str) -> str | None:
    for p in _ID_PATTERNS:
        m = p.search(path)
        if m:
            return m.group(1)
    return None


def _recv_header(sock, timeout: float = 30.0) -> bytes:
    """Read HTTP headers (until \\r\\n\\r\\n)."""
    sock.settimeout(timeout)
    buf = b''
    while b'\r\n\r\n' not in buf:
        try:
            chunk = sock.recv(4096)
        except (socket.timeout, OSError):
            break
        if not chunk:
            break
        buf += chunk
        if len(buf) > 65536:
            break
    return buf


def _close(sock) -> None:
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


def _pipe(src, dst, ev: threading.Event) -> None:
    try:
        while not ev.is_set():
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
        ev.set()


def _bidir_pipe(a, b) -> None:
    ev = threading.Event()
    threading.Thread(target=_pipe, args=(a, b, ev), daemon=True).start()
    threading.Thread(target=_pipe, args=(b, a, ev), daemon=True).start()
    ev.wait()


# ─── Per-connection handler ───────────────────────────────────────────────────

class _Conn(threading.Thread):
    """Handles one incoming TLS connection from Roblox."""

    def __init__(
        self,
        raw_client: socket.socket,
        ssl_ctx:    ssl.SSLContext,
        real_ip:    str,
        blocked:    set[str],
    ):
        super().__init__(daemon=True)
        self._raw     = raw_client
        self._ctx     = ssl_ctx
        self._real_ip = real_ip
        self._blocked = blocked

    def run(self):
        try:
            self._process()
        except Exception as e:
            log.debug('Conn error: %s', e)
        finally:
            _close(self._raw)

    def _process(self):
        try:
            client = self._ctx.wrap_socket(self._raw, server_side=True)
        except ssl.SSLError as e:
            log.debug('TLS handshake failed: %s', e)
            return

        try:
            headers = _recv_header(client)
            if not headers:
                return

            first = headers.split(b'\r\n', 1)[0].decode('latin-1', errors='replace')
            parts = first.split(' ')
            path  = parts[1] if len(parts) >= 2 else '/'

            asset_id = _extract_asset_id(path)
            if asset_id and asset_id in self._blocked:
                log.info('Blocked asset %s', asset_id)
                client.sendall(
                    b'HTTP/1.1 404 Not Found\r\n'
                    b'Content-Length: 0\r\n'
                    b'Connection: close\r\n\r\n'
                )
                return

            # Forward to real server (bypassing our hosts entry via direct IP)
            try:
                raw_srv = socket.create_connection((self._real_ip, 443), timeout=15)
                ctx_fwd = ssl.create_default_context()
                srv     = ctx_fwd.wrap_socket(raw_srv, server_hostname=INTERCEPT_HOST)
            except OSError as e:
                log.error('Cannot reach real server %s: %s', self._real_ip, e)
                client.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n')
                return

            try:
                srv.sendall(headers)          # replay the buffered request
                _bidir_pipe(client, srv)      # stream everything else
            finally:
                _close(srv)
        finally:
            try:
                client.close()
            except OSError:
                pass


# ─── Main proxy class ─────────────────────────────────────────────────────────

class AssetBlockerProxy:
    def __init__(self):
        self._blocked:  set[str]              = set()
        self._certs:    CertManager           = CertManager()
        self._hosts:    HostsManager          = HostsManager()
        self._server:   socket.socket | None  = None
        self._thread:   threading.Thread | None = None
        self._ssl_ctx:  ssl.SSLContext | None  = None
        self._real_ip:  str                   = ''
        self._running:  bool                  = False

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._running

    @property
    def crypto_available(self) -> bool:
        return CRYPTO_OK

    def set_blocked(self, asset_ids: list) -> None:
        self._blocked = {str(a) for a in asset_ids}

    def start(self) -> tuple[bool, str]:
        """Returns (ok, error_message)."""
        if self._running:
            return True, ''

        if not CRYPTO_OK:
            return False, 'cryptography package not installed.'

        if not self._certs.ca_key:
            return False, 'CA certificate not generated.'

        if not is_admin():
            return False, 'Administrator rights required.'

        # Resolve real IP before poisoning DNS
        try:
            self._real_ip = socket.getaddrinfo(INTERCEPT_HOST, 443,
                                               proto=socket.IPPROTO_TCP)[0][4][0]
            log.info('Resolved %s → %s', INTERCEPT_HOST, self._real_ip)
        except OSError as e:
            return False, f'DNS resolution failed: {e}'

        # Build SSL context for our server
        try:
            crt, key    = self._certs.host_cert(INTERCEPT_HOST)
            ctx         = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(crt, key)
            self._ssl_ctx = ctx
        except Exception as e:
            return False, f'SSL context error: {e}'

        # Bind to port 443
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((SERVER_ADDR, SERVER_PORT))
            srv.listen(100)
            self._server = srv
        except OSError as e:
            return False, f'Cannot bind to port 443: {e}'

        # Modify hosts file
        if not self._hosts.add(INTERCEPT_HOST):
            self._server.close()
            return False, 'Could not modify hosts file (need admin).'

        self._running = True
        self._thread  = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        log.info('Asset Blocker active on %s:%d', SERVER_ADDR, SERVER_PORT)
        return True, ''

    def stop(self) -> None:
        self._running = False
        self._hosts.remove(INTERCEPT_HOST)
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        log.info('Asset Blocker stopped.')

    def ca_installed(self) -> bool:
        return self._certs.is_installed()

    def install_ca(self) -> bool:
        return self._certs.install()

    def uninstall_ca(self) -> bool:
        return self._certs.uninstall()

    # ── Internal ──────────────────────────────────────────────────────────

    def _accept_loop(self):
        self._server.settimeout(1.0)
        while self._running:
            try:
                raw, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            _Conn(raw, self._ssl_ctx, self._real_ip, self._blocked).start()
