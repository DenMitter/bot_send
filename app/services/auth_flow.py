from __future__ import annotations

from dataclasses import dataclass
<<<<<<< HEAD
from typing import Dict, Optional, Tuple
=======
from typing import Optional, Tuple
>>>>>>> 9dd19731839bc17800be4d7e8cd1e3ac8fafa344
from uuid import uuid4

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from app.core.config import get_settings


@dataclass
class AuthFlow:
    phone: Optional[str]
    client: TelegramClient
    mode: str
    qr_login: Optional[object] = None
    web_token: Optional[str] = None
    code: Optional[str] = None
    password: Optional[str] = None
    needs_password: bool = False
    code_type: Optional[object] = None
    next_code_type: Optional[object] = None
    code_timeout: Optional[int] = None


class AuthFlowManager:
    def __init__(self) -> None:
        self._flows: Dict[int, AuthFlow] = {}
        self._token_index: Dict[str, int] = {}

    async def start(self, user_id: int, phone: str) -> None:
        settings = get_settings()
        client = TelegramClient(StringSession(), settings.api_id, settings.api_hash)
        await client.connect()
        try:
            sent_code = await client.send_code_request(phone)
        except Exception:
            await client.disconnect()
            raise
        self._flows[user_id] = AuthFlow(
            phone=phone,
            client=client,
            mode="code",
            code_type=getattr(sent_code, "type", None),
            next_code_type=getattr(sent_code, "next_type", None),
            code_timeout=getattr(sent_code, "timeout", None),
        )

    async def start_web(self, user_id: int, phone: str) -> str:
        settings = get_settings()
        client = TelegramClient(StringSession(), settings.api_id, settings.api_hash)
        await client.connect()
        try:
            sent_code = await client.send_code_request(phone)
        except Exception:
            await client.disconnect()
            raise
        token = uuid4().hex
        self._flows[user_id] = AuthFlow(
            phone=phone,
            client=client,
            mode="web",
            web_token=token,
            code_type=getattr(sent_code, "type", None),
            next_code_type=getattr(sent_code, "next_type", None),
            code_timeout=getattr(sent_code, "timeout", None),
        )
        self._token_index[token] = user_id
        return token

    async def start_qr(self, user_id: int) -> str:
        settings = get_settings()
        client = TelegramClient(StringSession(), settings.api_id, settings.api_hash)
        await client.connect()
        qr_login = await client.qr_login()
        self._flows[user_id] = AuthFlow(phone=None, client=client, mode="qr", qr_login=qr_login)
        return qr_login.url

<<<<<<< HEAD
=======
    def get_delivery_info(self, user_id: int) -> Tuple[Optional[object], Optional[object], Optional[int]]:
        flow = self._flows.get(user_id)
        if not flow:
            return None, None, None
        return flow.code_type, flow.next_code_type, flow.code_timeout

>>>>>>> 9dd19731839bc17800be4d7e8cd1e3ac8fafa344
    async def submit_code(self, user_id: int, code: str) -> Optional[str]:
        flow = self._flows.get(user_id)
        if not flow:
            return None
        try:
            await flow.client.sign_in(phone=flow.phone, code=code)
        except SessionPasswordNeededError:
            return "PASSWORD_REQUIRED"
        except Exception:
            return None
        session_string = flow.client.session.save()
        await flow.client.disconnect()
        self._flows.pop(user_id, None)
        return session_string

    async def submit_password(self, user_id: int, password: str) -> Optional[str]:
        flow = self._flows.get(user_id)
        if not flow:
            return None
        try:
            await flow.client.sign_in(password=password)
        except Exception:
            return None
        session_string = flow.client.session.save()
        await flow.client.disconnect()
        self._flows.pop(user_id, None)
        return session_string

<<<<<<< HEAD
    async def confirm_qr(self, user_id: int, timeout: int = 60) -> Tuple[Optional[str], Optional[str]]:
=======
    async def confirm_qr(self, user_id: int, timeout: int = 60) -> tuple[Optional[str], Optional[str]]:
>>>>>>> 9dd19731839bc17800be4d7e8cd1e3ac8fafa344
        flow = self._flows.get(user_id)
        if not flow or flow.mode != "qr" or not flow.qr_login:
            return None, None
        try:
            await flow.qr_login.wait(timeout=timeout)
        except Exception:
            return None, None
        me = await flow.client.get_me()
        session_string = flow.client.session.save()
        await flow.client.disconnect()
        self._flows.pop(user_id, None)
        phone = getattr(me, "phone", None)
        return session_string, phone

    def submit_web(self, token: str, code: Optional[str], password: Optional[str]) -> bool:
        user_id = self._token_index.get(token)
        if not user_id:
            return False
        flow = self._flows.get(user_id)
        if not flow or flow.mode != "web":
            return False
        if code:
            flow.code = code.strip()
        if password:
            flow.password = password.strip()
        return True

<<<<<<< HEAD
    async def confirm_web(self, user_id: int) -> Tuple[Optional[str], Optional[str], str]:
=======
    async def confirm_web(self, user_id: int) -> tuple[Optional[str], Optional[str], str]:
>>>>>>> 9dd19731839bc17800be4d7e8cd1e3ac8fafa344
        flow = self._flows.get(user_id)
        if not flow or flow.mode != "web":
            return None, None, "FAILED"
        if not flow.code:
            return None, None, "WAIT_CODE"
        try:
            await flow.client.sign_in(phone=flow.phone, code=flow.code)
        except SessionPasswordNeededError:
            flow.needs_password = True
            if not flow.password:
                return None, None, "NEED_PASSWORD"
            try:
                await flow.client.sign_in(password=flow.password)
            except Exception:
                return None, None, "FAILED"
        except Exception:
            return None, None, "FAILED"
        session_string = flow.client.session.save()
        await flow.client.disconnect()
        self._flows.pop(user_id, None)
        if flow.web_token:
            self._token_index.pop(flow.web_token, None)
        return session_string, flow.phone, "DONE"

    async def cancel(self, user_id: int) -> None:
        flow = self._flows.pop(user_id, None)
        if flow and flow.web_token:
            self._token_index.pop(flow.web_token, None)
        if flow and flow.client.is_connected():
            await flow.client.disconnect()
