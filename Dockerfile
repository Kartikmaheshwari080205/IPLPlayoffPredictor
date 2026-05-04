# Multi-stage build to keep image size minimal
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools for C++
RUN apt-get update && apt-get install -y \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy C++ source files
COPY predictor.cpp temp.cpp ./

# Compile C++ binaries
RUN g++ -std=c++17 -O2 predictor.cpp -o predictor && \
    g++ -std=c++17 -O2 temp.cpp -o temp

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy compiled binaries from builder
COPY --from=builder /app/predictor /app/temp /app/

# Copy Python scripts
COPY api_server.py nightly_job.py refresh_ipl_data.py ./

# Copy default configuration files (can be overridden with volumes at runtime)
COPY matches.txt h2h.txt ./

# Create ipl_json directory (will be populated at runtime via volumes or from repository if available)
RUN mkdir -p ./ipl_json

# Create a non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose the API port
EXPOSE 8000

# Set environment variable for port
ENV PORT=8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the API server
CMD ["python", "api_server.py"]
