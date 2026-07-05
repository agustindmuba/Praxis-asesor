#!/usr/bin/env bash
# Setup inicial del VPS DigitalOcean para Praxis Asesor.
#
# Ejecutar UNA vez, la primera después de crear el droplet:
#   ssh root@<IP-DEL-VPS>
#   curl -fsSL https://raw.githubusercontent.com/agustindmuba/Praxis-asesor/develop/scripts/bootstrap-vps.sh | bash
#
# Instala:
#   - Docker Engine + docker compose plugin (repo oficial de Docker)
#   - ufw firewall con 22/80/443 abiertos
#   - fail2ban (protección SSH brute-force)
#   - Usuario `praxis` con sudo (no correr todo como root)
#   - Estructura /opt/praxis lista para clonar el repo
#
# Después de esto, cargá el .env y hacé el primer `docker compose up -d`.

set -euo pipefail

echo "==> [1/7] Actualizar sistema"
apt-get update
apt-get upgrade -y

echo "==> [2/7] Instalar utilitarios base"
apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    ufw \
    fail2ban \
    git \
    htop \
    unattended-upgrades

echo "==> [3/7] Instalar Docker Engine (repo oficial)"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

. /etc/os-release
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker

echo "==> [4/7] Firewall (ufw)"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp   comment 'HTTP (Caddy)'
ufw allow 443/tcp  comment 'HTTPS (Caddy)'
ufw allow 443/udp  comment 'HTTP/3 (Caddy)'
ufw --force enable
ufw status verbose

echo "==> [5/7] fail2ban (protección SSH)"
systemctl enable --now fail2ban

echo "==> [6/7] Crear usuario praxis"
if ! id -u praxis >/dev/null 2>&1; then
    useradd -m -s /bin/bash praxis
    usermod -aG docker,sudo praxis
    # Passwordless sudo para el usuario praxis (solo apt/docker/systemctl).
    echo "praxis ALL=(ALL) NOPASSWD:/usr/bin/apt-get,/usr/bin/docker,/usr/bin/systemctl" \
        > /etc/sudoers.d/praxis
    chmod 440 /etc/sudoers.d/praxis
    # Copiar authorized_keys de root al nuevo usuario.
    if [ -f /root/.ssh/authorized_keys ]; then
        mkdir -p /home/praxis/.ssh
        cp /root/.ssh/authorized_keys /home/praxis/.ssh/
        chown -R praxis:praxis /home/praxis/.ssh
        chmod 700 /home/praxis/.ssh
        chmod 600 /home/praxis/.ssh/authorized_keys
    fi
fi

echo "==> [7/7] Estructura /opt/praxis"
mkdir -p /opt/praxis
chown -R praxis:praxis /opt/praxis

echo
echo "=================================================="
echo "  Bootstrap COMPLETO."
echo "  Siguiente paso: como usuario 'praxis',"
echo "    su - praxis"
echo "    cd /opt/praxis"
echo "    git clone -b develop https://github.com/agustindmuba/Praxis-asesor.git ."
echo "    cp .env.production.example .env"
echo "    nano .env    # setear valores reales"
echo "    docker compose -f docker-compose.prod.yml up -d --build"
echo "=================================================="
