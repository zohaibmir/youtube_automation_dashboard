# Oracle Always Free Deployment

Yes. This project can run on Oracle Cloud Always Free so it keeps working when your local computer is off.

Best fit:

1. Ubuntu VM on Oracle Cloud Always Free
2. Run `server.py` as the dashboard/API service
3. Run `scheduler.py` as the always-on queue worker
4. Keep `.env`, `tokens/`, `client_secrets.json`, and `yt_automation.db` on the VM

## Why Oracle Free VM Works Better Than Sleep-Based Free Hosting

1. Your app needs long-running background work.
2. Video generation and uploads are not a good fit for sleep-on-idle platforms.
3. You need persistent local files for tokens, outputs, thumbnails, and SQLite.

## Recommended VM Shape

1. `VM.Standard.A1.Flex` if available in your region
2. Ubuntu 22.04 or 24.04
3. At least 2 OCPU and 8 GB RAM if Oracle free capacity allows it

## What You Need To Copy From Your Local Machine

Copy these to the VM after cloning the repo:

1. `.env`
2. `client_secrets.json`
3. `tokens/`

Important:

Generate and refresh YouTube tokens locally first, then copy `tokens/` to the VM. That is simpler than doing OAuth browser login on a headless server.

## 1. Create The Oracle VM

1. Sign in to Oracle Cloud.
2. Create an Always Free Ubuntu VM.
3. Allow inbound port `22` for SSH.
4. Allow inbound port `8080` if you want direct dashboard access.
5. Attach enough block storage if you plan to keep many rendered videos.

## 2. Clone Repo And Install Dependencies

On the VM:

```bash
git clone <your-repo-url> youtube_automation
cd youtube_automation
bash deploy/oracle/setup_oracle_vm.sh
```

This script installs system packages, creates `.venv`, installs Python dependencies, and creates runtime folders.

## 3. Copy Secrets And Tokens

From your local machine:

```bash
scp .env opc@YOUR_VM_IP:/home/opc/youtube_automation/.env
scp client_secrets.json opc@YOUR_VM_IP:/home/opc/youtube_automation/client_secrets.json
scp -r tokens opc@YOUR_VM_IP:/home/opc/youtube_automation/
```

Adjust `opc` and the destination path if your Oracle username differs.

## 4. Install Systemd Services

This repo includes templates:

1. `deploy/oracle/yt-server.service.template`
2. `deploy/oracle/yt-scheduler.service.template`

Replace placeholders and install them:

```bash
cd /home/opc/youtube_automation
sed "s|__APP_DIR__|/home/opc/youtube_automation|g; s|__USER__|opc|g" \
  deploy/oracle/yt-server.service.template | sudo tee /etc/systemd/system/yt-server.service >/dev/null

sed "s|__APP_DIR__|/home/opc/youtube_automation|g; s|__USER__|opc|g" \
  deploy/oracle/yt-scheduler.service.template | sudo tee /etc/systemd/system/yt-scheduler.service >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now yt-server
sudo systemctl enable --now yt-scheduler
```

## 5. Check Status

```bash
sudo systemctl status yt-server
sudo systemctl status yt-scheduler
journalctl -u yt-server -f
journalctl -u yt-scheduler -f
```

## 6. Open The Dashboard

If port `8080` is open:

```text
http://YOUR_VM_IP:8080/youtube_automation_dashboard.html
```

For better security, put Nginx or Caddy in front of it later and restrict public access.

## 7. Make Daily Automation Work

The scheduler already runs continuously. Your seeded topics remain in SQLite on the VM.

Recommended settings:

1. Set `VIDEOS_PER_WEEK=7` in `.env`
2. Keep the 30-day queue seeded
3. Use Oracle block storage or periodically clean old output files

## Cost And Limits

Oracle Always Free is the best free option for this repo, but it still has limits:

1. Free capacity is not always available in every region
2. Rendering many videos can consume disk fast
3. If your workload grows, a low-cost VPS may become simpler

## Notes About Automatic Social Posting

This deployment keeps the tool running automatically, but social integrations still need their own platform credentials and wiring. Oracle hosting solves uptime, not platform API setup.
