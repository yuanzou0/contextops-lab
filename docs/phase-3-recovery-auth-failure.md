# Phase 3 recovery pilot authentication stop

## Outcome

**BLOCKED BEFORE MEASUREMENT.** The first direct-provider request returned HTTP 401 and the runner
stopped without retrying. A separate no-cost request to the provider model-list endpoint also
returned HTTP 401. No completion succeeded and the treatment proxy observed zero requests.

The first two configured environment variables were present and identical, but their value did not
have the expected OpenAI project-key format. A subsequent macOS Keychain-backed value had the
expected prefix and length but the provider returned `invalid_api_key`. The secret value and the
provider error message were not printed or recorded.

## Evidence boundary

This is an execution-precondition failure, not an observation of any prespecified primary recovery
gate. No recovery claim can be made from this attempt. Estimated provider cost is $0.00 because no
authenticated completion succeeded; actual account usage remains governed by provider billing
records.

No raw prompt, completion, secret, or real user data is present in this artifact.
