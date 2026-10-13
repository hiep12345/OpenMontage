---
name: faceswap
description: Use when HeyGen face swapping is explicitly requested or selected by the approved OpenMontage workflow. Follow the selected adapter contract and existing provider, voice, source and spend approvals; generic media requests use the project router.
allowed-tools: mcp__heygen__*
metadata:
  openclaw:
    requires:
      env:
        - HEYGEN_API_KEY
    primaryEnv: HEYGEN_API_KEY
---

# Face swap with the selected HeyGen capability

Use the current native tool or registered adapter only after confirming it supports face swapping for this account. This skill does not establish that an old workflow endpoint or node name is still available. Inspect its actual input, status and output schema before use; if unavailable, report that gap without silently choosing another provider.

Preserve the approved source/identity consent, target video, provider and spend scope. Prefer a clear, well-lit source image with one face; inspect the target's visible faces, occlusion and motion before judging suitability. Do not promise support for every video or a fixed processing time. Configure credentials through the supported private settings/environment mechanism; check presence without printing values or asking for keys in chat.

## Submit once, retain the accepted job

Before submission, bind a unique request identity to the approved input and inspect its durable receipt. An accepted handle means resume that job. A missing receipt after an uncertain POST does not mean the provider rejected it: reconcile first, without blind resubmission. A receipt is not a provider idempotency key.

The examples below are local orchestration patterns, not HeyGen SDK methods or assertions about its API schema. Supply callbacks using the actual selected tool/adapter:

- `submit` returns its accepted execution handle and honors the supplied HTTP timeout/abort signal. Do not use submission as an authentication test.
- `inspect` performs status lookup only and returns a **local normalized** `{state, result}` record. Map only the adapter's documented pending states to `pending`, its verified successful state/output to `completed`, and leave failed, cancelled, missing and unfamiliar states non-pending.
- `persist` is bound to that unique request and durably saves `{provider, handle}` before returning (atomic storage with the appropriate flush/commit). Do not overwrite another request's receipt or publish signed URLs.

Every post-accept failure carries `handle`, including receipt open/serialization/flush failures and poll errors. If persistence fails, stop, recover the handle from the exception and save it through a working durable channel before leaving the task. Crash recovery cannot be guaranteed when all durable storage fails. Do not begin polling until persistence succeeds.

## Python orchestration example

```python
import math
import time

class SubmissionUnknown(RuntimeError):
    """Submission outcome is unknown; reconcile before resending."""

class AcceptedJobError(RuntimeError):
    def __init__(self, handle, phase):
        self.handle = handle
        self.phase = phase
        super().__init__(f"Accepted face-swap job: {phase} failed; recover via .handle")

def faceswap_and_wait(submit, inspect, persist):
    try:
        handle = submit(timeout=30)
        if not isinstance(handle, str) or not handle:
            raise ValueError("Missing execution handle")
    except BaseException as error:
        raise SubmissionUnknown("Reconcile submission; do not blindly resend") from error
    try:
        persist({"provider": "heygen", "handle": handle})
    except BaseException as error:
        raise AcceptedJobError(handle, "receipt") from error
    return resume_faceswap(handle, inspect)

def resume_faceswap(handle, inspect, timeout=300, interval=10):
    """Load the receipt and call this function; it never calls submit."""
    try:
        if not math.isfinite(timeout) or not math.isfinite(interval) or timeout <= 0 or interval <= 0:
            raise ValueError("Positive timeout and interval required")
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Polling deadline exceeded")
            data = inspect(handle, timeout=min(20, remaining))
            if data.get("state") == "completed":
                return {"handle": handle, "result": data["result"]}
            if data.get("state") != "pending":
                raise RuntimeError("Terminal or unrecognized state; inspect response")
            time.sleep(min(interval, max(0, deadline - time.monotonic())))
    except BaseException as error:
        raise AcceptedJobError(handle, "poll") from error
```

The wrapper preserves the original exception as its cause, including an interruption. Record the handle, then honor the stop. A local timeout does not cancel the remote job; use status reconciliation on resume. The callbacks must implement the indicated transport timeouts, without hidden submission retries.

## TypeScript orchestration example

The same local callback contract applies here. `persist` must resolve only after durable storage completes. `submit` and `inspect` must pass the supplied abort signal to their actual transport; this is not a provider-specific SDK.

```typescript
type JobState = { state: string; result?: unknown };
type Submit = (signal: AbortSignal) => Promise<string>;
type Inspect = (handle: string, signal: AbortSignal) => Promise<JobState>;
type Persist = (record: { provider: string; handle: string }) => Promise<void>;

class SubmissionUnknown extends Error {}
class AcceptedJobError extends Error {
  handle: string;
  phase: string;
  constructor(handle: string, phase: string, cause: unknown) {
    super(`Accepted face-swap job: ${phase} failed; recover via .handle`, { cause });
    this.handle = handle;
    this.phase = phase;
  }
}

async function faceswapAndWait(submit: Submit, inspect: Inspect, persist: Persist) {
  let handle: string;
  try {
    handle = await submit(AbortSignal.timeout(30000));
    if (typeof handle !== "string" || !handle) throw new Error("Missing execution handle");
  } catch (cause) {
    throw new SubmissionUnknown("Reconcile submission; do not blindly resend", { cause });
  }
  try {
    await persist({ provider: "heygen", handle });
  } catch (cause) {
    throw new AcceptedJobError(handle, "receipt", cause);
  }
  return resumeFaceswap(handle, inspect);
}

async function resumeFaceswap(handle: string, inspect: Inspect,
                              timeoutMs = 300000, intervalMs = 10000) {
  try {
    if (!Number.isFinite(timeoutMs) || !Number.isFinite(intervalMs) ||
        timeoutMs <= 0 || intervalMs <= 0) throw new Error("Positive finite timing required");
    const deadline = performance.now() + timeoutMs;
    while (true) {
      const remaining = deadline - performance.now();
      if (remaining <= 0) throw new Error("Polling deadline exceeded");
      const data = await inspect(handle, AbortSignal.timeout(Math.max(1, Math.ceil(Math.min(20000, remaining)))));
      if (data.state === "completed") {
        if (!("result" in data)) throw new Error("Missing completed result");
        return { handle, result: data.result };
      }
      if (data.state !== "pending") throw new Error("Terminal or unrecognized state; inspect response");
      await new Promise(resolve => setTimeout(resolve, Math.min(intervalMs, Math.max(0, deadline - performance.now()))));
    }
  } catch (cause) {
    throw new AcceptedJobError(handle, "poll", cause);
  }
}
```

On resume, load the saved handle and call `resume_faceswap`/`resumeFaceswap` directly; neither function can submit a new job. Keep per-request receipts and collect individual results/errors if an approved batch runs concurrently.

If the requested target video must first be generated by an avatar workflow, use its selected supported adapter and the same receipt/reconciliation discipline. Inspect that completed artifact before a separately authorized face-swap submission. After completion, download to a task-owned output, inspect identity fidelity and temporal artifacts, and retain provenance and the job handle with the result.
