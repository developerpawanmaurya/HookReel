# Putting HookReel on a server

HookReel runs as three containers on one Linux server: the app, PostgreSQL, and Caddy (which handles HTTPS).

## What you need

- A Linux server with Docker. Clipping is CPU work: plan on **8+ CPU cores, 16 GB RAM and 200+ GB of disk** if
  several people will use it. Transcription runs at roughly 10x real time per video on 4 cores.
- A domain name pointing at the server (an `A` record).
- An AI key (see "Choose your AI" in the README). Optional: a Google "Web application" OAuth client, and an SMTP
  service for emails.

## Steps

1. Copy this folder to the server (or `git clone` it there).
2. `cp .env.example .env` and fill it in: the AI lines, `HOOKREEL_DOMAIN`, `POSTGRES_PASSWORD`, and
   `COMPOSE_PROFILES=own-https` if the server is HookReel's alone. Put key files, if you use files, in `./secrets/`.
3. `docker compose up -d --build`
   The first start downloads the speech model (about 480 MB) and creates the database tables.
4. Open `https://your-domain` and sign up. With Docker, accounts are on (`HOOKREEL_ACCOUNTS=1`), so everyone signs in.
   Every new account is a normal user.
5. Make yourself an admin, on the server: `docker compose exec app python -m studio.admin grant you@example.com`
   The admin dashboard is then at `https://your-domain/admin`. It answers "not found" for everyone who is not an
   admin, and no page or web request can make someone an admin: only that command can.
6. Sign in as that admin, open **Settings, AI**, and add your AI key there (or put it in `.env`).

## Free, with no domain: Oracle Cloud "Always Free"

Oracle's free tier includes an Arm server (2 cores, 12 GB memory, 200 GB disk) that is enough for one person.
`deploy/oracle-free.sh` sets it all up on first boot, with a free https address from sslip.io and sign-up closed
to everyone but you.

1. Make an Oracle Cloud account (a card is asked for to confirm who you are; the free tier is not charged).
2. **Networking, Virtual cloud networks**: in the default VCN's security list, add ingress rules for TCP **80** and
   **443** from `0.0.0.0/0`.
3. **Compute, Instances, Create instance**: image **Ubuntu 24.04**, shape **VM.Standard.A1.Flex** with 2 OCPUs and
   12 GB memory, boot volume about 150 GB, a public IPv4 address. Under **Advanced options, Initialization script**,
   paste (with your email):

   ```bash
   #!/bin/bash
   export HOOKREEL_OWNER=you@example.com
   curl -fsSL https://raw.githubusercontent.com/developerpawanmaurya/HookReel/main/deploy/oracle-free.sh | bash
   ```

4. About 10 to 15 minutes later, open `https://<public-ip-with-dashes>.sslip.io` (for 1.2.3.4:
   `https://1-2-3-4.sslip.io`), sign up with that email, and you are made the admin within a minute. Add your AI key
   in **Settings, AI**.

On two cores a one-hour video takes roughly a quarter of an hour. YouTube sometimes refuses downloads from cloud
servers (see "Good to know"); uploads, Twitch and Kick are not affected.

## Connecting YouTube, Instagram and TikTok

People connect their accounts with one click in **Settings, Connected apps**: they press Connect, sign in on the
platform's own page, and come back. For that, the server needs one app registered with each platform. An admin can
do it right there: press **Set up** on a platform, follow the steps shown, and paste the app's id and secret (or put
them in `.env`, see `.env.example`). The redirect address to register is shown in the panel, with a Copy button.

- **YouTube** (Google Cloud): an OAuth client of type Web application, with YouTube Data API v3 turned on. Until
  Google verifies the app, people see a warning screen and uploads stay private.
