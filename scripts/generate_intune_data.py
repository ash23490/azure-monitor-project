#!/usr/bin/env python3
"""
generate_intune_data_modern.py
Production-ready synthetic Intune compliance data generator using the
Azure Monitor Logs Ingestion API (DCR-based) with OAuth authentication.

Architecture:
    Python → DefaultAzureCredential → OAuth Bearer Token
         → DCE / DCR → Logs Ingestion API → Log Analytics custom table

This replaces the deprecated HTTP Data Collector API (end of support: Sept 2026).
"""

import json
import os
import sys
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Azure Identity is required for modern OAuth-based ingestion
try:
    from azure.identity import DefaultAzureCredential
except ImportError as _import_err:
    raise ImportError(
        "The azure-identity package is required. "
        "Install it: pip install azure-identity"
    ) from _import_err


# ============================================================================
# CONFIGURATION — validated at startup, zero hardcoded secrets
# ============================================================================

class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass


class Config:
    """
    Centralized configuration loaded exclusively from environment variables.
    No hardcoded credentials. No workspace keys.
    """

    # Data generation
    LOG_TYPE: str = os.getenv("LA_LOG_TYPE", "IntuneCompliance")
    DAYS: int = int(os.getenv("GENERATOR_DAYS", "30"))
    RANDOM_SEED: Optional[int] = (
        int(s) if (s := os.getenv("RANDOM_SEED")) else None
    )

    # Azure Monitor Logs Ingestion API (modern)
    DCE_URI: Optional[str] = os.getenv("AZURE_DCE_URI")
    DCR_IMMUTABLE_ID: Optional[str] = os.getenv("AZURE_DCR_IMMUTABLE_ID")
    STREAM_NAME: str = os.getenv(
        "AZURE_DCR_STREAM_NAME",
        f"Custom-{os.getenv('LA_LOG_TYPE', 'IntuneCompliance')}"
    )

    # Transport / resilience
    CHUNK_SIZE: int = int(os.getenv("LA_CHUNK_SIZE", "1000"))
    REQUEST_TIMEOUT: int = int(os.getenv("LA_TIMEOUT", "30"))
    MAX_RETRIES: int = int(os.getenv("LA_MAX_RETRIES", "3"))
    BACKOFF_FACTOR: float = float(os.getenv("LA_BACKOFF_FACTOR", "1.0"))

    @classmethod
    def validate(cls) -> None:
        """
        Validate that all required settings for the modern API are present.
        Raises ConfigError with actionable guidance if anything is missing.
        """
        missing = []

        if not cls.DCE_URI:
            missing.append("AZURE_DCE_URI")
        if not cls.DCR_IMMUTABLE_ID:
            missing.append("AZURE_DCR_IMMUTABLE_ID")

        if missing:
            raise ConfigError(
                f"Missing required environment variables: {', '.join(missing)}\n\n"
                "You are using the modern Logs Ingestion API. "
                "Prerequisites in Azure:\n"
                "  1. Create a Data Collection Endpoint (DCE)\n"
                "  2. Create a Data Collection Rule (DCR) targeting your Log Analytics workspace\n"
                "  3. Grant your identity 'Monitoring Metrics Publisher' role on the DCR\n\n"
                "Then set:\n"
                f"  export AZURE_DCE_URI='https://my-dce.region.ingest.monitor.azure.com'\n"
                f"  export AZURE_DCR_IMMUTABLE_ID='dcr-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'\n"
                f"  export AZURE_DCR_STREAM_NAME='Custom-{cls.LOG_TYPE}'  # optional, defaults to Custom-{cls.LOG_TYPE}\n\n"
                "Authentication uses DefaultAzureCredential (az login, Managed Identity, "
                "or service principal env vars)."
            )


# ============================================================================
# STRUCTURED LOGGING
# ============================================================================

def setup_logging() -> logging.Logger:
    """Structured logging for security auditing and operational visibility."""
    logger = logging.getLogger("IntuneDataGenerator")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logging()


# ============================================================================
# DATA MODELS
# ============================================================================

class ComplianceStatus(str, Enum):
    COMPLIANT = "Compliant"
    NON_COMPLIANT = "NonCompliant"


@dataclass(frozen=True)
class Device:
    """Immutable device record with lightweight validation."""
    name: str
    user: str
    department: str
    os: str

    def __post_init__(self):
        for field, value in self.__dict__.items():
            if not value or not isinstance(value, str):
                raise ValueError(f"Device.{field} must be a non-empty string")
            if len(value) > 128:
                raise ValueError(f"Device.{field} exceeds 128 characters")


