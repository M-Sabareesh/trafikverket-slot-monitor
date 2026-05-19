#!/bin/bash
# Trigger the monitor workflow via GitHub API
# 
# Usage:
#   ./trigger_workflow.sh
#
# This can be called by an external cron service for reliable scheduling.
# Set up on cron-job.org, easycron.com, or a local crontab.
#
# Required: GH_PAT environment variable with a GitHub Personal Access Token
# that has 'repo' scope.

REPO="M-Sabareesh/trafikverket-slot-monitor"

if [ -z "$GH_PAT" ]; then
    echo "Error: GH_PAT environment variable not set"
    echo "Create a token at: https://github.com/settings/tokens"
    exit 1
fi

echo "Triggering workflow..."
curl -X POST \
    -H "Accept: application/vnd.github.v3+json" \
    -H "Authorization: token $GH_PAT" \
    "https://api.github.com/repos/$REPO/dispatches" \
    -d '{"event_type":"trigger-monitor"}'

echo "Done!"
