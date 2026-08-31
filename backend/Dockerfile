FROM python:3.12-slim

WORKDIR /app

# pip usa el bundle del sistema (incluye la CA corporativa si se instala abajo)
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt

COPY requirements.txt .
COPY ca /ca

# CA corporativa OPCIONAL (Netskope / proxy HTTPS): crear ca/corporate-ca-chain.crt
# con la cadena COMPLETA (hoja + intermedias + RAÍZ, la raíz al final).
# Si el archivo no existe, el build continúa normal.
RUN if [ -f /ca/corporate-ca-chain.crt ]; then \
      cp /ca/corporate-ca-chain.crt /usr/local/share/ca-certificates/corporate-ca-chain.crt && \
      update-ca-certificates; \
    fi

RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]