- **Instagram** (Meta for Developers): an app with the "Manage messaging & content on Instagram" use case. Meta
  apps made since autumn 2026 only offer **API setup with Unified login**: link the app to a business portfolio,
  create a configuration (system-user token, with instagram_content_publish), register the redirect address on it,
  and paste the App ID, App secret and Configuration ID. Older apps with API setup with Instagram login leave the
  Configuration ID empty. Works with Creator and Business accounts. Until Meta reviews the app, only accounts added as testers can connect. Instagram
  fetches each clip from a one-hour signed link on your site, so the site needs a public https address.
- **TikTok** (TikTok for Developers): an app with Login Kit and the Content Posting API (Direct Post), scopes
  `user.info.basic` and `video.publish`. Until TikTok audits the app, clips are posted as private (HookReel does
  this by itself and says so on the account).

Instagram and TikTok only accept https redirect addresses.

## Google setup (sign-in and YouTube)

In Google Cloud, create an OAuth client of type **Web application** with these redirect URIs:

- `https://your-domain/auth/google/callback`
- `https://your-domain/oauth/youtube/callback`

Enable **YouTube Data API v3** in the same project. Posting publicly to YouTube needs Google's API audit;
until then uploads from the API stay private.

## Email

Set the `HOOKREEL_SMTP_*` lines and `HOOKREEL_MAIL_FROM` to send password-reset and confirmation emails through any
SMTP service. On a public site also set `HOOKREEL_VERIFY_EMAIL=1`, so people confirm their address before clipping.
Without SMTP on an HTTPS site, no reset emails can be sent.

## Good to know

- **Data**: everything lives in two Docker volumes, `pgdata` (accounts, AI usage) and `data` (videos, clips).
  Back both up. `docker compose exec db pg_dump -U hookreel hookreel > backup.sql` dumps the database.
- **Capacity**: `HOOKREEL_JOB_WORKERS` is how many videos are processed at once; `HOOKREEL_MAX_LIVE` is how many live
  streams are recorded at once. Raise them only as far as the CPU allows.
- **One server only**: jobs and live recordings run inside the app process. Do not start a second copy of the app
  against the same data.
- **YouTube downloads from data centres** are sometimes refused by YouTube ("confirm you're not a bot"). If links
  fail on the server but work at home, the server's address is the cause. HookReel then pauses YouTube links for a
  few minutes and says so; uploads and Twitch or Kick links keep working.
- **Updates**: `git pull && docker compose up -d --build`. A restart pauses videos in progress (they pick up
  where they stopped) and live recordings (clips already found are finished from the saved stream).
- **Open sign-up**: anyone who can reach the site can make an account and use your AI key. On a public address,
  keep the limits in `.env` sensible, or put the site behind your own access control.

## A server that already runs other sites

Leave `COMPOSE_PROFILES=own-https` out of `.env`. HookReel then listens only on `127.0.0.1:8765` and the web
server that is already there forwards the domain to it: see `deploy/nginx-hookreel.conf`, or
`deploy/docker-compose.traefik.yml` for Traefik.

## Cloudflare CDN in front

With the record proxied (orange cloud):

- Set `HOOKREEL_CLIENT_IP_HEADER=CF-Connecting-IP` in `.env`, so rate limits see each visitor, not Cloudflare. The
  header is only believed for connections that really come from Cloudflare's address ranges.
- Images, videos and scripts under `/brand/` and `/assets/` are cached by Cloudflare automatically. Signed-in
  pages, clips and the API send `private` or `no-store` and are never cached by Cloudflare.
- Use SSL/TLS mode Full (strict) with a Cloudflare origin certificate in `secrets/` and
  `HOOKREEL_CADDYFILE=Caddyfile.origin`.
- Cloudflare's standard plans refuse requests over 100 MB. HookReel sends big uploads in pieces
  (`HOOKREEL_UPLOAD_PART_MB`, 40 by default), so large files still work.

## Speech to text on a graphics card

Optional. A second machine with an NVIDIA card can do most of the transcription much faster:
`deploy/gpu/docker-compose.yml` runs it, and `HOOKREEL_ASR_URL` plus `HOOKREEL_ASR_TOKEN` on the main server point
at it. Keep its port closed to the internet. If it is unreachable, the main server carries on with its own
processor.