@dataclass
class ComplianceRecord:
    """Schema-aligned record for Log Analytics ingestion."""
    Date: str
    DeviceName: str
    UserName: str
    Department: str
    OperatingSystem: str
    PolicyName: str
    ComplianceStatus: str
    IsCompliant: bool
    IsComplianceDrift: bool
    ResourceGroup: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# DATA DEFINITIONS
# ============================================================================

DEVICES: List[Device] = [
    Device("DESKTOP-HR-001",    "john.smith",    "HR",         "Windows 11"),
    Device("DESKTOP-HR-002",    "jane.doe",      "HR",         "Windows 11"),
    Device("LAPTOP-FIN-001",    "bob.finance",   "Finance",    "Windows 11"),
    Device("LAPTOP-FIN-002",    "alice.budget",  "Finance",    "Windows 10"),
    Device("DESKTOP-IT-001",    "admin.it",      "IT",         "Windows 11"),
    Device("LAPTOP-IT-002",     "sarah.cloud",   "IT",         "Windows 11"),
    Device("DESKTOP-SALES-001", "mike.sales",    "Sales",      "Windows 10"),
    Device("LAPTOP-SALES-002",  "lisa.revenue",  "Sales",      "Windows 11"),
    Device("DESKTOP-OPS-001",   "tom.ops",       "Operations", "Windows 11"),
    Device("LAPTOP-OPS-002",    "emma.ops",      "Operations", "Windows 10"),
]

POLICIES: List[str] = [
    "BitLocker Encryption",
    "Windows Defender Antivirus",
    "OS Version Compliance",
    "Password Policy",
    "Firewall Enabled",
]


# ============================================================================
# AZURE LOGS INGESTION API CLIENT (Modern)
# ============================================================================

