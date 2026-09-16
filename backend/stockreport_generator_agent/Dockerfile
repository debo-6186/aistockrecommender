FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy project files
COPY stockreport_generator_agent/pyproject.toml ./
COPY stockreport_generator_agent/__init__.py ./
COPY stockreport_generator_agent/__main__.py ./
COPY stockreport_generator_agent/agent.py ./
COPY stockreport_generator_agent/report.py ./
COPY stockreport_generator_agent/logger.py ./
COPY stockreport_generator_agent/agent_executor.py ./
COPY stockreport_generator_agent/limited_context_session_service.py ./

# Shared agent building blocks (model config, session service, schemas)
COPY agent_core/ ./agent_core/

# database.py is shared with host_agent, for the report handoff row
COPY host_agent/database.py ./database.py
COPY host_agent/config.py ./config.py

# Install dependencies using uv
RUN uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install --system -r requirements.txt

EXPOSE 10004

CMD ["python", "__main__.py"]
