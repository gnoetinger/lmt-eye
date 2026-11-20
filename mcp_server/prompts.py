"""MCP prompts of LMT-EYE.

Prompts are ready-made messages that the user triggers from the client
(in Claude Code: /mcp__lmt-eye__<name>). Each function decorated with
@server.prompt() inside register_prompts() becomes a prompt; its
parameters become the prompt arguments (no default value = required).
"""

from mcp.server.mcpserver import MCPServer


def register_prompts(server: MCPServer) -> None:
    """Register the LMT-EYE prompts on the server."""

    @server.prompt(
        name="ecological_impact",
        title="Ecological impact",
        description="Provide an estimation of the ecological impact of your requests.",
    )
    def ecological_impact( ) -> str:
        return (
            "Using the current conversation with the user, "
            "estimate the impact in kWh of the usage, and the volume of water consumption. "
            "Display the difference between the energy used on the server side, and on the user's computer. "
            "Provide good practices to save energy."
        )

    # Add other prompts here, each with a distinct name:
    #
    # @server.prompt(name="...", description="...")
    # def my_prompt(arg: str) -> str:
    #     return f"..."
