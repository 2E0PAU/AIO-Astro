"""Alpaca HTTP envelopes, identifiers, and form encoding in one place."""

import asyncio
from dataclasses import dataclass
from itertools import count
from typing import Any

import httpx

from aio_astro import __version__
from aio_astro.domain.errors import DeviceError, ProtocolError


class AlpacaError(DeviceError):
    def __init__(self, number: int, message: str, *, operation: str = "") -> None:
        self.number = number
        self.operation = operation
        context = f" for {operation}" if operation else ""
        super().__init__(f"Alpaca error {number}{context}: {message}")


@dataclass(frozen=True, slots=True)
class ConfiguredDevice:
    name: str
    device_type: str
    number: int
    unique_id: str


class AlpacaClient:
    def __init__(
        self,
        base_url: str,
        *,
        client_id: int = 1,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        url = httpx.URL(base_url)
        if url.scheme not in ("http", "https") or not url.host or url.path not in ("", "/"):
            raise ValueError("Use an Alpaca server URL such as http://127.0.0.1:11111")
        if url.query or url.fragment or url.userinfo:
            raise ValueError("Alpaca server URLs cannot contain credentials, queries, or fragments")
        if not 0 <= client_id <= 65535:
            raise ValueError("Client ID must be in [0, 65535]")
        self._client_id = client_id
        self._transactions = count(1)
        self._http = httpx.AsyncClient(
            base_url=str(url),
            timeout=timeout,
            transport=transport,
            trust_env=False,
            headers={"Accept": "application/json", "User-Agent": f"AIO-Astro/{__version__}"},
        )

    async def __aenter__(self) -> "AlpacaClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    async def request(self, method: str, path: str, **params: Any) -> Any:
        transaction = next(self._transactions)
        values = {
            key: str(value).lower() if isinstance(value, bool) else str(value)
            for key, value in params.items()
        }
        values.update(ClientID=str(self._client_id), ClientTransactionID=str(transaction))
        try:
            if method == "GET":
                response = await self._http.get(path, params=values)
            elif method == "PUT":
                response = await self._http.put(path, data=values)
            else:
                raise ValueError("Alpaca requests must use GET or PUT")
            response.raise_for_status()
            # Large camera JSON arrays must not monopolise Qt's event-loop thread.
            payload = await asyncio.to_thread(response.json)
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:400].strip()
            raise ProtocolError(
                f"Alpaca {method} {path} returned HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ProtocolError(f"Alpaca {method} {path} failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise ProtocolError("Alpaca response must be an object")
        # Management envelopes omit device ErrorNumber/ErrorMessage fields in the standard.
        number = payload.get("ErrorNumber", 0 if path.startswith("/management/") else None)
        if type(number) is not int:
            raise ProtocolError("Alpaca response has no integer ErrorNumber")
        if number:
            raise AlpacaError(
                number,
                str(payload.get("ErrorMessage", "Unspecified driver error")),
                operation=f"{method} {path}",
            )
        # Some legacy devices return zero when they do not echo a client transaction ID.
        if payload.get("ClientTransactionID", 0) not in (0, transaction):
            raise ProtocolError("Alpaca response transaction does not match the request")
        return payload.get("Value")

    async def device(
        self, method: str, device_type: str, number: int, command: str, **params: Any
    ) -> Any:
        if number < 0 or not device_type.isalpha() or not command.isalpha():
            raise ValueError("Invalid Alpaca device path")
        return await self.request(
            method, f"/api/v1/{device_type.lower()}/{number}/{command.lower()}", **params
        )

    async def configured_devices(self) -> list[ConfiguredDevice]:
        value = await self.request("GET", "/management/v1/configureddevices")
        if not isinstance(value, list):
            raise ProtocolError("ConfiguredDevices must return an array")
        try:
            devices = []
            for item in value:
                if not isinstance(item, dict) or type(item["DeviceNumber"]) is not int:
                    raise ValueError("Invalid device number")
                if item["DeviceNumber"] < 0:
                    raise ValueError("Negative device number")
                for key in ("DeviceName", "DeviceType", "UniqueID"):
                    if not isinstance(item[key], str) or not item[key]:
                        raise ValueError(f"Invalid {key}")
                devices.append(
                    ConfiguredDevice(
                        item["DeviceName"],
                        item["DeviceType"],
                        item["DeviceNumber"],
                        item["UniqueID"],
                    )
                )
            return devices
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtocolError("Invalid ConfiguredDevices response") from exc
