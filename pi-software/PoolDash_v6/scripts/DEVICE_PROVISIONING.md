# PoolAIssistant_v6 Device Provisioning

This draft flow provisions each cloned device with a unique token and uses that token for secure uploads.

## Requirements
- Backend running with `BOOTSTRAP_SECRET` set
- Pi has outbound HTTPS access to the backend

## Provisioning (first boot)
1. Export `BACKEND_URL` and `BOOTSTRAP_SECRET` (or use `scripts/poolaissistant.env`).
2. Run:
   `python3 scripts/device_provision.py`

This stores a token at `DEVICE_TOKEN_PATH` (default: `/opt/PoolAIssistant/data/device_token.json`).

## Upload
Default mode sends only new readings (delta upload) from `POOLDB`:
`python3 scripts/device_upload.py`

Or pass a file path:
`python3 scripts/device_upload.py /path/to/file`

Set `UPLOAD_MODE=file` to upload the full SQLite file instead.

## Systemd (auto-retry)
Copy the unit files from `scripts/systemd` to `/etc/systemd/system` and enable:

`sudo systemctl enable --now poolaissistant_device_sync.timer`

This runs on boot and every 10 minutes. Failures write a warning to
`BACKEND_STATUS_PATH` (default: `/opt/PoolAIssistant/data/backend_status.json`) and the device continues normal operation.

## Notes
- The backend identifies devices by MAC + bootstrap secret at provision time.
- Tokens are stored locally; if deleted, re-run provisioning to rotate.
