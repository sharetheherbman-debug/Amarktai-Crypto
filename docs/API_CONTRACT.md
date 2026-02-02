# Amarktai Network - API Contract

**Generated:** audit_repo.py
**Date:** 2026-02-01 19:42:32

## Backend Endpoints

Total: 284 endpoints

| Method | Path | Auth | Function | File |
|--------|------|------|----------|------|
| DELETE | `/alerts/clear` | ✓ | `clear_alerts` | routes/alerts.py |
| DELETE | `/chat/history` | ✓ | `clear_chat_history` | routes/ai_chat.py |
| DELETE | `/users/{user_id}` | ✓ | `delete_user` | routes/admin_endpoints.py |
| DELETE | `/{bot_id}` | ✓ | `delete_bot` | routes/bot_lifecycle.py |
| DELETE | `/{countdown_id}` | ✓ | `delete_countdown` | routes/user_countdowns.py |
| DELETE | `/{provider}` | ✓ | `delete_key` | routes/keys.py |
| GET | `/` | ✓ | `get_user_countdowns` | routes/user_countdowns.py |
| GET | `/admin/reinvest/status` | ✓ | `get_reinvestment_status` | routes/daily_report.py |
| GET | `/advanced/decisions/recent` | ✓ | `get_recent_decisions` | routes/compatibility_endpoints.py |
| GET | `/ai/health` | ✓ | `ai_health_check` | routes/phase6_endpoints.py |
| GET | `/ai/insights` | ✓ | `get_ai_insights` | routes/compatibility_endpoints.py |
| GET | `/alerts` | ✓ | `get_alerts` | routes/alerts.py |
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
| GET | `/email/report-preview` | ✓ | `preview_daily_report` | routes/phase8_endpoints.py |
| GET | `/emergency-stop/status` | ✓ | `get_emergency_stop_status` | routes/emergency_stop_endpoints.py |
| GET | `/equity` | ✓ | `get_equity_curve` | routes/analytics_api.py |
| GET | `/events` | ✓ | `realtime_events` | routes/realtime.py |
| GET | `/exchange-comparison` | ✓ | `get_exchange_comparison` | routes/analytics_api.py |
| GET | `/funding-plans` | ✓ | `get_funding_plans` | routes/wallet_endpoints.py |
| GET | `/funding-plans/{plan_id}` | ✓ | `get_funding_plan` | routes/wallet_endpoints.py |
| GET | `/fusion/{symbol}` | ✓ | `get_fusion_signal` | routes/advanced_trading_endpoints.py |
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
| GET | `/ledger/verify-integrity` | ✓ | `verify_ledger_integrity` | routes/ledger_endpoints.py |
| GET | `/limiter/bot/{bot_id}/status` | ✓ | `get_bot_trade_status` | routes/phase5_endpoints.py |
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
| GET | `/ofi/stats/{symbol}` | ✓ | `get_ofi_stats` | routes/advanced_trading_endpoints.py |
| GET | `/ofi/{symbol}` | ✓ | `get_ofi_signal` | routes/advanced_trading_endpoints.py |
| GET | `/orders/pending` | ✓ | `get_pending_orders` | routes/order_endpoints.py |
| GET | `/orders/{order_id}/status` | ✓ | `get_order_status` | routes/order_endpoints.py |
| GET | `/overview` | ✓ | `get_overview` | routes/trading.py |
| GET | `/paper-status` | ✓ | `get_paper_trading_status` | routes/diagnostics.py |
| GET | `/paper-trading` |  | `get_paper_trading_status` | routes/system_health_endpoints.py |
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
| GET | `/requirements` | ✓ | `get_capital_requirements` | routes/wallet_endpoints.py |
| GET | `/resources/users` | ✓ | `get_user_resource_usage` | routes/admin_endpoints.py |
| GET | `/results/{backtest_id}` | ✓ | `get_backtest_results` | routes/backtesting.py |
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
| GET | `/status` | ✓ | `get_system_status` | routes/system_status.py |
| GET | `/status` | ✓ | `get_execution_quality_status` | routes/execution_quality.py |
| GET | `/status` | ✓ | `get_bots_status` | routes/bot_lifecycle.py |
| GET | `/status` |  | `get_payment_agent_status` | routes/payment_agent_endpoints.py |
| GET | `/status` | ✓ | `get_` | routes/two_factor_auth.py |
| GET | `/status` | ✓ | `get_platform_status` | routes/platforms.py |
| GET | `/status` | ✓ | `get_treasury_status` | routes/treasury.py |
| GET | `/status` | ✓ | `get_evolution_status` | routes/genetic_algorithm.py |
| GET | `/status` | ✓ | `get_quarantine_status` | routes/quarantine.py |
| GET | `/status` | ✓ | `get_system_status` | routes/emergency_stop_endpoints.py |
| GET | `/summary` | ✓ | `get_platforms_summary` | routes/platforms.py |
| GET | `/summary` | ✓ | `get_analytics_summary` | routes/analytics_api.py |
| GET | `/system-health` | ✓ | `system_health_check` | routes/diagnostics.py |
| GET | `/system-stats` | ✓ | `get_system_stats_extended` | routes/admin_endpoints.py |
| GET | `/system/logs` | ✓ | `get_system_logs` | routes/admin_endpoints.py |
| GET | `/system/processes` | ✓ | `get_process_health` | routes/admin_endpoints.py |
| GET | `/system/resources` | ✓ | `get_system_resources` | routes/admin_endpoints.py |
| GET | `/trace` | ✓ | `get_decision_trace` | routes/decision_trace.py |
| GET | `/transactions` | ✓ | `get_wallet_transactions` | routes/wallet_hub.py |
| GET | `/transfers` | ✓ | `get_transfers` | routes/wallet_transfers.py |
| GET | `/transfers` | ✓ | `get_transfer_diagnostics` | routes/diagnostics.py |
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
| GET | `/{bot_id}/diagnostics` | ✓ | `get_bot_diagnostics` | routes/bot_lifecycle.py |
| GET | `/{bot_id}/status` | ✓ | `get_bot_detailed_status` | routes/bot_lifecycle.py |
| GET | `/{platform}/bots` | ✓ | `get_platform_bots` | routes/platforms.py |
| GET | `/{provider}` | ✓ | `get_key` | routes/keys.py |
| GET | `/{run_id}/status` | ✓ | `get_training_status` | routes/training.py |
| PATCH | `/transfer/{transfer_id}/status` | ✓ | `update_transfer_status` | routes/wallet_transfers.py |
| POST | `/` | ✓ | `create_countdown` | routes/user_countdowns.py |
| POST | `/action/execute` | ✓ | `execute_ai_action` | routes/ai_chat.py |
| POST | `/admin/reinvest/trigger` | ✓ | `trigger_manual_reinvestment` | routes/daily_report.py |
| POST | `/ai/analyze-trade` | ✓ | `analyze_trade_opportunity` | routes/phase6_endpoints.py |
| POST | `/ai/market-insight` | ✓ | `generate_market_insight` | routes/phase6_endpoints.py |
| POST | `/ai/strategy-analysis/{bot_id}` | ✓ | `deep_strategy_analysis` | routes/phase6_endpoints.py |
| POST | `/alerts/ack/{alert_id}` | ✓ | `acknowledge_alert` | routes/alerts.py |
| POST | `/auth/login` | ✓ | `login` | routes/auth.py |
| POST | `/auth/register` | ✓ | `register` | routes/auth.py |
| POST | `/auto-evolve/disable` | ✓ | `disable_auto_evolution` | routes/genetic_algorithm.py |
| POST | `/auto-evolve/enable` | ✓ | `enable_auto_evolution` | routes/genetic_algorithm.py |
| POST | `/autopilot/disable` | ✓ | `disable_autopilot` | routes/autopilot_control.py |
| POST | `/autopilot/enable` | ✓ | `enable_autopilot` | routes/autopilot_control.py |
| POST | `/autopilot/toggle` | ✓ | `toggle_autopilot` | routes/autopilot_control.py |
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
| POST | `/mode/switch` | ✓ | `switch_mode` | routes/system_mode.py |
| POST | `/montecarlo` | ✓ | `run_montecarlo` | routes/backtesting.py |
| POST | `/mutate/{bot_id}` | ✓ | `mutate_bot` | routes/genetic_algorithm.py |
| POST | `/ofi/snapshot` | ✓ | `add_ofi_snapshot` | routes/advanced_trading_endpoints.py |
| POST | `/optimize/{strategy_id}` | ✓ | `optimize_parameters` | routes/backtesting.py |
| POST | `/orders/submit` | ✓ | `submit_order` | routes/order_endpoints.py |
| POST | `/pause-all` | ✓ | `pause_all_bots` | routes/bot_lifecycle.py |
| POST | `/pay-alpha-signal` |  | `pay_for_alpha_signal` | routes/payment_agent_endpoints.py |
| POST | `/pay-data-feed` |  | `pay_for_data_feed` | routes/payment_agent_endpoints.py |
| POST | `/profits/reinvest` | ✓ | `reinvest_profits` | routes/compatibility_endpoints.py |
| POST | `/quarantine/reset/{bot_id}` | ✓ | `reset_quarantined_bot` | routes/limits_management.py |
| POST | `/rebalance` | ✓ | `rebalance_treasury` | routes/treasury.py |
| POST | `/regime/update-price` | ✓ | `update_regime_price` | routes/advanced_trading_endpoints.py |
| POST | `/request-live` | ✓ | `request_live_trading` | routes/live_trading_gate.py |
| POST | `/request-testnet-funds` |  | `request_testnet_funds` | routes/payment_agent_endpoints.py |
| POST | `/resume-all` | ✓ | `resume_all_bots` | routes/bot_lifecycle.py |
| POST | `/risk/check-trade` | ✓ | `check_trade_risk` | routes/phase5_endpoints.py |
| POST | `/save` | ✓ | `save_key` | routes/keys.py |
| POST | `/session/end` | ✓ | `end_chat_session` | routes/chat_enhanced.py |
| POST | `/standard` | ✓ | `run_backtest` | routes/backtesting.py |
| POST | `/start` | ✓ | `start_training` | routes/training.py |
| POST | `/start-paper-learning` | ✓ | `start_paper_learning` | routes/live_trading_gate.py |
| POST | `/sweep` | ✓ | `sweep_excess_capital` | routes/treasury.py |
| POST | `/system/mode/toggle` | ✓ | `toggle_system_mode` | routes/trading.py |
| POST | `/test` | ✓ | `test_key` | routes/keys.py |
| POST | `/transfer` | ✓ | `transfer_funds` | routes/wallet_hub.py |
| POST | `/transfer-manual` | ✓ | `create_transfer_manual` | routes/wallet_endpoints.py |
| POST | `/transfers` | ✓ | `create_transfer` | routes/wallet_transfers.py |
| POST | `/unlock` | ✓ | `unlock_admin_panel` | routes/admin_endpoints.py |
| POST | `/users/{user_id}/block` | ✓ | `block_user` | routes/admin_endpoints.py |
| POST | `/users/{user_id}/logout` | ✓ | `force_logout_user` | routes/admin_endpoints.py |
| POST | `/users/{user_id}/reset-password` | ✓ | `reset_user_password` | routes/admin_endpoints.py |
| POST | `/users/{user_id}/unblock` | ✓ | `unblock_user` | routes/admin_endpoints.py |
| POST | `/validate` | ✓ | `validate_` | routes/two_factor_auth.py |
| POST | `/verify` | ✓ | `verify_` | routes/two_factor_auth.py |
| POST | `/walkforward` | ✓ | `run_walkforward` | routes/backtesting.py |
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

