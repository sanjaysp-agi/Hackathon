# Deploying the Intelligent Workflow Manager — step by step

This gets the app live on **one AWS EC2 box**: nginx serves the React dashboard,
FastAPI runs the backend, SQLite holds the data, and Claude runs on **Bedrock**
via the instance's IAM role. A login (username + password) gates the whole site.

You do **4 things**; the server configures itself from your repo.

> **Account note:** don't use the temporary *Workshop Studio* account — it expires
> and gets deleted, so the URL won't last. Use a normal AWS account (or a fresh
> workshop you control) where you can create an IAM role and enable Bedrock.

---

## Step 0 — one-time prerequisites
- A **GitHub account** (free): https://github.com/signup
- An **AWS account** you can log into: https://console.aws.amazon.com
- **Git installed** on your laptop (you already have it).

---

## Step 1 — put the code on GitHub
GitHub is how the server gets the code (works around the S3/SSL block on your laptop).

1. Create an **empty private repo** on GitHub: click **+ → New repository**, name it
   `iwm`, choose **Private**, **don't** add a README, click **Create repository**.
2. In a terminal, from the project root
   (`.../Documents/hack`), run — replacing `YOU` with your GitHub username:
   ```bash
   git init
   git add .
   git commit -m "Intelligent Workflow Manager"
   git branch -M main
   git remote add origin https://github.com/YOU/iwm.git
   git push -u origin main
   ```
   (If it asks for a password, use a **Personal Access Token**:
   GitHub → Settings → Developer settings → Tokens (classic) → Generate, scope `repo`.)
3. Your clone URL for Step 3 is `https://github.com/YOU/iwm.git`.
   For a **private** repo, use `https://<TOKEN>@github.com/YOU/iwm.git` so the server can pull it.

> `.env` and secrets are already git-ignored — they will **not** be pushed. Good.

---

## Step 2 — turn on Bedrock model access (one time, ~1 min)
1. AWS Console → search **Bedrock** → open it. Top-right region = **US East (N. Virginia) us-east-1**.
2. Left menu → **Model access** → **Enable specific models** (or "Manage model access").
3. Tick the **Anthropic Claude** models → **Save / Request access** (usually instant).

That's what lets the app actually call Claude.

---

## Step 3 — launch everything with one CloudFormation stack
1. AWS Console → search **CloudFormation** → **Create stack → With new resources**.
2. **Choose "Upload a template file"** → **Choose file** → pick
   `deploy/cloudformation.yaml` from this repo → **Next**.
3. **Stack name:** `iwm`. Fill the parameters:
   - **RepoUrl** → your URL from Step 1 (`https://github.com/YOU/iwm.git`, or the token form if private)
   - **BasicUser** → `admin` (or anything)
   - **BasicPass** → a password you'll remember
   - **InstanceType** → `t3.small` (use `t3.medium` if the build is slow)
   - leave **LatestAmi** as is
4. **Next → Next** → tick **"I acknowledge that AWS CloudFormation might create IAM resources"** → **Submit**.
5. Wait ~3–5 min until the stack shows **CREATE_COMPLETE**. (The box is installing + building in the background.)
6. Open the stack → **Outputs** tab → click the **URL**.

---

## Step 4 — log in
The browser shows a login popup → enter the **BasicUser / BasicPass** you chose → the dashboard loads. 🎉

> First open may take an extra minute while the server finishes building. If you
> see an nginx error page, wait 60s and refresh.

---

## If something's off (quick checks)
The build log lives on the instance at **`/var/log/iwm-bootstrap.log`**. To read it:
- EC2 Console → the `iwm-control-tower` instance → **Connect → EC2 Instance Connect** (browser SSH, no key needed) → then:
  ```bash
  sudo tail -n 100 /var/log/iwm-bootstrap.log   # setup log
  sudo systemctl status iwm                     # is the API running?
  sudo journalctl -u iwm -n 50                  # API logs
  ```
- Common fixes: Bedrock not enabled (Step 2) → chat errors; build OOM → recreate stack with `t3.medium`.

---

## Make it HTTPS + nicer login (optional, later)
- **HTTPS:** point a domain at the instance (Route 53 or any registrar), SSH in, and run
  `sudo dnf install -y certbot python3-certbot-nginx && sudo certbot --nginx -d your.domain`.
- **Cognito login** (instead of Basic Auth, with real per-user identity for the audit trail):
  put an **Application Load Balancer** in front with a Cognito listener rule — ask and I'll
  add a `deploy/cognito.yaml` for it.

---

## Tear it down (stop all charges)
CloudFormation → select the `iwm` stack → **Delete**. That removes the instance,
security group, and IAM role in one go.

---

## What this uses
**EC2 · EBS (instance disk) · Bedrock (Claude) · IAM role · Security Group** — plus
**GitHub** for code transport and **nginx Basic Auth** for the login. SQLite is the DB
(the file on the instance). No S3/RDS/Cognito/AgentCore required for this single-box deploy.
