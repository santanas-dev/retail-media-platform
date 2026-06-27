"""AV Scanner integration foundation for creative media.

Provides:
- AVScanner abstract interface (CreativeAVScanner)
- ClamAVScanner — ClamAV integration (clamd socket or clamscan subprocess)
- NoScanner — explicit no-scanner placeholder (no fake clean)

Safety:
- Fake AV pass prohibited: scan_status=clean NEVER set without real scanner
- Timeout handling prevents hanging
- All scanner errors → scan_failed (not clean)
- ClamAV absence → not_configured (not clean)
"""

import logging
import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# ── Scanner timeout (seconds) ───────────────────────────────────────────────
SCAN_TIMEOUT = 60  # clamscan can be slow on first run (signature load)


class ScanResult(str, Enum):
    """AV scan result — maps directly to creatives.scan_status."""
    NOT_CONFIGURED = "not_configured"
    PENDING = "pending"
    CLEAN = "clean"
    INFECTED = "infected"
    FAILED = "failed"


@dataclass
class ScanReport:
    """Structured scan report with optional threat details (sanitized)."""
    result: ScanResult
    message: str = ""
    threats: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return self.result == ScanResult.CLEAN

    @property
    def is_infected(self) -> bool:
        return self.result == ScanResult.INFECTED


# ═══════════════════════════════════════════════════════════════════════════
# Abstract interface
# ═══════════════════════════════════════════════════════════════════════════

class AVScanner(ABC):
    """Abstract AV scanner — implement for ClamAV, commercial, or cloud."""

    @abstractmethod
    async def scan(self, content: bytes, filename: str = "file") -> ScanReport:
        """Scan file content and return a structured report.

        Must NOT raise exceptions — return ScanReport with result=FAILED on errors.
        """
        ...

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the scanner is properly configured and available."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable scanner name for audit trail."""
        ...


# ═══════════════════════════════════════════════════════════════════════════
# ClamAV Scanner
# ═══════════════════════════════════════════════════════════════════════════

