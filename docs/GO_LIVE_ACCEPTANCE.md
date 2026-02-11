# Go-Live Acceptance Checklist

All items below must pass before enabling live trading:

- [ ] User can login, create bot, start bot (paper), see trades appear, see PnL change.
- [ ] Pause/resume/restart works and shows reasons when blocked.
- [ ] Admin endpoints return 200 and overview stats match DB.
- [ ] AI chat returns a response when OpenAI key is configured, and returns a clear error if not.
- [ ] Realtime SSE/WS connects and streams at least one event.
- [ ] scripts/go_live_verify.sh runs both interactive and non-interactive.
