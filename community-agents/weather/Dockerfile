FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY main.py .

# Generate keys at build time (will be overwritten by secrets in prod)
RUN python -c "import nacl.signing; k=nacl.signing.SigningKey.generate(); open('agent_private_key.pem','wb').write(k.encode()); open('agent_public_key.pem','wb').write(k.verify_key.encode())"

# Run
ENV PORT=8080
EXPOSE 8080
CMD ["python", "main.py"]
