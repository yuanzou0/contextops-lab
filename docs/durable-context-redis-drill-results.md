# P0.3-D real Redis drill results

**Evidence label:** `local_real_redis_restart_drill`  
**Overall status:** **PASS**  
**Git commit:** `20d2e7874960e669eb706e1a4b25ee1cea896b97`

This provider-free local drill used a dedicated loopback Redis process, synthetic data, AES-256-GCM, and AOF with `appendfsync always`. It does not establish production-cluster, failover, backup, cross-region, key-rotation, or zero-data-loss claims.

## Gates

| Gate | Status |
|---|---|
| `preflight` | **PASS** |
| `synthetic_write` | **PASS** |
| `application_restart_exact_recovery` | **PASS** |
| `redis_aof_restart_exact_recovery` | **PASS** |
| `tenant_session_isolation` | **PASS** |
| `found_expired_not_found` | **PASS** |
| `wrong_key_tamper_swap_corrupt` | **PASS** |
| `ciphertext_at_rest_and_privacy` | **PASS** |
| `read_outage_unhealthy` | **PASS** |
| `safe_proxy_startup_fail_closed` | **PASS** |
| `fresh_process_recovers_after_outage` | **PASS** |
| `clean_volume_repeat_run` | **PASS** |
| `zero_provider_calls_and_cost` | **PASS** |

## Cost and privacy boundary

- Provider calls: **0**
- Provider cost: **$0.00**
- Real user data: **none**
- Raw context, scope, path, or encryption key in evidence: **none**

## Runtime

- Redis: `Redis server v=7.4.5 sha=00000000:1 malloc=libc bits=64 build=1da1354c3aac5040`
- Python: `3.13.9`
- redis-py: `6.4.0`
- cryptography: `46.0.7`
- PariTok: `1.3.11`
