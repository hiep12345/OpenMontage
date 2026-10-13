# BFL API key setup

Check presence without printing the value:

```bash
[ -n "$BFL_API_KEY" ] && echo "BFL_API_KEY configured" || echo "BFL_API_KEY missing"
```

Presence does not establish validity. Use an authorized non-generating account/auth
check supported by the current API, with secret headers supplied from the process
environment and response/error logging redacted. Distinguish authentication
rejection from network, rate-limit and permission errors.

If absent, direct the user to https://dashboard.bfl.ai/get-started to create a key
and enter it privately in the supported connector or ignored local environment
file. Load that file through the application's environment loader without printing
its contents. Never request chat-pasted credentials or grep/echo their values.
Do not overwrite unrelated settings or add duplicate key entries.
