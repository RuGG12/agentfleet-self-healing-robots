#!/usr/bin/env python3
"""
observability.py
Description: Enterprise Observability Layer for AgentFleet.
             Provides centralized structured logging (JSON), distributed tracing, 
             and operational metrics collection for the Multi-Agent System.

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

# --- Optimization Notes ---
# 1. Structured Logging: Uses a custom JsonFormatter to output logs in JSONL format.
#    This allows for downstream ingestion by tools like Datadog, Splunk, or BigQuery,
#    which is critical for the "Enterprise" track criteria.
# 2. Singleton Pattern: Ensures all agents (Manager, Workers, Orchestrator) write to 
#    the same metrics registry and log file without race conditions in initialization.
# --------------------------

class JsonFormatter(logging.Formatter):
    """
    Custom logging formatter to output events as JSON objects.
    Includes trace_id and span_id for correlation.
    """
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "service": record.name,
            "message": record.getMessage(),
        }
        # Inject tracing context if available
        if hasattr(record, "trace_id"):
            log_record["trace_id"] = record.trace_id
        if hasattr(record, "span_id"):
            log_record["span_id"] = record.span_id
        if hasattr(record, "metadata"):
            log_record.update(record.metadata)
            
        return json.dumps(log_record)


class ObservabilityService:
    """
    Central service for tracking fleet health, metrics, and logs.
    Implemented as a Singleton to be shared across modules.
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
        
        # Operational Metrics Registry
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
        
        # Setup Standard Logger
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        self.logger = logging.getLogger("AgentFleet")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(handler)
        
        # Setup Persistent File Logger (JSON Lines)
        file_handler = logging.FileHandler("fleet_observability.jsonl")
        file_handler.setFormatter(JsonFormatter())
        self.logger.addHandler(file_handler)

    def start_trace(self, trace_id: str = None) -> str:
        """
        Start a new distributed trace for a specific workflow (e.g., a delivery task).
        
        Args:
            trace_id (str, optional): Existing trace ID or None to generate new.
            
        Returns:
            str: The active trace_id.
        """
        self.current_trace_id = trace_id or str(uuid.uuid4())
        return self.current_trace_id

    def log_event(self, service: str, event: str, level: str = "INFO", metadata: Dict[str, Any] = None):
        """
        Log a structured event with metadata.
        
        Args:
            service (str): Name of the component (e.g., 'Manager', 'Orchestrator').
            event (str): Short event name (e.g., 'Task_Completed').
            level (str): Log level.
            metadata (dict): Additional context data.
        """
        extra = {
            "trace_id": self.current_trace_id,
            "span_id": str(uuid.uuid4())[:8],
            "metadata": metadata or {}
        }
        
        # Automatic Metric Updates based on event type
        if event == "Task_Completed":
            self.metrics["tasks_completed"] += 1
        elif event == "Recovery_Triggered":
            self.metrics["recoveries_triggered"] += 1
        elif event == "Recovery_Success":
            self.metrics["recoveries_successful"] += 1

        # Emit Log
        log_entry = logging.LogRecord(
            name=service, level=logging.INFO, pathname="", lineno=0,
            msg=event, args=(), exc_info=None
        )
        log_entry.__dict__.update(extra)
        self.logger.handle(log_entry)

    def track_metric(self, metric_name: str, value: float):
        """
        Manually track a specific metric value.
        """
        if metric_name == "latency":
            self.metrics["api_latency_ms"].append(value)
        elif metric_name in self.metrics:
            self.metrics[metric_name] += value

    def generate_report(self):
        """
        Generate and save an Enterprise Dashboard Summary to disk.
        Useful for post-simulation analysis.
        """
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
        
        # Persist report
        with open("enterprise_dashboard.json", "w") as f:
            json.dump(report, f, indent=2)
            
        return report

# Global Singleton Instance
obs = ObservabilityService()