from mcp.server.fastmcp import FastMCP

from opsdesk.actions import ActionHandlers
from opsdesk.configuration import Configuration
from opsdesk.storage import Database


def main():
    config = Configuration()
    database = Database(config)
    handlers = ActionHandlers(database, config)
    server = FastMCP("OpsDesk action tools", instructions="Only act on persisted eligible support operations.")

    @server.tool()
    def create_work_order(request_id: str) -> dict:
        """Create or return the work order for an eligible operation."""
        return handlers.create_work_order(request_id)

    @server.tool()
    def export_ledger(request_id: str) -> dict:
        """Idempotently export an existing work order to the local workbook."""
        return handlers.export_ledger(request_id)

    @server.tool()
    def notify_escalation(request_id: str) -> dict:
        """Record an escalation, or send via explicitly configured SMTP, for P1 only."""
        return handlers.notify_escalation(request_id)

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
