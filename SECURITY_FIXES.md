# Security Fixes Implementation Guide

## ✅ What Has Been Fixed

### 1. Removed Hardcoded API Key from cloudbuild.yaml
- **Before**: API key `sk-atp-amorce-dev-2024` was hardcoded in line 38
- **After**: Configured to use Google Secret Manager reference
- **Changes**:
  - Added `availableSecrets` section to access Secret Manager
  - Removed hardcoded key from `--set-env-vars`
  - Added note to configure AGENT_API_KEY in Cloud Run console

### 2. Removed Hardcoded Admin Key from setup_full_env.py
- **Before**: Admin key `sk-admin-amorce-2025-secure-reset` was hardcoded
- **After**: Now reads from `DIRECTORY_ADMIN_KEY` environment variable
- **Changes**:
  - Replaced hardcoded value with `os.environ.get()`
  - Added validation to ensure the variable is set
  - Added helpful error message with usage instructions

---

## 🔐 Next Steps: Setting Up Secrets

### Option 1: Use the Interactive Script (Recommended)

I've created a script that will guide you through setting up the secrets:

```bash
cd /Users/rgosselin/amorce
./setup_secrets.sh
```

The script will:
1. Prompt you for new rotated secret values
2. Create or update secrets in Secret Manager
3. Provide commands to configure Cloud Run

### Option 2: Manual Setup

If you prefer manual setup, follow these commands:

#### Create AGENT_API_KEY Secret
```bash
# Generate a new key (replace with your own random string)
NEW_AGENT_KEY="sk-atp-amorce-2025-$(openssl rand -hex 16)"

# Create the secret
echo -n "$NEW_AGENT_KEY" | gcloud secrets create AGENT_API_KEY \
  --project=amorce-prod-rgosselin \
  --replication-policy="automatic" \
  --data-file=-
```

#### Create DIRECTORY_ADMIN_KEY Secret
```bash
# Generate a new key (replace with your own random string)
NEW_ADMIN_KEY="sk-admin-amorce-2025-$(openssl rand -hex 16)"

# Create the secret
echo -n "$NEW_ADMIN_KEY" | gcloud secrets create DIRECTORY_ADMIN_KEY \
  --project=amorce-prod-rgosselin \
  --replication-policy="automatic" \
  --data-file=-
```

#### Configure Cloud Run Service
```bash
# Update the 'natp' service to use the AGENT_API_KEY secret
gcloud run services update natp \
  --project=amorce-prod-rgosselin \
  --region=us-central1 \
  --update-secrets=AGENT_API_KEY=AGENT_API_KEY:latest
```

---

## 📝 Using the Updated Scripts

### For setup_full_env.py

Before running the script, set the environment variable:

```bash
# Option 1: Set from Secret Manager
export DIRECTORY_ADMIN_KEY=$(gcloud secrets versions access latest \
  --secret="DIRECTORY_ADMIN_KEY" \
  --project="amorce-prod-rgosselin")

# Option 2: Set directly (for testing only)
export DIRECTORY_ADMIN_KEY="your-new-admin-key"

# Then run the script
python3 setup_full_env.py
```

### For Cloud Build Deployments

Cloud Build will now automatically access `AGENT_API_KEY` from Secret Manager when deploying. However, you still need to configure Cloud Run to use the secret as an environment variable.

---

## ⚠️ Important Security Actions

### 1. Rotate the Exposed Keys
- ✅ Generate new keys (done via script or manual commands above)
- ⏳ Update all services to use new keys
- ⏳ Test new configuration
- ⏳ Invalidate old keys:
  - `sk-atp-amorce-dev-2024` (old AGENT_API_KEY)
  - `sk-admin-amorce-2025-secure-reset` (old DIRECTORY_ADMIN_KEY)

### 2. Commit and Push Changes
```bash
cd /Users/rgosselin/amorce
git add cloudbuild.yaml setup_full_env.py setup_secrets.sh
git commit -m "Security: Remove hardcoded secrets, use Secret Manager"
git push
```

### 3. Update Cloud Run Configuration
After secrets are created, update the Cloud Run service to reference them.

---

## ✅ Verification Checklist

- [ ] Run `setup_secrets.sh` or manually create secrets
- [ ] Verify secrets exist in Secret Manager
- [ ] Update Cloud Run service to use AGENT_API_KEY secret
- [ ] Test `setup_full_env.py` with new DIRECTORY_ADMIN_KEY
- [ ] Commit and push changes to GitHub
- [ ] Deploy via Cloud Build and verify it works
- [ ] Invalidate old exposed keys
- [ ] Update any other services using the old keys

---

## 🔍 Verify Secrets in Secret Manager

```bash
# List all secrets
gcloud secrets list --project=amorce-prod-rgosselin

# View secret metadata (not the value)
gcloud secrets describe AGENT_API_KEY --project=amorce-prod-rgosselin
gcloud secrets describe DIRECTORY_ADMIN_KEY --project=amorce-prod-rgosselin
```

---

## 📚 Additional Resources

- [Google Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)
- [Cloud Run Secrets](https://cloud.google.com/run/docs/configuring/secrets)
- [Cloud Build Secrets](https://cloud.google.com/build/docs/securing-builds/use-secrets)
