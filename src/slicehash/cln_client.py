"""Core Lightning REST API client (clnrest plugin).

Wraps the CLN REST API for invoice creation and payment monitoring.
Authentication uses rune-based auth via the 'Rune' header.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)


@dataclass
class InvoiceResult:
    """Result from creating a CLN invoice."""

    bolt11: str
    payment_hash: str
    expires_at: datetime


@dataclass
class InvoiceStatus:
    """Current status of a CLN invoice."""

    status: str  # "unpaid", "paid", or "expired"
    paid_at: datetime | None = None
    amount_received_msat: int | None = None


class CLNClient:
    """Async client for Core Lightning's clnrest REST API.

    Args:
        base_url: Base URL of the clnrest server (e.g. "https://127.0.0.1:3010")
        rune: CLN rune for authentication (from `lightning-cli createrune`)
        ca_cert: Path to CLN's CA certificate file for TLS verification.
                 Pass None to disable TLS verification (only for localhost).
    """

    def __init__(self, base_url: str, rune: str, ca_cert: str | None = None):
        self._base_url = base_url.rstrip("/")
        self._rune = rune
        self._ca_cert: str | bool = ca_cert if ca_cert else False

    def _make_client(self, timeout: float | None = 30.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Rune": self._rune, "Content-Type": "application/json"},
            verify=self._ca_cert,
            timeout=timeout,
        )

    async def create_invoice(
        self,
        amount_msat: int,
        label: str,
        description: str,
        expiry: int = 600,
    ) -> InvoiceResult:
        """Create a new Lightning invoice.

        Args:
            amount_msat: Invoice amount in millisatoshis
            label: Unique label for this invoice (used for waitinvoice)
            description: Human-readable description shown to payer
            expiry: Invoice expiry in seconds (default 10 minutes)

        Returns:
            InvoiceResult with bolt11 string, payment_hash, and expires_at

        Raises:
            httpx.HTTPStatusError: If CLN returns an error
        """
        async with self._make_client() as client:
            resp = await client.post(
                "/v1/invoice",
                json={
                    "amount_msat": amount_msat,
                    "label": label,
                    "description": description,
                    "expiry": expiry,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            return InvoiceResult(
                bolt11=data["bolt11"],
                payment_hash=data["payment_hash"],
                expires_at=datetime.fromtimestamp(
                    data["expires_at"], tz=timezone.utc
                ),
            )

    async def wait_invoice(self, label: str, timeout: float = 720.0) -> InvoiceStatus:
        """Block until a specific invoice is paid or expires.

        CLN's waitinvoice endpoint blocks until the invoice transitions from
        "unpaid" to "paid" or "expired". The timeout should exceed the invoice
        expiry time (default 600s expiry + 120s buffer = 720s).

        Args:
            label: Invoice label as passed to create_invoice
            timeout: HTTP request timeout in seconds

        Returns:
            InvoiceStatus with status "paid" or "expired"

        Raises:
            httpx.HTTPStatusError: If CLN returns an unexpected error
            httpx.TimeoutException: If request exceeds timeout
        """
        async with self._make_client(timeout=timeout) as client:
            resp = await client.post("/v1/waitinvoice", json={"label": label})
            resp.raise_for_status()
            data = resp.json()

        status = data.get("status", "expired")
        paid_at = None
        amount_received_msat = None

        if status == "paid":
            paid_at_ts = data.get("paid_at")
            if paid_at_ts:
                paid_at = datetime.fromtimestamp(paid_at_ts, tz=timezone.utc)
            amount_received_msat = data.get("amount_received_msat")

        return InvoiceStatus(
            status=status,
            paid_at=paid_at,
            amount_received_msat=amount_received_msat,
        )

    async def get_invoice_status(self, payment_hash: str) -> InvoiceStatus | None:
        """Look up current invoice status by payment hash.

        Used during startup recovery to check invoices that were pending
        when the app last shut down.

        Args:
            payment_hash: 64-character hex payment hash

        Returns:
            InvoiceStatus or None if invoice not found
        """
        async with self._make_client() as client:
            resp = await client.post(
                "/v1/listinvoices",
                json={"payment_hash": payment_hash},
            )
            resp.raise_for_status()
            data = resp.json()

        invoices = data.get("invoices", [])
        if not invoices:
            return None

        invoice = invoices[0]
        status = invoice.get("status", "unknown")
        paid_at = None
        amount_received_msat = None

        if status == "paid":
            paid_at_ts = invoice.get("paid_at")
            if paid_at_ts:
                paid_at = datetime.fromtimestamp(paid_at_ts, tz=timezone.utc)
            amount_received_msat = invoice.get("amount_received_msat")

        return InvoiceStatus(
            status=status,
            paid_at=paid_at,
            amount_received_msat=amount_received_msat,
        )
