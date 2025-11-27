# AgentFleet - Production Dockerfile
# Competition: Agents Intensive Capstone Project 2025
# NOTE: Provided as proof-of-concept for deployment capability (bonus criteria).

FROM python:3.10-slim

LABEL maintainer="rugvedraote@gmail.com"
LABEL description="AgentFleet Self-Healing Robot Fleet System"
LABEL version="1.0.0"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy full project
COPY . .

# Create data directory and move DB
RUN mkdir -p /app/data && \
    touch /app/data/agent_fleet.db

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/app/data/agent_fleet.db

# Non-root user
RUN useradd -m -u 1000 agentfleet && \
    chown -R agentfleet:agentfleet /app
USER agentfleet

# Entry point

CMD ["python", "fleet_orchestrator.py"]
