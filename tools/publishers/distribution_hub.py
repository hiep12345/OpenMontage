"""Optional service-authenticated delivery tool; never a social publisher."""
from lib.distribution_hub import HubError
from lib.hub_access import configured_client
from lib.hub_diagnostics import HandoffReport
from tools.base_tool import (BaseTool, ExecutionMode, ResourceProfile, ResumeSupport,
                             ToolResult, ToolRuntime, ToolStability, ToolStatus, ToolTier)


class DistributionHub(BaseTool):
    name = "distribution_hub"
    version = "0.1.0"
    tier = ToolTier.PUBLISH
    capability = "distribution_handoff"
    provider = "distribution_hub"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    runtime = ToolRuntime.API
    resume_support = ResumeSupport.FROM_CHECKPOINT
    dependencies = []
    install_instructions = "Administrator provisions the Hub HTTPS origin and dedicated content-ingest Access service credentials."
    capabilities = ["inspect_handoff", "ingest_metadata", "deliver_immutable_media", "inspect_readiness", "content_novelty"]
    supports = {"uploads": True, "social_publication": False, "generation": False, "resumable": True}
    best_for = ["verifying a reviewed exact artifact and delivering immutable files to Distribution Hub"]
    not_good_for = ["creating content, selecting destinations, QA approval or social upload/publication"]
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=32, network_required=True)
    side_effects = ["ingest creates Hub metadata/jobs", "deliver writes authenticated immutable media chunks"]
    user_visible_verification = ["Inspect exact content, current job bindings and file readiness; public publication is not asserted."]
    input_schema = {"type": "object", "required": ["operation"], "properties": {
        "operation": {"enum": ["inspect", "readiness", "ingest", "deliver", "content_index", "novelty"]},
        "channel": {"type": "string"}, "content_id": {"type": "string"}, "target": {"type": "string"},
        "root": {"type": "string"}, "expected": {"type": "object"}, "payload": {"type": "object"},
        "identity": {"type": "object"}, "stage": {"enum": ["PRE_GENERATION", "PRE_DELIVERY"]},
        "registry_path": {"type": "string"}, "reserve": {"type": "boolean"}, "project_dir": {"type": "string"},
        "delivery_plan": {"oneOf": [{"type": "object"}, {"type": "array", "items": {"type": "object"}}]}}}
    output_schema = {"type": "object"}

    @staticmethod
    def _client():
        return configured_client()

    def get_status(self):
        try:
            self._client()
        except (HubError, ValueError):
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    def execute(self, inputs):
        # Persist RUNNING before sending: an interrupted process leaves evidence.
        try:
            report = HandoffReport(inputs)
        except (AttributeError, TypeError, ValueError, OSError):
            return ToolResult(success=False, error="Cannot persist Hub handoff report; no request sent")
        client = None
        try:
            client = self._client()
            if hasattr(client, "diagnostics"):
                client.diagnostics = []
            operation = inputs["operation"]
            if operation == "ingest":
                result = client.ingest(inputs["payload"], delivery_plan=inputs.get("delivery_plan"), novelty_registry=inputs.get("registry_path"))
            elif operation == "content_index":
                result = client.content_index(inputs["channel"])
            elif operation == "novelty":
                result = client.novelty(inputs["channel"], inputs["identity"], inputs.get("stage", "PRE_GENERATION"),
                                       registry_path=inputs.get("registry_path"), reserve=inputs.get("reserve", False),
                                       delivery_plan=inputs.get("delivery_plan"))
            elif operation in {"inspect", "readiness", "deliver"}:
                args = [inputs["channel"], inputs["content_id"]]
                if operation != "inspect":
                    args.append(inputs["target"])
                if operation == "deliver":
                    args.append(inputs["root"])
                kwargs = {"expected": inputs.get("expected")}
                if operation == "deliver" and inputs.get("identity") is not None:
                    kwargs["content_identity"] = inputs["identity"]
                result = getattr(client, operation)(*args, **kwargs)
            else:
                raise HubError("Unknown Hub operation")
            try:
                report_path = report.finish(result=result, requests=getattr(client, "diagnostics", []))
            except (TypeError, ValueError, OSError):
                # Never turn a completed mutation into an apparent retryable failure.
                return ToolResult(success=True, data={**result, "reportPath": str(report.path), "reportPersisted": False})
            return ToolResult(success=True, data={**result, "reportPath": report_path, "reportPersisted": True})
        except HubError as error:
            return self._failure(report, client, error, str(error))
        except (KeyError, TypeError, ValueError, OSError):
            return self._failure(report, client, HubError("Invalid Hub inputs or unavailable exact local file"),
                                 "Invalid Hub inputs or unavailable exact local file")

    @staticmethod
    def _failure(report, client, error, message):
        try:
            path = report.finish(error=error, requests=getattr(client, "diagnostics", []))
        except (TypeError, ValueError, OSError):
            return ToolResult(success=False, error=message, data={"reportPath": str(report.path), "reportPersisted": False,
                                                                 "nextAction": report.value["nextAction"]})
        return ToolResult(success=False, error=message, data={"reportPath": path, "reportPersisted": True,
                                                            "nextAction": report.value["nextAction"]})
