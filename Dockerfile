FROM python:3.13-slim

WORKDIR /app

# Install dependencies
# (We install flask and cryptography, plus ezkl for the verification)
COPY requirements.txt .
RUN pip install --no-cache-dir flask requests cryptography ezkl

COPY . .

# Expose the local proxy port
EXPOSE 8080

CMD ["python", "docker-proxy.py"]