class LogsIngestionClient:
    """
    Client for Azure Monitor Logs Ingestion API using OAuth 2.0.
    Replaces the legacy Data Collector API (SharedKey auth).
    """

    def __init__(
        self,
        dce_uri: str,
        dcr_immutable_id: str,
        stream_name: str
    ):
        self.dce_uri = dce_uri.rstrip("/")
        self.dcr_immutable_id = dcr_immutable_id
        self.stream_name = stream_name

        self.ingestion_uri = (
            f"{self.dce_uri}/dataCollectionRules/"
            f"{self.dcr_immutable_id}/streams/{self.stream_name}"
            f"?api-version=2023-01-01"
        )

        self.credential = DefaultAzureCredential()
        self.session = requests.Session()

        # Configure retries ONLY for safe, idempotent methods.
        # POST is intentionally excluded from automatic retry because it is
        # not idempotent — a retried POST can result in duplicate records.
        # We handle POST retries manually with explicit logging.
        safe_retry = Retry(
            total=3,
            backoff_factor=1.0,
            allowed_methods=frozenset({"GET", "HEAD", "OPTIONS"})
        )
        adapter = HTTPAdapter(max_retries=safe_retry, pool_connections=5, pool_maxsize=10)
        self.session.mount("https://", adapter)

    def _get_token(self) -> str:
        """Acquire an OAuth token scoped for Azure Monitor data ingestion."""
        # Scope: https://monitor.azure.com/.default is required for DCE ingestion
        token = self.credential.get_token("https://monitor.azure.com/.default")
        return token.token

    def send_chunk(self, records: List[Dict[str, Any]]) -> int:
        """
        Send a single chunk of records to the Logs Ingestion API.
        Implements manual retry with exponential backoff for transient errors.

        WARNING: POST is not idempotent. Retrying a partially-successful
        request may create duplicates. This is acceptable for synthetic/test
        data, but production pipelines should implement idempotency keys
        or exactly-once delivery semantics.
        """
        body = json.dumps(records, separators=(",", ":"))
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

        max_attempts = Config.MAX_RETRIES
        backoff = Config.BACKOFF_FACTOR

        for attempt in range(1, max_attempts + 1):
            try:
                response = self.session.post(
                    self.ingestion_uri,
                    data=body,
                    headers=headers,
                    timeout=Config.REQUEST_TIMEOUT
                )
                response.raise_for_status()
                return response.status_code

            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response else 0
                # Retry on rate-limit or server errors
                if status in (429, 500, 502, 503, 504) and attempt < max_attempts:
                    wait = backoff * (2 ** (attempt - 1))
                    logger.warning(
                        f"Ingestion attempt {attempt}/{max_attempts} failed "
                        f"(HTTP {status}). Retrying in {wait:.1f}s..."
                    )
                    time.sleep(wait)
                    # Refresh token before retry in case of expiry
                    headers["Authorization"] = f"Bearer {self._get_token()}"
                    continue

                logger.error(
                    f"Ingestion failed after {attempt} attempt(s): "
                    f"HTTP {status} — {e.response.text[:500] if e.response else 'No response'}"
                )
                raise

            except requests.exceptions.RequestException as e:
                if attempt < max_attempts:
                    wait = backoff * (2 ** (attempt - 1))
                    logger.warning(
                        f"Network error on attempt {attempt}: {e}. "
                        f"Retrying in {wait:.1f}s..."
                    )
                    time.sleep(wait)
                    headers["Authorization"] = f"Bearer {self._get_token()}"
                    continue
                logger.error(f"Network failure after {max_attempts} attempts: {e}")
                raise

    def send_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Chunk and send all records with progress tracking.
        Returns a summary dictionary.
        """
        total = len(records)
        if total == 0:
            logger.warning("No records to ingest.")
            return {"total": 0, "chunks": 0, "success": True}

        chunks = [
            records[i : i + Config.CHUNK_SIZE]
            for i in range(0, total, Config.CHUNK_SIZE)
        ]

        logger.info(
            f"Starting ingestion: {total} records across {len(chunks)} chunk(s) "
            f"(max {Config.CHUNK_SIZE} per chunk)"
        )

        success_count = 0
        failed_chunks = 0

        for idx, chunk in enumerate(chunks, 1):
            try:
                status = self.send_chunk(chunk)
                success_count += len(chunk)
                logger.info(f"Chunk {idx}/{len(chunks)} ingested (HTTP {status})")

                # Brief pause between chunks to avoid rate limiting
                if idx < len(chunks):
                    time.sleep(0.5)

            except Exception as e:
                failed_chunks += 1
                logger.error(f"Chunk {idx}/{len(chunks)} failed: {e}")
                # Continue with remaining chunks to maximize data delivery

        summary = {
            "total": total,
            "chunks": len(chunks),
            "successful_records": success_count,
            "failed_chunks": failed_chunks,
            "success": failed_chunks == 0,
        }

        logger.info(f"Ingestion summary: {summary}")
        return summary


# ============================================================================
# SYNTHETIC DATA GENERATION (Reproducible)
# ============================================================================

def generate_compliance_data(days: int, seed: Optional[int] = None) -> List[ComplianceRecord]:
    """
    Generate synthetic compliance data using a seeded pseudo-random generator
    for reproducible test datasets.
    """
    logger.info(f"Generating {days} days of Intune compliance data (seed={seed})...")

    rng = random.Random(seed) if seed is not None else random.Random()
    records: List[ComplianceRecord] = []
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    resource_group = "azure-monitor-project"

    for day in range(days):
        current_date = start_date + timedelta(days=day)
        date_str = current_date.strftime("%Y-%m-%d")

        for device in DEVICES:
            for policy in POLICIES:
                # Scenario: compliance drift on day 20 for Sales department
                if day == 20 and device.department == "Sales":
                    is_compliant = False
                    status = ComplianceStatus.NON_COMPLIANT
                    is_drift = True

                # Scenario: random non-compliance for Windows 10 devices (~10%)
                elif device.os == "Windows 10" and rng.randint(1, 10) == 1:
                    is_compliant = False
                    status = ComplianceStatus.NON_COMPLIANT
                    is_drift = False

                else:
                    is_compliant = True
                    status = ComplianceStatus.COMPLIANT
                    is_drift = False

                records.append(ComplianceRecord(
                    Date=date_str,
                    DeviceName=device.name,
                    UserName=device.user,
                    Department=device.department,
                    OperatingSystem=device.os,
                    PolicyName=policy,
                    ComplianceStatus=status.value,
                    IsCompliant=is_compliant,
                    IsComplianceDrift=is_drift,
                    ResourceGroup=resource_group,
                ))

    logger.info(f"Generated {len(records)} records")
    return records


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:
    """Entry point with comprehensive error handling and audit logging."""
    start_time = time.time()

    try:
        # 1. Validate configuration
        Config.validate()

        # 2. Generate reproducible synthetic data
        records = generate_compliance_data(Config.DAYS, Config.RANDOM_SEED)
        record_dicts = [r.to_dict() for r in records]

        # 3. Ingest via modern Logs Ingestion API
        client = LogsIngestionClient(
            dce_uri=Config.DCE_URI,
            dcr_immutable_id=Config.DCR_IMMUTABLE_ID,
            stream_name=Config.STREAM_NAME,
        )
        summary = client.send_records(record_dicts)

        # 4. Audit log
        elapsed = time.time() - start_time
        logger.info(
            f"Execution completed in {elapsed:.2f}s | "
            f"Records: {summary['successful_records']}/{summary['total']} | "
            f"Success: {summary['success']}"
        )

        return 0 if summary["success"] else 1

    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        return 2
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())