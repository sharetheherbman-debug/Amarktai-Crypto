#!/bin/bash
echo "=== OpenAI Retry Test ==="
echo "To verify retries, check logs for 'Retrying' after a 429 from OpenAI."
echo "In logs you should see: tenacity.before_sleep: Retrying call to _call_openai_with_retry"
echo "Manual test: set OPENAI_API_KEY to an exhausted key and send a chat message."
