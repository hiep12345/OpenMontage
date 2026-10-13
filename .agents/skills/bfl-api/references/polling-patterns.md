---
name: polling-patterns
description: Accepted-job persistence and bounded polling for a selected BFL generation request.
---

# BFL polling and recovery

Use these illustrative helpers only with the selected BFL endpoint/model and its current response contract. They are not an installed SDK. A successful submission supplies a `polling_url`; `Ready` supplies `result`, and only the confirmed `Pending` state is polled here. Every other state, including cancellation or an unfamiliar value, stops polling. Check the current adapter or official documentation before extending that whitelist.

`persist_accepted_job(record)` is a caller-provided durable receipt callback (awaitable in the async example). Bind it to a unique task/request identity, selected provider/model, and approved input before submission. It must save the handle atomically and durably, returning only after success; do not expose credentials or signed URLs in public logs. A failed write stops polling and raises an exception with the recoverable `handle`. Save that handle through an available durable channel before leaving the task. No client can guarantee crash recovery if every storage channel fails.

Before a fresh POST, inspect that request's receipt. If it contains a handle, use `resume`/`resume_async` without another POST. If a prior POST has an unknown outcome, reconcile with the provider first; an empty receipt is not proof that submission failed. The helpers never retry POSTs. Errors before a usable handle arrives mean unknown acceptance, not authorization to resend.

## Synchronous example

```python
import math
import time
import requests

class SubmissionUnknown(RuntimeError):
    """No usable handle received; reconcile before another POST."""

class AcceptedJobError(RuntimeError):
    def __init__(self, handle, phase):
        self.handle = handle
        self.phase = phase
        super().__init__(f"Accepted job: {phase} failed; recover via .handle, do not resubmit")

def ready_result(data):
    if data.get("status") == "Ready":
        return True, data["result"]
    if data.get("status") == "Pending":
        return False, None
    raise RuntimeError("Terminal or unrecognized provider state; inspect response")

class BFLClient:
    def __init__(self, api_key, base_url="https://api.bfl.ai"):
        self.base_url = base_url
        self.headers = {"x-key": api_key, "Content-Type": "application/json"}

    def generate(self, model, prompt, persist_accepted_job, **kwargs):
        try:
            response = requests.post(
                f"{self.base_url}/v1/{model}", headers=self.headers,
                json={"prompt": prompt, **kwargs}, timeout=30,
            )
            response.raise_for_status()
            handle = response.json()["polling_url"]
            if not isinstance(handle, str) or not handle:
                raise ValueError("Missing polling URL")
        except BaseException as error:
            raise SubmissionUnknown("Reconcile submission; do not blindly resend") from error
        try:
            persist_accepted_job({"provider": "bfl", "model": model, "handle": handle})
        except BaseException as error:
            raise AcceptedJobError(handle, "receipt") from error
        return self.resume(handle)

    def resume(self, handle, timeout=120, interval=2):
        """GET only; load handle from the request's durable receipt."""
        try:
            if not math.isfinite(timeout) or not math.isfinite(interval) or timeout <= 0 or interval <= 0:
                raise ValueError("Positive timeout and interval required")
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Polling deadline exceeded")
                response = requests.get(handle, headers=self.headers,
                                        timeout=min(20, remaining))
                response.raise_for_status()
                done, result = ready_result(response.json())
                if done:
                    return {"handle": handle, "result": result}
                time.sleep(min(interval, max(0, deadline - time.monotonic())))
        except BaseException as error:
            raise AcceptedJobError(handle, "poll") from error
```

`AcceptedJobError.handle` remains available for receipt errors, HTTP/JSON errors, unknown/failed/cancelled states, deadline expiry and interruption. Its cause retains the original error. The wrapper intentionally stops this illustrative operation even for an interruption; record the handle, then honor the stop. A local poll timeout does not cancel the remote job.

## Asynchronous example

Use the definitions above and an already configured `aiohttp` session. Each accepted job gets its own receipt before its first status GET. Cancellation after acceptance retains the handle, including during response cleanup or receipt persistence.

```python
import asyncio
import aiohttp

class AcceptedJobCancelled(AcceptedJobError):
    def __init__(self, handle):
        super().__init__(handle, "interrupted")

async def submit_and_poll(session, client, model, prompt, persist_accepted_job):
    handle = None
    phase = "submit"
    try:
        async with session.post(
            f"{client.base_url}/v1/{model}", headers=client.headers,
            json={"prompt": prompt}, timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            response.raise_for_status()
            data = await response.json()
            candidate = data.get("polling_url")
            if not isinstance(candidate, str) or not candidate:
                raise ValueError("Missing polling URL")
            handle = candidate
        phase = "receipt"
        await persist_accepted_job({"provider": "bfl", "model": model, "handle": handle})
    except asyncio.CancelledError as error:
        if handle is not None:
            raise AcceptedJobCancelled(handle) from error
        raise SubmissionUnknown("Interrupted submission; reconcile before resending") from error
    except BaseException as error:
        if handle is not None:
            raise AcceptedJobError(handle, phase) from error
        raise SubmissionUnknown("Reconcile submission; do not blindly resend") from error
    return await resume_async(session, client, handle)

async def resume_async(session, client, handle, timeout=120, interval=2):
    """GET only; no submission or implicit retry."""
    try:
        if not math.isfinite(timeout) or not math.isfinite(interval) or timeout <= 0 or interval <= 0:
            raise ValueError("Positive timeout and interval required")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("Polling deadline exceeded")
            async with session.get(handle, headers=client.headers,
                                   timeout=aiohttp.ClientTimeout(total=min(20, remaining))) as response:
                response.raise_for_status()
                done, result = ready_result(await response.json())
            if done:
                return {"handle": handle, "result": result}
            await asyncio.sleep(min(interval, max(0, deadline - loop.time())))
    except asyncio.CancelledError as error:
        raise AcceptedJobCancelled(handle) from error
    except BaseException as error:
        raise AcceptedJobError(handle, "poll") from error
```

For an approved parallel batch, cap concurrent submissions to the provider's rate limit and remaining budget, bind a separate durable callback to each request, and collect each result/error rather than dropping siblings when one fails. Use `asyncio.gather(..., return_exceptions=True)` to collect per-job outcomes. The wrapper deliberately converts post-accept cancellation into an ordinary accepted-job exception so batch collection preserves its handle; honor that interruption after recording the outcome. Reconcile each saved handle independently. Bounded backoff/jitter can replace the fixed interval while retaining the deadline and state whitelist. A rate-limit response is not a reason to submit again.

Download a completed artifact promptly to a task-owned output after checking the current response contract and expiry; do not rely on a fixed URL lifetime. Preserve existing outputs unless replacement is authorized. Record the local artifact and its accepted handle before considering the job complete.