class ClamAVScanner(AVScanner):
    """ClamAV integration via clamd socket (preferred) or clamscan subprocess.

    Priority:
    1. clamd UNIX socket (/var/run/clamav/clamd.ctl or env CLAMD_SOCKET)
    2. clamscan subprocess (slower, loads signatures each time)

    Requirements (optional):
        sudo apt-get install clamav clamav-daemon
        sudo freshclam           # update signatures
        sudo systemctl start clamav-daemon
    """

    DEFAULT_SOCKET = "/var/run/clamav/clamd.ctl"

    def __init__(self, socket_path: str | None = None):
        self._socket = socket_path or os.environ.get(
            "CLAMD_SOCKET", self.DEFAULT_SOCKET
        )
        self._available = None  # lazy check

    @property
    def name(self) -> str:
        return "ClamAV"

    @property
    def is_configured(self) -> bool:
        if self._available is not None:
            return self._available
        self._available = self._check_available()
        return self._available

    def _check_available(self) -> bool:
        """Check if ClamAV is available via socket or binary."""
        # Check socket
        if os.path.exists(self._socket):
            try:
                sock = self._connect_socket()
                if sock:
                    sock.close()
                    logger.info("ClamAV socket available at %s", self._socket)
                    return True
            except Exception:
                pass

        # Check clamscan binary
        try:
            proc = subprocess.run(
                ["clamscan", "--version"],
                capture_output=True, timeout=5,
            )
            if proc.returncode == 0:
                logger.info("clamscan binary available: %s", proc.stdout.decode().strip())
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        logger.info("ClamAV not available (no socket, no clamscan)")
        return False

    def _connect_socket(self):
        """Connect to clamd UNIX socket."""
        import socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(SCAN_TIMEOUT)
        sock.connect(self._socket)
        return sock

    async def scan(self, content: bytes, filename: str = "file") -> ScanReport:
        """Scan file content with ClamAV.

        Returns ScanReport — NEVER raises exceptions.
        """
        if not content:
            return ScanReport(
                result=ScanResult.FAILED,
                message="Пустой файл — проверка невозможна",
            )

        # Try socket first, fallback to clamscan
        if os.path.exists(self._socket):
            return await self._scan_via_socket(content, filename)
        else:
            return await self._scan_via_subprocess(content, filename)

    async def _scan_via_socket(self, content: bytes, filename: str) -> ScanReport:
        """Scan via clamd socket (INSTREAM command)."""
        import asyncio
        import socket as socket_mod

        try:
            sock = self._connect_socket()
        except Exception as e:
            logger.warning("ClamAV socket connect failed: %s", e)
            # Fallback to subprocess
            return await self._scan_via_subprocess(content, filename)

        try:
            # Send INSTREAM command
            # Format: n SCAN /path\n → n INSTREAM\n → n <size>\r\n<data>\0
            loop = asyncio.get_event_loop()

            # Read banner first
            try:
                banner = await loop.sock_recv(sock, 1024)
            except socket_mod.timeout:
                return ScanReport(
                    result=ScanResult.FAILED,
                    message="Проверка временно недоступна — таймаут сканера",
                )

            # Send INSTREAM
            size = len(content)
            await loop.sock_sendall(sock, b"nINSTREAM\n")
            await loop.sock_sendall(sock, size.to_bytes(4, "big") + content)
            await loop.sock_sendall(sock, b"\x00\x00\x00\x00")  # EOF

            # Read response
            try:
                response = await loop.sock_recv(sock, 4096)
                response_str = response.decode("utf-8", errors="replace").strip()
            except socket_mod.timeout:
                return ScanReport(
                    result=ScanResult.FAILED,
                    message="Проверка временно недоступна — таймаут сканера",
                )

            # Parse response
            if response_str.endswith("OK"):
                return ScanReport(result=ScanResult.CLEAN, message="Файл проверен")
            elif "FOUND" in response_str:
                threat = response_str.split("FOUND")[0].split(":")[-1].strip()
                return ScanReport(
                    result=ScanResult.INFECTED,
                    message="Найдена угроза",
                    threats=[threat],
                )
            elif "ERROR" in response_str:
                return ScanReport(
                    result=ScanResult.FAILED,
                    message=f"Ошибка проверки: {response_str[:200]}",
                )
            else:
                return ScanReport(
                    result=ScanResult.FAILED,
                    message=f"Неожиданный ответ сканера: {response_str[:200]}",
                )

        except Exception as e:
            logger.exception("ClamAV socket scan error")
            return ScanReport(
                result=ScanResult.FAILED,
                message=f"Ошибка проверки: {str(e)[:100]}",
            )
        finally:
            try:
                sock.close()
            except Exception:
                pass

    async def _scan_via_subprocess(self, content: bytes, filename: str) -> ScanReport:
        """Scan via clamscan subprocess."""
        import asyncio

        # Write content to temp file (clamscan requires a path)
        tmp = None
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}")
            tmp.write(content)
            tmp.flush()
            tmp.close()

            proc = await asyncio.create_subprocess_exec(
                "clamscan",
                "--no-summary",
                "--infected",
                "--quiet",
                tmp.name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=SCAN_TIMEOUT
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ScanReport(
                    result=ScanResult.FAILED,
                    message="Проверка временно недоступна — таймаут сканера",
                )

            if proc.returncode == 0:
                return ScanReport(result=ScanResult.CLEAN, message="Файл проверен")
            elif proc.returncode == 1:
                # Virus found — parse threat names
                lines = stdout.decode("utf-8", errors="replace").strip().split("\n")
                threats = []
                for line in lines:
                    if ":" in line and "FOUND" in line:
                        threats.append(line.split("FOUND")[0].strip())
                return ScanReport(
                    result=ScanResult.INFECTED,
                    message="Найдена угроза",
                    threats=threats,
                )
            else:
                return ScanReport(
                    result=ScanResult.FAILED,
                    message=f"Ошибка проверки (код {proc.returncode}): "
                           f"{stderr.decode('utf-8', errors='replace')[:200]}",
                )

        except FileNotFoundError:
            return ScanReport(
                result=ScanResult.NOT_CONFIGURED,
                message="Антивирус не установлен",
            )
        except Exception as e:
            logger.exception("clamscan error")
            return ScanReport(
                result=ScanResult.FAILED,
                message=f"Ошибка проверки: {str(e)[:100]}",
            )
        finally:
            if tmp and os.path.exists(tmp.name):
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass


# ═══════════════════════════════════════════════════════════════════════════
# No-op scanner (explicit placeholder — no fake clean)
# ═══════════════════════════════════════════════════════════════════════════

class NoScanner(AVScanner):
    """Explicit no-scanner placeholder.

    Returns NOT_CONFIGURED for every scan. NEVER returns CLEAN — no fake pass.
    """

    @property
    def is_configured(self) -> bool:
        return False

    @property
    def name(self) -> str:
        return "none"

    async def scan(self, content: bytes, filename: str = "file") -> ScanReport:
        return ScanReport(
            result=ScanResult.NOT_CONFIGURED,
            message="Проверка безопасности не настроена",
        )


# ═══════════════════════════════════════════════════════════════════════════
# Factory — creates the best available scanner
# ═══════════════════════════════════════════════════════════════════════════

def create_av_scanner() -> AVScanner:
    """Create the best available AV scanner.

    Priority:
    1. ClamAV (if installed and configured)
    2. NoScanner (explicit placeholder, no fake clean)
    """
    scanner = ClamAVScanner()
    if scanner.is_configured:
        logger.info("AV scanner: ClamAV (configured)")
        return scanner
    logger.info("AV scanner: not configured (NoScanner)")
    return NoScanner()
