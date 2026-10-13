---
name: setup-api-key
description: Configure or diagnose authentication for explicitly selected ElevenLabs tools. Use for missing/invalid ElevenLabs credentials or an explicit ElevenLabs setup request.
license: MIT
compatibility: Requires an ElevenLabs account and network access for an authorized authentication check.
---

# ElevenLabs API key setup

1. Inspect credential presence in the selected connector/environment or ignored
   local configuration without displaying the value or reading secrets into chat.
2. If present, validate via the supported non-generating account check (the API's
   `GET /v1/user` requires appropriate read permission). Supply the header from the
   environment; redact headers and response/error logs. A missing read permission,
   rate limit or network failure does not prove the credential invalid.
3. If already valid, report that configuration is ready and continue the authorized
   task. Rotation is optional and only needed when requested or compromised.
4. If missing or rejected, direct the user to
   https://elevenlabs.io/app/settings/api-keys. Have them create a least-privilege
   key and enter it privately in the supported connector/secret setting or an
   ignored local environment file. Never ask them to paste it into chat or pass
   it as a literal shell argument.
5. Recheck without revealing secrets. Preserve unrelated configuration and existing
   keys; replace a credential only for an authorized rotation. Explain the actual
   storage used: an `.env` file is loaded by an application, not automatically a
   process environment variable.
