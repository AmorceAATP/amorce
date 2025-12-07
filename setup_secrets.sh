#!/bin/bash
# Script to create and rotate secrets in Google Secret Manager
# Run this script to set up secrets for Amorce orchestrator

set -e  # Exit on error

PROJECT_ID="amorce-prod-rgosselin"
REGION="us-central1"

echo "🔐 Setting up secrets in Google Secret Manager for project: $PROJECT_ID"
echo ""

# Function to create or update a secret
create_or_update_secret() {
    local SECRET_NAME=$1
    local SECRET_VALUE=$2
    local DESCRIPTION=$3
    
    echo "📝 Processing secret: $SECRET_NAME"
    
    # Check if secret exists
    if gcloud secrets describe "$SECRET_NAME" --project="$PROJECT_ID" >/dev/null 2>&1; then
        echo "   ↳ Secret exists, adding new version..."
        echo -n "$SECRET_VALUE" | gcloud secrets versions add "$SECRET_NAME" \
            --project="$PROJECT_ID" \
            --data-file=-
        echo "   ✅ New version added to $SECRET_NAME"
    else
        echo "   ↳ Creating new secret..."
        echo -n "$SECRET_VALUE" | gcloud secrets create "$SECRET_NAME" \
            --project="$PROJECT_ID" \
            --replication-policy="automatic" \
            --data-file=-
        echo "   ✅ Created new secret: $SECRET_NAME"
    fi
    echo ""
}

echo "⚠️  IMPORTANT: You need to generate NEW rotated keys to replace the exposed ones"
echo "   - Old AGENT_API_KEY: sk-atp-amorce-dev-2024 (EXPOSED - DO NOT USE)"
echo "   - Old ADMIN_KEY: sk-admin-amorce-2025-secure-reset (EXPOSED - DO NOT USE)"
echo ""
echo "Press ENTER to continue with setting up secrets (you'll be prompted for values)..."
read

# Setup AGENT_API_KEY
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣  AGENT_API_KEY (for Orchestrator authentication)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Enter the NEW rotated AGENT_API_KEY (or press ENTER to skip):"
echo "Suggested format: sk-atp-amorce-$(date +%Y)-<random-string>"
read -r AGENT_API_KEY_VALUE

if [ -n "$AGENT_API_KEY_VALUE" ]; then
    create_or_update_secret "AGENT_API_KEY" "$AGENT_API_KEY_VALUE" "API key for orchestrator authentication"
else
    echo "⏭️  Skipped AGENT_API_KEY"
    echo ""
fi

# Setup DIRECTORY_ADMIN_KEY
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣  DIRECTORY_ADMIN_KEY (for Trust Directory admin access)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Enter the NEW rotated DIRECTORY_ADMIN_KEY (or press ENTER to skip):"
echo "Suggested format: sk-admin-amorce-$(date +%Y)-<random-string>"
read -r DIRECTORY_ADMIN_KEY_VALUE

if [ -n "$DIRECTORY_ADMIN_KEY_VALUE" ]; then
    create_or_update_secret "DIRECTORY_ADMIN_KEY" "$DIRECTORY_ADMIN_KEY_VALUE" "Admin key for Trust Directory"
else
    echo "⏭️  Skipped DIRECTORY_ADMIN_KEY"
    echo ""
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Secret Manager setup complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Next steps:"
echo "   1. Update Cloud Run service 'natp' to use AGENT_API_KEY secret"
echo "   2. Update any services using the old exposed keys"
echo "   3. Test the new configuration"
echo "   4. Invalidate/delete the old exposed keys"
echo ""
echo "To configure Cloud Run to use the secret, run:"
echo ""
echo "gcloud run services update natp \\"
echo "  --project=$PROJECT_ID \\"
echo "  --region=$REGION \\"
echo "  --update-secrets=AGENT_API_KEY=AGENT_API_KEY:latest"
echo ""
