# Optional worker dispatch

Use direct work for tightly coupled or small compositions. Delegate independently
verifiable scene/frame work only when it improves speed or quality and native
capabilities plus current user/project instructions permit it. This reference does
not grant delegation authority.

For an allowed child, provide the relevant role file, bounded task context, owned
output paths, dependencies and acceptance checks. Tell writers they share the
checkout and must preserve others' edits. Keep provider/spend gates in the parent;
worker dispatch does not authorize paid calls.

Use only the native dispatch/wait tools actually exposed by the host, respecting
its schemas. Apply the stricter runtime and project limit: this workspace allows
at most two concurrent children and depth one; children never create children.
A project's no-child rule takes precedence. Never use CLI/background agent
processes to bypass disabled or unavailable native delegation, authorization,
concurrency or depth limits. Instead execute the needed roles directly, loading
one role's resources at a time and retaining its acceptance checks.

Wait for actual worker completion and inspect its artifacts and evidence. File
existence alone does not establish success. Diagnose failures before targeted
repair; do not blindly redispatch. Preserve all planned scene outputs whether
executed directly or in bounded waves. After collecting results, stop and archive
completed children using the product capability, or report unavailable cleanup.

Resolve role and script paths from the loaded skill's `SKILL_DIR`, not the process
working directory. Read only the references needed for the assigned scene.
