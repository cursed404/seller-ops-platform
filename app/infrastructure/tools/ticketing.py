class TicketGateway:
    def create_ticket(self, *, reference: str, summary: str) -> dict[str, str]:
        return {
            "status": "success",
            "ticket_id": f"TKT-{reference}",
            "summary": summary,
        }
