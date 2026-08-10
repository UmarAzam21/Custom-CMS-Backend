from sqlalchemy.orm import Session
from sqlalchemy import desc

from app import models


def get_or_create_customer(db: Session, email: str, name: str | None = None) -> models.SupportCustomer:
    customer = db.query(models.SupportCustomer).filter(models.SupportCustomer.email == email).first()
    if customer:
        if name and not customer.name:
            customer.name = name
            db.commit()
            db.refresh(customer)
        return customer

    customer = models.SupportCustomer(email=email, name=name)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def create_ticket_with_message(
    db: Session, customer: models.SupportCustomer, subject: str, body: str
) -> models.SupportTicket:
    ticket = models.SupportTicket(customer_id=customer.id, subject=subject)
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    message = models.SupportTicketMessage(
        ticket_id=ticket.id,
        direction=models.MessageDirection.INBOUND,
        sender_email=customer.email,
        body=body,
    )
    db.add(message)
    db.commit()
    db.refresh(ticket)
    return ticket


def add_message(
    db: Session, ticket: models.SupportTicket, direction: models.MessageDirection,
    sender_email: str, body: str,
) -> models.SupportTicketMessage:
    message = models.SupportTicketMessage(
        ticket_id=ticket.id,
        direction=direction,
        sender_email=sender_email,
        body=body,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def list_tickets(db: Session):
    return (
        db.query(models.SupportTicket)
        .order_by(desc(models.SupportTicket.updated_at))
        .all()
    )


def get_ticket(db: Session, ticket_id: int) -> models.SupportTicket | None:
    return db.query(models.SupportTicket).filter(models.SupportTicket.id == ticket_id).first()
