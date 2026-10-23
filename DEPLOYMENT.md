# Deployment – invest.suthaharan.de

> **Hinweis: Das Produktiv-Deployment läuft inzwischen anders.** invest.suthaharan.de nutzt
> das fertige Image `ghcr.io/sujant-h/investment-research-poc` (gebaut von
> `.github/workflows/ci.yml`) und wird über das private Infrastruktur-Repo `vps-infra`
> (Ansible) konfiguriert. Auf dem Server wird nichts mehr geklont oder gebaut. Die Anleitung
> unten bleibt als Referenz für einen manuellen Betrieb.

This guide deploys the Investment Research web app to a Linux VPS. The container
is published on `127.0.0.1` only; your **existing global nginx** on the VPS
terminates TLS and reverse-proxies the subdomain to it.

```
Visitor ──HTTPS──> nginx (:443, host) ──HTTP──> 127.0.0.1:APP_PORT ──> web container (:8080)
```

## What's in the box

| File            | Purpose                                                        |
| --------------- | ------------------------------------------------------------- |
| `Dockerfile`    | Builds the app image (Python 3.12, no external dependencies). |
| `compose.yaml`  | Runs the app, published on the host loopback for nginx.       |
| `.env.example`  | Template for API keys, app port, and rate limits.             |

## 1. DNS

Create a DNS record for the subdomain pointing at your server's public IP:

```
Type: A      Name: invest      Value: <your.server.ip>
```

(Add an `AAAA` record too if the server has IPv6.) Since nginx already runs on
this VPS, the record just needs to point at the same server.

## 2. Server prerequisites

Docker is the only new prerequisite (nginx is already installed):

```bash
curl -fsSL https://get.docker.com | sh          # Docker + Compose plugin
sudo usermod -aG docker "$USER" && newgrp docker
```

No new firewall ports are needed — traffic stays on `443` via nginx, and the
container is only reachable on `127.0.0.1`.

## 3. Configure

```bash
git clone <this-repo> investment-research && cd investment-research
cp .env.example .env
```

Edit `.env` and set at least:

- `OPENAI_API_KEY` – your OpenAI key.
- `MARKETAUX_API_TOKEN` – news provider key.
- `APP_PORT` – host loopback port nginx will proxy to (default `8080`; change
  it if that port is already taken on the VPS).

The rate-limit values (`RATE_LIMIT_*`) already have safe defaults that cap how
many paid analyses visitors can run. Tighten them if you want a smaller bill.

## 4. Launch the container

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8080/api/health   # -> {"status": "ok"}  (use your APP_PORT)
```

## 5. nginx reverse-proxy config

Add a server block for the subdomain on the host (e.g.
`/etc/nginx/sites-available/invest.suthaharan.de`), then obtain TLS with your
usual tool (`certbot --nginx -d invest.suthaharan.de`):

```nginx
server {
    server_name invest.suthaharan.de;

    # Cap the request body — the analysis payload is tiny; this blocks
    # memory-exhaustion attempts (the app enforces the same 64 KiB limit).
    client_max_body_size 64k;

    # Security headers. The frontend loads only same-origin assets, so a strict
    # CSP needs no 'unsafe-inline'. Uncomment HSTS only *after* TLS is live.
    add_header X-Frame-Options            "DENY"                                   always;
    add_header X-Content-Type-Options     "nosniff"                                always;
    add_header Referrer-Policy            "strict-origin-when-cross-origin"        always;
    add_header Content-Security-Policy    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'" always;
    # add_header Strict-Transport-Security "max-age=63072000; includeSubDomains"     always;

    location / {
        proxy_pass         http://127.0.0.1:8080;   # match APP_PORT
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        # Overwrite (do NOT append with $proxy_add_x_forwarded_for): a client can
        # otherwise pre-set X-Forwarded-For and rotate it to bypass per-IP limits.
        proxy_set_header   X-Forwarded-For   $remote_addr;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # listen 443 ssl;  # added by certbot --nginx
}
```

The `X-Forwarded-For` header above is what feeds the app's per-IP rate limiting;
overwriting it with `$remote_addr` ensures visitors cannot spoof it. Enable and
reload:

```bash
sudo ln -s /etc/nginx/sites-available/invest.suthaharan.de /etc/nginx/sites-enabled/
sudo certbot --nginx -d invest.suthaharan.de
sudo nginx -t && sudo systemctl reload nginx
curl https://invest.suthaharan.de/api/health   # -> {"status": "ok"}
```

## 6. Link it from your portfolio

Add a link on `suthaharan.de` pointing at the demo. Suggested snippet:

```html
<a href="https://invest.suthaharan.de" target="_blank" rel="noopener">
  KI-Investment-Research (Live-Demo)
</a>
```

The demo page itself already links back to `suthaharan.de` and shows a
"keine Anlageberatung" disclaimer in the footer.

## Updating

```bash
git pull
docker compose up -d --build
```

## Cost & abuse protection

Because every analysis calls paid APIs, the public `/api/research` endpoint is
rate limited (see `webapp.RateLimiter`):

- **Per visitor IP:** `RATE_LIMIT_PER_IP` requests per `RATE_LIMIT_WINDOW_SECONDS`.
- **Global daily cap:** `RATE_LIMIT_GLOBAL_PER_DAY` requests per UTC day across
  all visitors — a hard ceiling on daily spend.

The real client IP is read from the `X-Forwarded-For` header set by nginx.
Blocked requests get HTTP `429` with a friendly German message. Set any limit
to `0` to disable it.

## Notes

- The app binds `0.0.0.0:8080` **inside** the container only; it is not exposed
  on the host loopback (`127.0.0.1:APP_PORT`). All public traffic goes through
  the host nginx.
- Generated briefs are written to `/app/output` inside the container
  (ephemeral). Mount a volume there if you want to keep them.
- To run locally without Docker: `investment-research-web` (defaults to
  `127.0.0.1:8080`; override with `HOST`/`PORT` env vars or `--host/--port`).
