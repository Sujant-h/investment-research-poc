# Deployment – invest.suthaharan.de

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

    location / {
        proxy_pass         http://127.0.0.1:8080;   # match APP_PORT
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    # listen 443 ssl;  # added by certbot --nginx
}
```

The `X-Forwarded-For` header above is what feeds the app's per-IP rate limiting.
Enable and reload:

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
