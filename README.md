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
3. Copy `.env.example` to `.env` and fill in your Signal number and recipients. Keep `.env` private and never commit it.
4. Run `docker compose up -d`.

Diun checks every six hours by default (`schedule` in `diun.yml`) and watches all running containers. Set `watchByDefault: false` and add the label `diun.enable=true` to only watch chosen containers.

## Configuration

| Variable | Description |
|---|---|
| `SIGNAL_NUMBER` | Sender number registered with signal-cli-rest-api |
| `SIGNAL_RECIPIENTS` | Comma-separated recipient numbers |
| `SIGNAL_API_URL` | Defaults to `http://signal-api:8080/v2/send` |

## Security notes

- The bridge has no authentication. It only listens on the internal `alerts` network and publishes no host ports; keep it that way.
- Diun needs read-only access to the Docker socket to see your containers. That socket is effectively root access, so only run images you trust.
- The bridge container runs with a read-only filesystem and `no-new-privileges`.
