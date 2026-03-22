# Denkeeper systemd User Units

These units provide reboot-safe startup and periodic health checks for the container stack.

## Units

- `denkeeper-compose.service`
  - runs `docker compose up -d --build` for `ops/docker/docker-compose.yml`
  - `RemainAfterExit=yes` keeps service active after compose startup
- `denkeeper-healthcheck.service`
  - runs `ops/docker/healthcheck.sh`
- `denkeeper-healthcheck.timer`
  - executes the healthcheck service every 5 minutes

## Install

```bash
cd /home/ninadsapate21/workspace/projects/denkeeper/ops/systemd
./install-user-units.sh
```

`install-user-units.sh` renders the unit templates with the detected repository root, so unit paths match the local checkout location.

## Reboot behavior

To start user units at boot without an interactive login:

```bash
sudo loginctl enable-linger "$USER"
```

## Inspect

```bash
systemctl --user status denkeeper-compose.service
systemctl --user status denkeeper-healthcheck.timer
journalctl --user -u denkeeper-compose.service -n 100 --no-pager
journalctl --user -u denkeeper-healthcheck.service -n 100 --no-pager
```
