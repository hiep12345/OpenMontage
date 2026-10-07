"""Optional service-authenticated delivery tool; never a social publisher."""
import os

from lib.distribution_hub import HubClient, HubError
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
    dependencies = ["env:DISTRIBUTION_HUB_ORIGIN", "env:DISTRIBUTION_HUB_CLIENT_ID", "env:DISTRIBUTION_HUB_CLIENT_SECRET"]
    install_instructions = "Administrator provisions the Hub HTTPS origin and dedicated content-ingest Access service credentials."
    capabilities = ["inspect_handoff", "ingest_metadata", "deliver_immutable_media", "inspect_readiness"]
    supports = {"uploads": True, "social_publication": False, "generation": False, "resumable": True}
    best_for = ["verifying a reviewed exact artifact and delivering immutable files to Distribution Hub"]
    not_good_for = ["creating content, selecting destinations, QA approval or social upload/publication"]
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=32, network_required=True)
    side_effects = ["ingest creates Hub metadata/jobs", "deliver writes authenticated immutable media chunks"]
    user_visible_verification = ["Inspect exact content, current job bindings and file readiness; public publication is not asserted."]
    input_schema = {"type": "object", "required": ["operation"], "properties": {
        "operation": {"enum": ["inspect", "readiness", "ingest", "deliver"]},
        "channel": {"type": "string"}, "content_id": {"type": "string"}, "target": {"type": "string"},
        "root": {"type": "string"}, "expected": {"type": "object"}, "payload": {"type": "object"}}}
    output_schema = {"type": "object"}

    @staticmethod
    def _client():
        return HubClient(os.environ.get("DISTRIBUTION_HUB_ORIGIN", ""),
                         os.environ.get("DISTRIBUTION_HUB_CLIENT_ID", ""),
                         os.environ.get("DISTRIBUTION_HUB_CLIENT_SECRET", ""))

    def get_status(self):
        try:
            self._client()
        except (HubError, ValueError):
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    def execute(self, inputs):
        try:
            client = self._client()
            operation = inputs["operation"]
            if operation == "ingest":
                result = client.ingest(inputs["payload"])
            elif operation in {"inspect", "readiness", "deliver"}:
                args = [inputs["channel"], inputs["content_id"]]
                if operation != "inspect":
                    args.append(inputs["target"])
                if operation == "deliver":
                    args.append(inputs["root"])
                result = getattr(client, operation)(*args, expected=inputs.get("expected"))
            else:
                raise HubError("Unknown Hub operation")
            return ToolResult(success=True, data=result)
        except HubError as error:
            return ToolResult(success=False, error=str(error))
        except (KeyError, TypeError, ValueError, OSError):
            return ToolResult(success=False, error="Invalid Hub inputs or unavailable exact local file")
