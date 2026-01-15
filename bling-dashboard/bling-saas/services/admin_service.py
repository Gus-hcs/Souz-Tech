from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from models import Client, UsageLog


def list_clients(session: Session) -> List[Client]:
    return session.query(Client).order_by(Client.company_name.asc()).all()


def get_client(session: Session, client_id: int) -> Optional[Client]:
    return session.query(Client).filter(Client.id == client_id).first()


def get_client_by_username(session: Session, username: str) -> Optional[Client]:
    return session.query(Client).filter(Client.username == username).first()


def create_client(session: Session, client: Client) -> Client:
    session.add(client)
    session.commit()
    session.refresh(client)
    return client


def update_client(session: Session, client: Client) -> Client:
    session.add(client)
    session.commit()
    session.refresh(client)
    return client


def delete_client(session: Session, client_id: int) -> None:
    client = get_client(session, client_id)
    if not client:
        return
    session.query(UsageLog).filter(UsageLog.client_id == client_id).delete()
    session.delete(client)
    session.commit()


def set_active(session: Session, client_id: int, is_active: bool) -> None:
    client = get_client(session, client_id)
    if not client:
        return
    client.is_active = is_active
    session.add(client)
    session.commit()


def log_action(session: Session, client_id: int, action: str) -> None:
    log = UsageLog(client_id=client_id, action=action)
    session.add(log)
    session.commit()


def get_logs(session: Session, client_id: int) -> List[UsageLog]:
    return (
        session.query(UsageLog)
        .filter(UsageLog.client_id == client_id)
        .order_by(UsageLog.timestamp.desc())
        .limit(200)
        .all()
    )
