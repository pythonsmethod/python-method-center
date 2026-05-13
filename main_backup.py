# main_backup.py
# BACKUP of main.py created before PHASE 3.1A pipeline wire-in
# Date: 2026-05-13
# DO NOT DEPLOY THIS FILE DIRECTLY
# This is a reference backup only.
# If rollback needed: copy contents to main.py
#
# Original main.py: FastAPI + SendPulse + Claude AI Agents + Stripe
# Deployment: Railway
# Message flow: SendPulse webhook -> process_message(contact_id, text) -> send_message()
#
# Key structure:
#   POST /webhook      -> extract_event() -> process_message() -> send_message()
#   POST /stripe-webhook -> on_payment_confirmed()
#   GET  /health       -> health check
#   GET  /documents/oferta -> serve PDF
#
# Imports: agents.process_message, agents.on_payment_confirmed, ai_router.health_check
# Sessions: dict stored in memory (sessions = {})
# Auth: STRIPE_WEBHOOK_SECRET, SENDPULSE_CLIENT_ID, SENDPULSE_CLIENT_SECRET
#
# To restore: git revert commit that modifies main.py, or copy this to main.py

# [ORIGINAL SOURCE PRESERVED IN GIT HISTORY]
# Git commit before this backup: 17d5ff85
# To retrieve: git show 17d5ff85:main.py
