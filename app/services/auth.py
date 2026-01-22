from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account


class AccountService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_account(self, owner_id: int) -> Optional[Account]:
        result = await self._session.execute(
            select(Account).where(Account.owner_id == owner_id, Account.is_active == True)
        )
        return result.scalars().first()

    async def get_by_phone(self, phone: str) -> Optional[Account]:
        result = await self._session.execute(select(Account).where(Account.phone == phone))
        return result.scalars().first()

    async def add_account(self, owner_id: int, phone: str, session_string: str) -> Account:
        account = Account(owner_id=owner_id, phone=phone, session_string=session_string, is_active=True)
        self._session.add(account)
        await self._session.commit()
        await self._session.refresh(account)
        return account

    async def list_accounts(self, owner_id: int) -> list[Account]:
        result = await self._session.execute(select(Account).where(Account.owner_id == owner_id))
        return result.scalars().all()

    async def set_active(self, owner_id: int, account_id: int, active: bool) -> bool:
        result = await self._session.execute(
            select(Account).where(Account.id == account_id, Account.owner_id == owner_id)
        )
        account = result.scalars().first()
        if not account:
            return False
        if active:
            await self._session.execute(
                update(Account).where(Account.owner_id == owner_id).values(is_active=False)
            )
        account.is_active = active
        await self._session.commit()
        return True
