# diun-signal-bridge

Sends [Diun](https://crazymax.dev/diun/) container image update notifications to Signal through [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api).

Diun watches your running Docker containers for new image versions and posts a webhook. This small Python service (standard library only) receives that webhook and forwards a short message to Signal.

## How it works

```
Diun --webhook--> diun-signal-bridge --HTTP--> signal-cli-rest-api --> Signal
```

A message looks like:

```
🔔 CONTAINER UPDATE

Image: docker.io/library/caddy:2-alpine
Status: UPDATE
Container: caddy
```

## Setup

Requirements: Docker, and a running signal-cli-rest-api container with a registered number, reachable as `signal-api` on a shared Docker network.

1. Create the shared network once: `docker network create alerts`.
2. Attach your signal-api container to that `alerts` network.
3. Copy `.env.example` to `.env`, fill in your Signal number and recipients, and generate a private 48-byte random webhook token with `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`. Put it in `BRIDGE_WEBHOOK_TOKEN`. Keep `.env` private (`chmod 600 .env`) and never commit it.
4. Run `docker compose up -d`.

Diun checks every six hours by default (`schedule` in `diun.yml`) and watches all running containers. Set `watchByDefault: false` and add the label `diun.enable=true` to only watch chosen containers.

## Configuration

| Variable | Description |
|---|---|
| `SIGNAL_NUMBER` | Sender number registered with signal-cli-rest-api |
| `SIGNAL_RECIPIENTS` | Comma-separated recipient numbers |
| `SIGNAL_API_URL` | Defaults to `http://signal-api:8080/v2/send` |

## Security notes

- The bridge checks the DIUN `Authorization: Bearer` webhook header against the private token. It fails closed without the token and never publishes a host port. DIUN sends the header through `DIUN_NOTIF_WEBHOOK_HEADERS_AUTHORIZATION`. Leave `alerts` restricted to trusted services.
- DIUN no longer mounts the Docker socket. A dedicated socket proxy on an internal-only `docker-api` network allows GET access to needed Docker API resources and denies POST. Only the proxy mounts the real Docker socket. This reduces the blast radius but the proxy still has privileged access and needs image updates and restricted network membership.
- The bridge container runs with a read-only filesystem and `no-new-privileges`.


## Migration and verification

The updated configuration **requires a new local secret**. After pulling changes to the server, add `BRIDGE_WEBHOOK_TOKEN` to the existing private `.env`. Keep the same token on both DIUN and bridge (Compose passes it to both) and keep `.env` out of Git. Run `docker compose config --quiet` to check interpolation, then `docker compose pull && docker compose up -d`. Inspect `docker compose ps` and `docker compose logs --tail 60 diun diun-signal-bridge socket-proxy`. The webhook accepts at most 64 KiB of JSON and at most eight concurrent requests. Unauthorized POSTs return 401; invalid bodies are rejected; healthy bridge responds on `/health`.

The proxy image is pinned to a released tag rather than `latest`, and DIUN uses its major-release tag. Periodically update both after checking upstream release notes. No real Signal phone numbers or webhook secrets are stored in this repository.
