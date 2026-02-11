from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BalanceTransaction, PriceConfig, UserBalance


class BillingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_balance(self, user_id: int) -> float:
        result = await self._session.execute(select(UserBalance).where(UserBalance.user_id == user_id))
        balance = result.scalars().first()
        return balance.balance if balance else 0.0

    async def add_balance(self, user_id: int, amount: float, reason: str | None = None) -> tuple[float, int]:
        result = await self._session.execute(select(UserBalance).where(UserBalance.user_id == user_id))
        balance = result.scalars().first()
        if not balance:
            balance = UserBalance(user_id=user_id, balance=amount)
            self._session.add(balance)
        else:
            balance.balance += amount
        tx = BalanceTransaction(
            user_id=user_id,
            amount=amount,
            tx_type="topup" if amount >= 0 else "adjust",
            reason=reason,
        )
        self._session.add(tx)
        await self._session.flush()
        await self._session.commit()
        return balance.balance, tx.id

    async def charge(self, user_id: int, amount: float, reason: str | None = None) -> float:
        if amount <= 0:
            return await self.get_balance(user_id)
        result = await self._session.execute(select(UserBalance).where(UserBalance.user_id == user_id))
        balance = result.scalars().first()
        if not balance:
            balance = UserBalance(user_id=user_id, balance=-amount)
            self._session.add(balance)
        else:
            balance.balance -= amount
        self._session.add(
            BalanceTransaction(
                user_id=user_id,
                amount=-amount,
                tx_type="charge",
                reason=reason,
            )
        )
        await self._session.commit()
        return balance.balance

    async def set_price(self, key: str, price: float) -> float:
        result = await self._session.execute(select(PriceConfig).where(PriceConfig.key == key))
        row = result.scalars().first()
        if not row:
            row = PriceConfig(key=key, price=price)
            self._session.add(row)
        else:
            row.price = price
        await self._session.commit()
        return row.price

    async def get_price(self, key: str) -> float:
        result = await self._session.execute(select(PriceConfig).where(PriceConfig.key == key))
        row = result.scalars().first()
        return row.price if row else 0.0

    async def list_prices(self) -> list[PriceConfig]:
        result = await self._session.execute(select(PriceConfig))
        return result.scalars().all()

    async def ensure_price(self, key: str, default: float = 0.0) -> float:
        result = await self._session.execute(select(PriceConfig).where(PriceConfig.key == key))
        row = result.scalars().first()
        if row:
            return row.price
        row = PriceConfig(key=key, price=default)
        self._session.add(row)
        await self._session.commit()
        return row.price

    async def list_transactions(self, user_id: int, limit: int = 10) -> list[BalanceTransaction]:
        result = await self._session.execute(
            select(BalanceTransaction)
            .where(BalanceTransaction.user_id == user_id)
            .order_by(BalanceTransaction.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
