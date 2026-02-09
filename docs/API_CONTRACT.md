# Amarktai Network - API Contract

**Generated:** audit_repo.py
**Date:** 2026-02-07 20:40:32

## Backend Endpoints

Total: 346 endpoints

| Method | Path | Auth | Function | File |
|--------|------|------|----------|------|
| DELETE | `/addresses/{address_id}` | ✓ | `delete_withdrawal_address` | routes/wallet_addresses.py |
| DELETE | `/alerts/clear` | ✓ | `clear_alerts` | routes/alerts.py |
| DELETE | `/api-keys/{provider}` | ✓ | `compat_api_keys_delete` | routes/compat.py |
| DELETE | `/chat/history` | ✓ | `clear_chat_history` | routes/ai_chat.py |
| DELETE | `/users/{user_id}` | ✓ | `delete_user` | routes/admin_endpoints.py |
| DELETE | `/{address_id}` | ✓ | `delete_my_whitelist_address` | routes/user_whitelist.py |
| DELETE | `/{address_id}` |  | `delete_whitelist_address` | routes/admin_whitelist.py |
| DELETE | `/{bot_id}` | ✓ | `delete_bot` | routes/bot_lifecycle.py |
| DELETE | `/{countdown_id}` | ✓ | `delete_countdown` | routes/user_countdowns.py |
| DELETE | `/{provider}` | ✓ | `delete_key` | routes/keys.py |
| GET | `/` | ✓ | `get_user_countdowns` | routes/user_countdowns.py |
| GET | `/addresses/list` | ✓ | `list_withdrawal_addresses` | routes/wallet_addresses.py |
| GET | `/admin/addresses/pending` | ✓ | `get_pending_address_approvals` | routes/wallet_addresses.py |
| GET | `/admin/pending-approvals` | ✓ | `get_pending_approvals` | routes/wallet_hub.py |
| GET | `/admin/reinvest/status` | ✓ | `get_reinvestment_status` | routes/daily_report.py |
| GET | `/admin/transfers/pending` | ✓ | `list_pending_approvals` | routes/wallet_transfers_enhanced.py |
| GET | `/advanced/decisions/recent` | ✓ | `get_recent_decisions` | routes/compatibility_endpoints.py |
| GET | `/ai/health` | ✓ | `ai_health_check` | routes/phase6_endpoints.py |
| GET | `/ai/insights` | ✓ | `get_ai_insights` | routes/compatibility_endpoints.py |
| GET | `/alerts` | ✓ | `get_alerts` | routes/alerts.py |
| GET | `/all` |  | `list_all_whitelist_addresses` | routes/admin_whitelist.py |
| GET | `/analytics/performance` | ✓ | `compat_analytics_performance` | routes/compat.py |
| GET | `/api-keys/list` | ✓ | `compat_api_keys_list` | routes/compat.py |
| GET | `/api/dashboard/overview` | ✓ | `get_dashboard_overview` | routes/dashboard_overview.py |
| GET | `/api/overview/snapshot` | ✓ | `get_overview_snapshot` | routes/dashboard_overview.py |
| GET | `/api/risk/daily-loss-lock` | ✓ | `get_daily_loss_lock_status` | routes/risk_management.py |
| GET | `/approvals` | ✓ | `get_approvals_diagnostics` | routes/diagnostics.py |
| GET | `/audit/compliance-report` | ✓ | `get_compliance_report` | routes/phase8_endpoints.py |
| GET | `/audit/critical` | ✓ | `get_critical_events` | routes/phase8_endpoints.py |
| GET | `/audit/events` | ✓ | `get_audit_events` | routes/admin_endpoints.py |
| GET | `/audit/statistics` | ✓ | `get_audit_statistics` | routes/phase8_endpoints.py |
| GET | `/audit/trail` | ✓ | `get_audit_trail` | routes/phase8_endpoints.py |
| GET | `/auth/me` | ✓ | `get_current_user_profile` | routes/auth.py |
| GET | `/auth/profile` | ✓ | `get_profile` | routes/auth.py |
| GET | `/auto-spawn` | ✓ | `get_auto_spawn_status` | routes/diagnostics.py |
| GET | `/autopilot-check` | ✓ | `autopilot_functionality_check` | routes/diagnostics.py |
| GET | `/autopilot/status` | ✓ | `get_autopilot_status` | routes/autopilot_control.py |
| GET | `/balance/summary` | ✓ | `get_balance_summary` | routes/wallet_transfers.py |
| GET | `/balances` | ✓ | `get_all_balances` | routes/wallet_hub.py |
| GET | `/balances-legacy` | ✓ | `get_wallet_balances_legacy` | routes/wallet_endpoints.py |
| GET | `/bot/{bot_id}/injections` | ✓ | `get_bot_injections` | routes/capital_tracking_endpoints.py |
| GET | `/bot/{bot_id}/real-profit` | ✓ | `get_bot_real_profit` | routes/capital_tracking_endpoints.py |
| GET | `/bots` | ✓ | `get_all_bots_admin` | routes/admin_endpoints.py |
| GET | `/bots` | ✓ | `get_training_quarantine_bots` | routes/training_quarantine.py |
| GET | `/bots/reconcile` | ✓ | `reconcile_bots` | routes/admin_endpoints.py |
| GET | `/bots/{bot_id}/status` | ✓ | `get_bot_status` | routes/bot_control.py |
| GET | `/build` |  | `get_build_info_legacy` | routes/build_info.py |
| GET | `/can-pay/{amount_fet}` |  | `check_can_make_payment` | routes/payment_agent_endpoints.py |
| GET | `/capital/allocation-report` | ✓ | `get_allocation_report` | routes/phase5_endpoints.py |
| GET | `/capital/bot/{bot_id}/optimal` | ✓ | `get_optimal_allocation` | routes/phase5_endpoints.py |
| GET | `/capital_breakdown` | ✓ | `get_capital_breakdown` | routes/analytics_api.py |
| GET | `/chat/history` | ✓ | `get_chat_history` | routes/ai_chat.py |
| GET | `/circuit-breaker/global-status` | ✓ | `get_global_circuit_breaker_status` | routes/phase5_endpoints.py |
| GET | `/circuit-breaker/history` | ✓ | `get_circuit_breaker_history` | routes/order_endpoints.py |
| GET | `/circuit-breaker/status` | ✓ | `get_circuit_breaker_status` | routes/order_endpoints.py |
| GET | `/circuit-breaker/status/{bot_id}` | ✓ | `get_circuit_breaker_status` | routes/phase5_endpoints.py |
| GET | `/compat/status` | ✓ | `compat_layer_status` | routes/compat.py |
| GET | `/config` | ✓ | `get_limits_config` | routes/limits_management.py |
| GET | `/config` | ✓ | `get_quarantine_config` | routes/quarantine.py |
| GET | `/countdown` | ✓ | `get_countdown_to_target` | routes/analytics_api.py |
| GET | `/countdown/status` | ✓ | `get_countdown_status` | routes/ledger_endpoints.py |
| GET | `/daily-summary` | ✓ | `get_daily_summary` | routes/chat_enhanced.py |
| GET | `/daily/config` | ✓ | `get_report_config` | routes/daily_report.py |
| GET | `/dashboard/stats` | ✓ | `get_admin_dashboard_stats` | routes/admin_enhanced.py |
| GET | `/decision-trace/latest` | ✓ | `get_decision_trace_latest` | routes/dashboard_aliases.py |
| GET | `/diagnostics` | ✓ | `get_all_bots_diagnostics` | routes/bot_lifecycle.py |
| GET | `/drawdown` | ✓ | `get_drawdown_analysis` | routes/analytics_api.py |
| GET | `/email-status` | ✓ | `get_email_status` | routes/notifications.py |
| GET | `/email-status` | ✓ | `get_email_status` | routes/diagnostics.py |
| GET | `/email/report-preview` | ✓ | `preview_daily_report` | routes/phase8_endpoints.py |
| GET | `/emergency-gates` | ✓ | `get_emergency_gates_status` | routes/emergency_stop_endpoints.py |
| GET | `/emergency-stop/status` | ✓ | `get_emergency_stop_status` | routes/emergency_stop_endpoints.py |
| GET | `/equity` | ✓ | `get_equity_curve` | routes/analytics_api.py |
| GET | `/events` | ✓ | `realtime_events` | routes/realtime.py |
| GET | `/exchange-comparison` | ✓ | `get_exchange_comparison` | routes/analytics_api.py |
| GET | `/funding-plans` | ✓ | `get_funding_plans` | routes/wallet_endpoints.py |
| GET | `/funding-plans/{plan_id}` | ✓ | `get_funding_plan` | routes/wallet_endpoints.py |
| GET | `/fusion/{symbol}` | ✓ | `get_fusion_signal` | routes/advanced_trading_endpoints.py |
| GET | `/gates` | ✓ | `get_system_gates` | routes/system.py |
| GET | `/health` | ✓ | `health_check` | routes/system_status.py |
| GET | `/health` | ✓ | `get_wallet_health` | routes/wallet_hub.py |
| GET | `/health` | ✓ | `platform_health` | routes/platforms.py |
| GET | `/health` | ✓ | `get_limits_health` | routes/limits_management.py |
| GET | `/health-detail` | ✓ | `get_health_detail` | routes/diagnostics.py |
| GET | `/history` | ✓ | `get_execution_quality_history` | routes/execution_quality.py |
| GET | `/history` | ✓ | `get_training_history` | routes/training.py |
| GET | `/history` | ✓ | `get_backtest_history` | routes/backtesting.py |
| GET | `/history` | ✓ | `get_quarantine_history` | routes/quarantine.py |
| GET | `/indicators` |  | `get_health_indicators` | routes/system_health_endpoints.py |
| GET | `/info` |  | `get_build_info` | routes/build_info.py |
| GET | `/insights` | ✓ | `get_trading_insights` | routes/analytics_api.py |
| GET | `/latest` | ✓ | `get_latest_decisions` | routes/decision_trace.py |
| GET | `/learning/analyze/{bot_id}` | ✓ | `analyze_bot_performance` | routes/phase6_endpoints.py |
| GET | `/ledger/audit-trail` | ✓ | `get_audit_trail` | routes/ledger_endpoints.py |
| GET | `/ledger/fills` | ✓ | `get_fills` | routes/ledger_endpoints.py |
| GET | `/ledger/reconcile` | ✓ | `reconcile_ledger` | routes/ledger_endpoints.py |
| GET | `/ledger/summary` | ✓ | `compat_ledger_summary` | routes/compat.py |
| GET | `/ledger/verify-integrity` | ✓ | `verify_ledger_integrity` | routes/ledger_endpoints.py |
| GET | `/limiter/bot/{bot_id}/status` | ✓ | `get_bot_trade_status` | routes/phase5_endpoints.py |
| GET | `/limits` | ✓ | `compat_limits_root` | routes/compat.py |
| GET | `/limits` | ✓ | `get_trade_limits` | routes/system_limits.py |
| GET | `/limits/bot/{bot_id}` | ✓ | `get_bot_limits` | routes/system_limits.py |
| GET | `/limits/exchange/{exchange}` | ✓ | `get_exchange_limits` | routes/system_limits.py |
| GET | `/limits/status` | ✓ | `get_limits_status` | routes/order_endpoints.py |
| GET | `/list` | ✓ | `list_user_keys` | routes/keys.py |
| GET | `/live` | ✓ | `get_live_trades` | routes/trades.py |
| GET | `/live-bay` | ✓ | `get_live_training_bay` | routes/training.py |
| GET | `/live-eligibility` | ✓ | `get_live_eligibility` | routes/live_trading_gate.py |
| GET | `/macro/signal` | ✓ | `get_macro_signal` | routes/advanced_trading_endpoints.py |
| GET | `/macro/summary` | ✓ | `get_macro_summary` | routes/advanced_trading_endpoints.py |
| GET | `/metrics` | ✓ | `get_trade_metrics` | routes/trades.py |
| GET | `/metrics/summary` | ✓ | `get_metrics_summary` | routes/dashboard_aliases.py |
| GET | `/ml/predict` | ✓ | `ml_predict_query_params` | routes/compatibility_endpoints.py |
| GET | `/mode` | ✓ | `get_mode` | routes/system_mode.py |
| GET | `/mode/readiness` | ✓ | `check_readiness` | routes/system_mode.py |
| GET | `/my-addresses` | ✓ | `get_my_whitelist_addresses` | routes/user_whitelist.py |
| GET | `/ofi/stats/{symbol}` | ✓ | `get_ofi_stats` | routes/advanced_trading_endpoints.py |
| GET | `/ofi/{symbol}` | ✓ | `get_ofi_signal` | routes/advanced_trading_endpoints.py |
| GET | `/orders` | ✓ | `compat_orders_root` | routes/compat.py |
| GET | `/orders/pending` | ✓ | `get_pending_orders` | routes/order_endpoints.py |
| GET | `/orders/{order_id}/status` | ✓ | `get_order_status` | routes/order_endpoints.py |
| GET | `/overview` | ✓ | `get_admin_overview` | routes/admin_endpoints.py |
| GET | `/overview` | ✓ | `get_overview` | routes/trading.py |
| GET | `/paper-status` | ✓ | `get_paper_trading_status` | routes/diagnostics.py |
| GET | `/paper-trading` |  | `get_paper_trading_status` | routes/system_health_endpoints.py |
| GET | `/pending` |  | `list_pending_whitelist_approvals` | routes/admin_whitelist.py |
| GET | `/performance-ranking` | ✓ | `get_performance_ranking` | routes/genetic_algorithm.py |
| GET | `/performance_summary` | ✓ | `get_performance_summary` | routes/analytics_api.py |
| GET | `/ping` |  | `ping` | routes/system_health_endpoints.py |
| GET | `/ping` |  | `health_ping` | routes/health.py |
| GET | `/ping` | ✓ | `system_ping` | routes/system.py |
| GET | `/ping` | ✓ | `trades_ping` | routes/trades.py |
| GET | `/platforms` | ✓ | `get_platforms` | routes/system.py |
| GET | `/pnl_timeseries` | ✓ | `get_pnl_timeseries` | routes/analytics_api.py |
| GET | `/portfolio/summary` | ✓ | `get_portfolio_summary` | routes/ledger_endpoints.py |
| GET | `/preflight` |  | `preflight_check` | routes/health.py |
| GET | `/prices` | ✓ | `get_market_prices` | routes/market_api.py |
| GET | `/profits` | ✓ | `get_profits` | routes/ledger_endpoints.py |
| GET | `/providers` | ✓ | `get_providers_list` | routes/keys.py |
| GET | `/quarantined` | ✓ | `get_quarantined_bots` | routes/limits_management.py |
| GET | `/queue` | ✓ | `get_training_queue` | routes/training.py |
| GET | `/readiness` | ✓ | `platform_readiness` | routes/platforms.py |
| GET | `/ready` |  | `health_ready` | routes/health.py |
| GET | `/realtime` | ✓ | `get_realtime_status` | routes/diagnostics.py |
| GET | `/realtime-smoke` | ✓ | `realtime_smoke_test` | routes/diagnostics.py |
| GET | `/recent` | ✓ | `get_recent_trades` | routes/trades.py |
| GET | `/regime` | ✓ | `get_market_regime` | routes/diagnostics.py |
| GET | `/regime/summary` | ✓ | `get_regime_summary` | routes/advanced_trading_endpoints.py |
| GET | `/regime/{symbol}` | ✓ | `get_regime_for_symbol` | routes/advanced_trading_endpoints.py |
| GET | `/report/{bot_id}` | ✓ | `get_bot_training_report` | routes/training_quarantine.py |
| GET | `/reports` | ✓ | `get_training_reports` | routes/training_quarantine.py |
| GET | `/required-capital` | ✓ | `get_required_capital` | routes/wallet_endpoints.py |
| GET | `/requirements` | ✓ | `get_capital_requirements` | routes/wallet_endpoints.py |
| GET | `/reserves` | ✓ | `get_reserves_diagnostics` | routes/diagnostics.py |
| GET | `/resources/users` | ✓ | `get_user_resource_usage` | routes/admin_endpoints.py |
| GET | `/self-healing/health` | ✓ | `get_self_healing_health` | routes/advanced_trading_endpoints.py |
| GET | `/sentiment/summary` | ✓ | `get_sentiment_summary` | routes/advanced_trading_endpoints.py |
| GET | `/sentiment/{coin}` | ✓ | `get_sentiment_signal` | routes/advanced_trading_endpoints.py |
| GET | `/since-last-login` | ✓ | `get_since_last_login` | routes/system_status.py |
| GET | `/staggerer/queue-status` | ✓ | `get_queue_status` | routes/phase5_endpoints.py |
| GET | `/staggerer/schedule` | ✓ | `get_trade_schedule` | routes/phase5_endpoints.py |
| GET | `/stats` | ✓ | `get_system_stats` | routes/admin_endpoints.py |
| GET | `/stats` |  | `get_payment_statistics` | routes/payment_agent_endpoints.py |
| GET | `/stats` | ✓ | `get_trade_stats` | routes/trades.py |
| GET | `/status` | ✓ | `get_advanced_system_status` | routes/advanced_trading_endpoints.py |
| GET | `/status` | ✓ | `get_keys_status` | routes/keys.py |
| GET | `/status` | ✓ | `get_system_status` | routes/system_status.py |
| GET | `/status` | ✓ | `get_execution_quality_status` | routes/execution_quality.py |
| GET | `/status` | ✓ | `get_bots_status` | routes/bot_lifecycle.py |
| GET | `/status` |  | `get_payment_agent_status` | routes/payment_agent_endpoints.py |
| GET | `/status` | ✓ | `get_` | routes/two_factor_auth.py |
| GET | `/status` | ✓ | `get_platform_status` | routes/platforms.py |
| GET | `/status` | ✓ | `get_treasury_status` | routes/treasury.py |
| GET | `/status` | ✓ | `get_evolution_status` | routes/genetic_algorithm.py |
| GET | `/status` | ✓ | `get_quarantine_status` | routes/quarantine.py |
| GET | `/summary` | ✓ | `get_platforms_summary` | routes/platforms.py |
| GET | `/summary` | ✓ | `get_analytics_summary` | routes/analytics_api.py |
| GET | `/system-health` | ✓ | `system_health_check` | routes/diagnostics.py |
| GET | `/system-stats` | ✓ | `get_system_stats_extended` | routes/admin_endpoints.py |
| GET | `/system/logs` | ✓ | `get_system_logs` | routes/admin_endpoints.py |
| GET | `/system/processes` | ✓ | `get_process_health` | routes/admin_endpoints.py |
| GET | `/system/resources` | ✓ | `get_system_resources` | routes/admin_endpoints.py |
| GET | `/trace` | ✓ | `get_decision_trace` | routes/decision_trace.py |
| GET | `/trade-cadence` | ✓ | `get_trade_cadence` | routes/metrics_api.py |
| GET | `/trades` | ✓ | `compat_trades_root` | routes/compat.py |
| GET | `/transactions` | ✓ | `get_wallet_transactions` | routes/wallet_hub.py |
| GET | `/transfer-path` | ✓ | `transfer_path_diagnostic` | routes/diagnostics.py |
| GET | `/transfers` | ✓ | `list_transfers` | routes/wallet_transfers_enhanced.py |
| GET | `/transfers` | ✓ | `get_transfers` | routes/wallet_transfers.py |
| GET | `/transfers` | ✓ | `get_transfer_diagnostics` | routes/diagnostics.py |
| GET | `/transfers/{transfer_id}` | ✓ | `get_transfer_details` | routes/wallet_transfers_enhanced.py |
| GET | `/usage` | ✓ | `get_limits_usage` | routes/limits_management.py |
| GET | `/user-storage` | ✓ | `get_user_storage_usage` | routes/admin_endpoints.py |
| GET | `/user/injections` | ✓ | `get_user_injections` | routes/capital_tracking_endpoints.py |
| GET | `/user/real-profit` | ✓ | `get_user_real_profit` | routes/capital_tracking_endpoints.py |
| GET | `/users` | ✓ | `get_all_users` | routes/admin_endpoints.py |
| GET | `/users/list` | ✓ | `get_users_list` | routes/admin_enhanced.py |
| GET | `/users/{user_id}` | ✓ | `get_user_details` | routes/admin_endpoints.py |
| GET | `/users/{user_id}/api-keys` | ✓ | `get_user_api_keys_status` | routes/admin_endpoints.py |
| GET | `/users/{user_id}/bots` | ✓ | `get_user_bots_detailed` | routes/admin_enhanced.py |
| GET | `/wallet-status` | ✓ | `get_wallet_status` | routes/diagnostics.py |
| GET | `/welcome` | ✓ | `get_welcome_message` | routes/chat_enhanced.py |
| GET | `/whale-flow/summary` | ✓ | `whale_flow_summary_alias` | routes/dashboard_aliases.py |
| GET | `/whale-flow/{coin}` | ✓ | `whale_flow_coin_alias` | routes/dashboard_aliases.py |
| GET | `/whale/summary` | ✓ | `get_whale_summary` | routes/advanced_trading_endpoints.py |
| GET | `/whale/{coin}` | ✓ | `get_whale_signal` | routes/advanced_trading_endpoints.py |
| GET | `/win_rate` | ✓ | `get_win_rate_stats` | routes/analytics_api.py |
| GET | `/ws` | ✓ | `websocket_diagnostics` | routes/diagnostics.py |
| GET | `/{bot_id}/diagnostics` | ✓ | `get_bot_diagnostics` | routes/bot_lifecycle.py |
| GET | `/{bot_id}/status` | ✓ | `get_bot_detailed_status` | routes/bot_lifecycle.py |
| GET | `/{platform}/bots` | ✓ | `get_platform_bots` | routes/platforms.py |
| GET | `/{provider}` | ✓ | `get_key` | routes/keys.py |
| GET | `/{run_id}/status` | ✓ | `get_training_status` | routes/training.py |
| PATCH | `/transfer/{transfer_id}/status` | ✓ | `update_transfer_status` | routes/wallet_transfers.py |
| POST | `/` | ✓ | `create_countdown` | routes/user_countdowns.py |
| POST | `/action/execute` | ✓ | `execute_ai_action` | routes/ai_chat.py |
| POST | `/addresses/add` | ✓ | `add_withdrawal_address` | routes/wallet_addresses.py |
| POST | `/admin/addresses/approve` | ✓ | `approve_withdrawal_address` | routes/wallet_addresses.py |
| POST | `/admin/addresses/reject` | ✓ | `reject_withdrawal_address` | routes/wallet_addresses.py |
| POST | `/admin/approve/{transfer_id}` | ✓ | `admin_approve_transfer` | routes/wallet_hub.py |
| POST | `/admin/reinvest/trigger` | ✓ | `trigger_manual_reinvestment` | routes/daily_report.py |
| POST | `/admin/reject/{transfer_id}` | ✓ | `admin_reject_transfer` | routes/wallet_hub.py |
| POST | `/admin/transfers/{transfer_id}/approve` | ✓ | `approve_transfer` | routes/wallet_transfers_enhanced.py |
| POST | `/admin/transfers/{transfer_id}/reject` | ✓ | `reject_transfer` | routes/wallet_transfers_enhanced.py |
| POST | `/ai/analyze-trade` | ✓ | `analyze_trade_opportunity` | routes/phase6_endpoints.py |
| POST | `/ai/market-insight` | ✓ | `generate_market_insight` | routes/phase6_endpoints.py |
| POST | `/ai/strategy-analysis/{bot_id}` | ✓ | `deep_strategy_analysis` | routes/phase6_endpoints.py |
| POST | `/alerts/ack/{alert_id}` | ✓ | `acknowledge_alert` | routes/alerts.py |
| POST | `/api-keys/save` | ✓ | `compat_api_keys_save` | routes/compat.py |
| POST | `/api-keys/test` | ✓ | `compat_api_keys_test` | routes/compat.py |
| POST | `/api/admin/reset-risk-lock` | ✓ | `admin_reset_risk_lock` | routes/risk_management.py |
| POST | `/api/admin/reset-user-data` | ✓ | `reset_user_data` | routes/admin_start_fresh.py |
| POST | `/api/admin/start-fresh` | ✓ | `start_fresh` | routes/admin_start_fresh.py |
| POST | `/api/bots/reset` | ✓ | `user_self_reset_bots` | routes/admin_start_fresh.py |
| POST | `/api/risk/daily-loss-lock/reset` | ✓ | `reset_daily_loss_lock` | routes/risk_management.py |
| POST | `/api/risk/resume-all` | ✓ | `resume_all_bots_with_risk_check` | routes/risk_management.py |
| POST | `/auth/login` | ✓ | `login` | routes/auth.py |
| POST | `/auth/register` | ✓ | `register` | routes/auth.py |
| POST | `/auto-evolve/disable` | ✓ | `disable_auto_evolution` | routes/genetic_algorithm.py |
| POST | `/auto-evolve/enable` | ✓ | `enable_auto_evolution` | routes/genetic_algorithm.py |
| POST | `/autopilot/disable` | ✓ | `disable_autopilot` | routes/autopilot_control.py |
| POST | `/autopilot/enable` | ✓ | `enable_autopilot` | routes/autopilot_control.py |
| POST | `/autopilot/toggle` | ✓ | `toggle_autopilot` | routes/autopilot_control.py |
| POST | `/bots/clamp-caps` | ✓ | `clamp_bot_caps` | routes/admin_endpoints.py |
| POST | `/bots/{bot_id}/exchange` | ✓ | `change_bot_exchange` | routes/admin_endpoints.py |
| POST | `/bots/{bot_id}/mode` | ✓ | `change_bot_mode` | routes/admin_endpoints.py |
| POST | `/bots/{bot_id}/pause` | ✓ | `pause_bot` | routes/admin_endpoints.py |
| POST | `/bots/{bot_id}/pause` | ✓ | `pause_bot` | routes/bot_control.py |
| POST | `/bots/{bot_id}/restart` | ✓ | `restart_bot` | routes/admin_endpoints.py |
| POST | `/bots/{bot_id}/resume` | ✓ | `resume_bot` | routes/admin_endpoints.py |
| POST | `/bots/{bot_id}/resume` | ✓ | `resume_bot` | routes/bot_control.py |
| POST | `/bots/{bot_id}/start` | ✓ | `start_bot` | routes/bot_control.py |
| POST | `/capital/rebalance` | ✓ | `rebalance_capital` | routes/phase5_endpoints.py |
| POST | `/change-password` | ✓ | `change_admin_password` | routes/admin_endpoints.py |
| POST | `/chat` | ✓ | `ai_chat` | routes/ai_chat.py |
| POST | `/chat/clear` | ✓ | `clear_chat_history_post` | routes/ai_chat.py |
| POST | `/chat/greeting` | ✓ | `get_daily_greeting` | routes/ai_chat.py |
| POST | `/circuit-breaker-alert` | ✓ | `send_circuit_breaker_alert_manual` | routes/notifications.py |
| POST | `/circuit-breaker/check` | ✓ | `check_circuit_breaker` | routes/limits_management.py |
| POST | `/circuit-breaker/reset` | ✓ | `reset_circuit_breaker` | routes/order_endpoints.py |
| POST | `/clear` | ✓ | `clear_chat_history` | routes/chat_enhanced.py |
| POST | `/crossover` | ✓ | `crossover_bots` | routes/genetic_algorithm.py |
| POST | `/daily/send-all` | ✓ | `send_all_reports` | routes/daily_report.py |
| POST | `/daily/send-test` | ✓ | `send_test_report` | routes/daily_report.py |
| POST | `/disable` | ✓ | `disable_` | routes/two_factor_auth.py |
| POST | `/email/send-daily-report` | ✓ | `send_daily_report` | routes/phase8_endpoints.py |
| POST | `/email/test` | ✓ | `test_email` | routes/phase8_endpoints.py |
| POST | `/emergency-resume` | ✓ | `emergency_resume` | routes/emergency_stop_endpoints.py |
| POST | `/emergency-stop` | ✓ | `activate_emergency_stop` | routes/emergency_stop_endpoints.py |
| POST | `/emergency-stop/disable` | ✓ | `deactivate_emergency_stop` | routes/emergency_stop_endpoints.py |
| POST | `/enroll` | ✓ | `enroll_` | routes/two_factor_auth.py |
| POST | `/evolve` | ✓ | `evolve_bots` | routes/genetic_algorithm.py |
| POST | `/factory-reset` | ✓ | `factory_reset_keep_admin` | routes/admin_endpoints.py |
| POST | `/funding-plans/{plan_id}/cancel` | ✓ | `cancel_funding_plan` | routes/wallet_endpoints.py |
| POST | `/fusion/portfolio` | ✓ | `get_portfolio_fusion` | routes/advanced_trading_endpoints.py |
| POST | `/history` |  | `get_payment_history` | routes/payment_agent_endpoints.py |
| POST | `/initialize` | ✓ | `initialize_capital_tracking` | routes/capital_tracking_endpoints.py |
| POST | `/learning/apply-adjustments/{bot_id}` | ✓ | `apply_bot_adjustments` | routes/phase6_endpoints.py |
| POST | `/learning/generate-adjustments/{bot_id}` | ✓ | `generate_bot_adjustments` | routes/phase6_endpoints.py |
| POST | `/learning/run-cycle` | ✓ | `run_learning_cycle` | routes/phase6_endpoints.py |
| POST | `/ledger/funding` | ✓ | `record_funding` | routes/ledger_endpoints.py |
| POST | `/log` | ✓ | `log_decision` | routes/decision_trace.py |
| POST | `/make-payment` |  | `make_payment` | routes/payment_agent_endpoints.py |
| POST | `/message` | ✓ | `chat_message` | routes/chat_endpoints.py |
| POST | `/migrate-api-keys` | ✓ | `migrate_api_keys_encryption` | routes/admin_endpoints.py |
| POST | `/mode/switch` | ✓ | `switch_mode` | routes/system_mode.py |
| POST | `/mutate/{bot_id}` | ✓ | `mutate_bot` | routes/genetic_algorithm.py |
| POST | `/ofi/snapshot` | ✓ | `add_ofi_snapshot` | routes/advanced_trading_endpoints.py |
| POST | `/optimize` | ✓ | `optimize_strategy` | routes/backtesting.py |
| POST | `/orders/submit` | ✓ | `submit_order` | routes/order_endpoints.py |
| POST | `/pause-all` | ✓ | `pause_all_bots` | routes/bot_lifecycle.py |
| POST | `/pay-alpha-signal` |  | `pay_for_alpha_signal` | routes/payment_agent_endpoints.py |
| POST | `/pay-data-feed` |  | `pay_for_data_feed` | routes/payment_agent_endpoints.py |
| POST | `/profits/reinvest` | ✓ | `reinvest_profits` | routes/compatibility_endpoints.py |
| POST | `/quarantine/reset/{bot_id}` | ✓ | `reset_quarantined_bot` | routes/limits_management.py |
| POST | `/rebalance` | ✓ | `rebalance_treasury` | routes/treasury.py |
| POST | `/regime/update-price` | ✓ | `update_regime_price` | routes/advanced_trading_endpoints.py |
| POST | `/request` | ✓ | `request_whitelist_address` | routes/user_whitelist.py |
| POST | `/request-live` | ✓ | `request_live_trading` | routes/live_trading_gate.py |
| POST | `/request-testnet-funds` |  | `request_testnet_funds` | routes/payment_agent_endpoints.py |
| POST | `/risk/check-trade` | ✓ | `check_trade_risk` | routes/phase5_endpoints.py |
| POST | `/run` | ✓ | `run_backtest` | routes/backtesting.py |
| POST | `/save` | ✓ | `save_key` | routes/keys.py |
| POST | `/session/end` | ✓ | `end_chat_session` | routes/chat_enhanced.py |
| POST | `/start` | ✓ | `start_training` | routes/training.py |
| POST | `/start-paper-learning` | ✓ | `start_paper_learning` | routes/live_trading_gate.py |
| POST | `/sweep` | ✓ | `sweep_excess_capital` | routes/treasury.py |
| POST | `/system/mode/toggle` | ✓ | `toggle_system_mode` | routes/trading.py |
| POST | `/test` | ✓ | `test_key` | routes/keys.py |
| POST | `/test-email` | ✓ | `send_test_email` | routes/notifications.py |
| POST | `/transfer` | ✓ | `transfer_funds` | routes/wallet_hub.py |
| POST | `/transfer-manual` | ✓ | `create_transfer_manual` | routes/wallet_endpoints.py |
| POST | `/transfers` | ✓ | `create_transfer` | routes/wallet_transfers.py |
| POST | `/transfers/create` | ✓ | `create_transfer_with_state_machine` | routes/wallet_transfers_enhanced.py |
| POST | `/transfers/{transfer_id}/cancel` | ✓ | `cancel_transfer` | routes/wallet_transfers_enhanced.py |
| POST | `/unlock` | ✓ | `unlock_admin_panel` | routes/admin_endpoints.py |
| POST | `/users/{user_id}/block` | ✓ | `block_user` | routes/admin_endpoints.py |
| POST | `/users/{user_id}/logout` | ✓ | `force_logout_user` | routes/admin_endpoints.py |
| POST | `/users/{user_id}/reset` | ✓ | `reset_user_account` | routes/admin_endpoints.py |
| POST | `/users/{user_id}/reset-password` | ✓ | `reset_user_password` | routes/admin_endpoints.py |
| POST | `/users/{user_id}/unblock` | ✓ | `unblock_user` | routes/admin_endpoints.py |
| POST | `/validate` | ✓ | `validate_` | routes/two_factor_auth.py |
| POST | `/verify` | ✓ | `verify_` | routes/two_factor_auth.py |
| POST | `/welcome-email` | ✓ | `send_welcome_email_manual` | routes/notifications.py |
| POST | `/{address_id}/approve` |  | `approve_whitelist_address` | routes/admin_whitelist.py |
| POST | `/{address_id}/reject` |  | `reject_whitelist_address` | routes/admin_whitelist.py |
| POST | `/{bot_id}/cooldown` | ✓ | `set_bot_cooldown` | routes/bot_lifecycle.py |
| POST | `/{bot_id}/fail` | ✓ | `fail_training` | routes/training.py |
| POST | `/{bot_id}/pause` | ✓ | `pause_bot` | routes/bot_lifecycle.py |
| POST | `/{bot_id}/promote` | ✓ | `promote_bot_from_training` | routes/training.py |
| POST | `/{bot_id}/resume` | ✓ | `resume_bot` | routes/bot_lifecycle.py |
| POST | `/{bot_id}/start` | ✓ | `start_bot` | routes/bot_lifecycle.py |
| POST | `/{bot_id}/stop` | ✓ | `stop_bot` | routes/bot_lifecycle.py |
| POST | `/{bot_id}/trading-enabled` | ✓ | `toggle_bot_trading` | routes/bot_lifecycle.py |
| POST | `/{bot_id}/unpause` | ✓ | `resume_bot` | routes/bot_lifecycle.py |
| POST | `/{provider}` | ✓ | `save_key_provider_path` | routes/keys.py |
| POST | `/{run_id}/stop` | ✓ | `stop_training` | routes/training.py |
| PUT | `/auth/profile` | ✓ | `update_profile` | routes/auth.py |
| PUT | `/mode` | ✓ | `toggle_mode` | routes/system_mode.py |
| PUT | `/users/{user_id}/block` | ✓ | `block_user_put` | routes/admin_endpoints.py |
| PUT | `/users/{user_id}/password` | ✓ | `reset_user_password_put` | routes/admin_endpoints.py |
| PUT | `/{bot_id}/pause` | ✓ | `pause_bot` | routes/bot_lifecycle.py |
| PUT | `/{bot_id}/resume` | ✓ | `resume_bot` | routes/bot_lifecycle.py |
| PUT | `/{bot_id}/trading-enabled` | ✓ | `toggle_bot_trading` | routes/bot_lifecycle.py |
| PUT | `/{bot_id}/unpause` | ✓ | `resume_bot` | routes/bot_lifecycle.py |
| PUT | `/{countdown_id}` | ✓ | `update_countdown` | routes/user_countdowns.py |

## Frontend API Calls

Total: 0 API calls

| Path | Files |
|------|-------|

## Contract Validation

The following checks should be performed:

1. **No 404s:** Every frontend API call should have a matching backend endpoint
2. **Consistent paths:** API keys should use single canonical route set
3. **Auth consistency:** Protected endpoints should require authentication
4. **Response schemas:** Backend responses should match frontend expectations

