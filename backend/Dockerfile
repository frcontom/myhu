FROM python:3.12-slim

WORKDIR /app

# Certificados corporativos (Netskope/Kaspersky) — opcional: se instala backend/ca/*.crt si existen
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*

COPY ca /ca
RUN if ls /ca/*.crt >/dev/null 2>&1; then \
      cp /ca/*.crt /usr/local/share/ca-certificates/ && \
      update-ca-certificates; \
    fi

# pip usa el bundle del sistema (incluye la CA corporativa si se instaló)
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# Kiro CLI (opcional) - proveedor "kiro": se usa en modo headless con KIRO_API_KEY
RUN if curl -fsSL --max-time 180 https://cli.kiro.dev/install -o /tmp/kiro-install.sh \
       && bash /tmp/kiro-install.sh \
       && /root/.local/bin/kiro-cli --version; then \
      echo "kiro-cli instalado"; \
    else \
      echo "AVISO: no se pudo instalar kiro-cli (proveedor kiro no estara disponible)"; \
    fi; \
    rm -f /tmp/kiro-install.sh

ENV PATH="/root/.local/bin:${PATH}"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]