FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Herramientas de COPIA DE SEGURIDAD (Centinela las ejecuta desde aquí):
#   · postgresql-client-16 → pg_dump / pg_restore. Habla con Postgres por la red interna
#     de Docker; NO se usa `docker exec` contra su contenedor, bloqueado a propósito en el
#     proxy de Docker por seguridad.
#   · openssh-client + rsync → enviar la copia FUERA del servidor.
#
# La versión 16 está CLAVADA a la del servidor, y no es un capricho: Debian 13 trae el
# cliente 17, y sus volcados llevan un formato que el Postgres 16 NO sabe leer
# ("unsupported version (1.16) in file header", comprobado el 24-jul-2026). O sea que las
# copias solo se podrían restaurar con herramientas 17+, y eso no se descubre hasta el día
# que toca restaurar — el peor día posible. Por eso se añade el repositorio oficial de
# PostgreSQL: para que la copia la pueda leer el propio servidor del que salió.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt trixie-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-16 openssh-client rsync \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright + Chromium para `portal_browser.leer_portal` quedan DESACTIVADOS a propósito
# (26-oct-2026): la guarda anti-SSRF de ese módulo pasó por 3 rondas de revisión sin cerrar
# la última verificación de principio a fin, así que el paquete no se instala — sin él,
# leer_portal falla siempre de forma segura (ImportError capturado, error relleno, nunca
# navega a ningún lado). No reinstalar sin pasar antes la verificación completa end-to-end.
# RUN pip install --no-cache-dir playwright && playwright install --with-deps chromium

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
