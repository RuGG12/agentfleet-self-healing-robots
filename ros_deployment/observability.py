#!/usr/bin/env python3
"""
observability.py
Description: Enterprise Observability Layer.
             Handles structured logging, distributed tracing simulation,
             and metrics collection for the fleet.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

import json
import time
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

# --- Configuration ---
LOG_FILE = "fleet_observability.jsonl"
DASHBOARD_FILE = "enterprise_dashboard.json"

class JsonFormatter(logging.Formatter):
    """Custom formatter to output logs in JSON lines format."""
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "service": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "trace_id"):
            log_record["trace_id"] = record.trace_id
        if hasattr(record, "span_id"):
            log_record["span_id"] = record.span_id
        if hasattr(record, "metadata"):
            log_record.update(record.metadata)
        return json.dumps(log_record)


class ObservabilityService:
    """
    Singleton service for tracking metrics and logs.
    Acts as a central monitoring hub for the distributed agent system.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ObservabilityService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.metrics = {
            "tasks_assigned": 0,
            "tasks_completed": 0,
            "recoveries_triggered": 0,
            "recoveries_successful": 0,
            "token_usage_simulated": 0,
            "api_latency_ms": []
        }
        self.logs = []
        self.current_trace_id = None
        
        # Setup Logger
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        self.logger = logging.getLogger("AgentFleet")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(handler)
        
        # File handler for persistent logs
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(JsonFormatter())
        self.logger.addHandler(file_handler)
        
        print(f"✓ Observability initialized. Logs -> {LOG_FILE}")

    def start_trace(self, trace_id: str = None) -> str:
        """Start a new trace for a workflow (e.g., a delivery task)."""
        self.current_trace_id = trace_id or str(uuid.uuid4())
        return self.current_trace_id

    def log_event(self, service: str, event: str, level: str = "INFO", metadata: Dict[str, Any] = None):
        """Log a structured event."""
        extra = {
            "trace_id": self.current_trace_id,
            "span_id": str(uuid.uuid4())[:8],
            "metadata": metadata or {}
        }
        
        # Update internal metrics based on events
        if event == "Task_Completed":
            self.metrics["tasks_completed"] += 1
        elif event == "Recovery_Triggered":
            self.metrics["recoveries_triggered"] += 1
        elif event == "Recovery_Success":
            self.metrics["recoveries_successful"] += 1

        # Actually log
        log_entry = logging.LogRecord(
            name=service, level=logging.INFO, pathname="", lineno=0,
            msg=event, args=(), exc_info=None
        )
        log_entry.__dict__.update(extra)
        self.logger.handle(log_entry)

    def track_metric(self, metric_name: str, value: float):
        """Track a specific metric."""
        if metric_name == "latency":
            self.metrics["api_latency_ms"].append(value)
        elif metric_name in self.metrics:
            self.metrics[metric_name] += value

    def generate_report(self):
        """Generate an Enterprise Dashboard Summary."""
        avg_latency = 0
        if self.metrics["api_latency_ms"]:
            avg_latency = sum(self.metrics["api_latency_ms"]) / len(self.metrics["api_latency_ms"])
            
        report = {
            "status": "HEALTHY" if self.metrics.get("tasks_failed", 0) == 0 else "DEGRADED",
            "uptime": time.time(),
            "metrics": self.metrics,
            "performance": {
                "avg_latency_ms": round(avg_latency, 2),
                "throughput": f"{self.metrics['tasks_completed']} tasks/session"
            }
        }
        
        # Save to disk
        with open(DASHBOARD_FILE, "w") as f:
            json.dump(report, f, indent=2)
            
        return report

# Global instance
obs = ObservabilityService()
