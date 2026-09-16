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
COPY document_analyser_agent/pyproject.toml ./
COPY document_analyser_agent/__init__.py ./
COPY document_analyser_agent/__main__.py ./
COPY document_analyser_agent/agent.py ./
COPY document_analyser_agent/doc_types.py ./
COPY document_analyser_agent/reader.py ./
COPY document_analyser_agent/agent_executor.py ./
COPY document_analyser_agent/limited_context_session_service.py ./

# Shared agent building blocks (model config, session service, schemas)
COPY agent_core/ ./agent_core/

# database.py is shared with host_agent and used to track uploads
COPY host_agent/database.py ./database.py
COPY host_agent/config.py ./config.py

# Install dependencies using uv
RUN uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install --system -r requirements.txt

# Expose the default A2A port
EXPOSE 10003

# Start the agent
CMD ["python", "__main__.py"]
