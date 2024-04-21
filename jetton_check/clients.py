import threading
import time

import httpx

from models import (
    Event,
    Account,
    JettonData,
)

semaphore = threading.Semaphore(1)


class ApiClient:
    def __init__(self, url: str, auth: str = None, pause_seconds: int = 1):
        self.url = url
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {auth}"
        self.client = httpx.Client(headers=headers)
        self.last_exec: float = 0.0
        self.pause_seconds = pause_seconds

    def _request(
        self, method: str, url: str, data: dict | None = None
    ) -> dict:
        with semaphore:
            time.sleep(1)
            response = self.client.request(method, url, json=data)

            if response.status_code > 299:
                raise Exception(response.json())

            return response.json()


class TonViewerClient(ApiClient):
    def get_jetton_holders(
        self, address: str, limit: int = 1000, offset: int = 0
    ) -> list[dict]:
        response = self._request(
            "GET",
            f"{self.url}/jettons/{address}/holders?limit={limit}&offset={offset}",
        )
        return response["addresses"]

    def get_jetton_data(self, address: str) -> JettonData:
        return JettonData(
            **self._request("GET", f"{self.url}/jettons/{address}")
        )

    def get_account(self, address: str) -> Account:
        return Account(
            **self._request("GET", f"{self.url}/accounts/{address}")
        )

    def get_accounts_bulk(self, addresses: list[str]) -> list[Account]:
        accounts = self._request(
            "POST",
            f"{self.url}/accounts/_bulk",
            data={"account_ids": addresses},
        )["accounts"]
        return [Account(**a) for a in accounts]

    def get_account_events(
        self, address: str, end_timestamp: int, limit: int = 100
    ) -> dict:
        response = self._request(
            "GET",
            f"{self.url}/accounts/{address}/events?initiator=false&subject_only=false&limit={limit}&end_date={end_timestamp}",
        )
        return [Event(**e) for e in response["events"]]

    def get_account_jetton_event_history(
        self,
        account_address: str,
        jetton_address: int,
        end_timestamp: int,
        limit: int = 100,
    ) -> dict:
        response = self._request(
            "GET",
            f"{self.url}/accounts/{account_address}/jettons/{jetton_address}/history?initiator=false&subject_only=false&limit={limit}&end_date={end_timestamp}",
        )
        return [Event(**e) for e in response["events"]]

    def parse_account(self, address: str) -> str:
        return self._request("GET", f"{self.url}/address/{address}/parse")

    def get_account_jettons(self, address: str) -> list[str]:
        response = self._request(
            "GET", f"{self.url}/accounts/{address}/jettons"
        )
        return response["balances"]

    def execute_account_method(self, address: str, method: str) -> dict:
        return self._request(
            "GET",
            f"{self.url}/blockchain/accounts/{address}/methods/{method}",
        )


class GeckoTerminalClient(ApiClient):
    def get_jetton_pools(self, jetton_address: str):
        return self._request(
            "GET",
            f"{self.url}/networks/ton/tokens/{jetton_address}/pools",
        )

    def get_new_pools(self, page: int = 1):
        return self._request(
            "GET", f"{self.url}/networks/ton/new_pools?page={page}"
        )


class TelegramBotClient:
    def __init__(self, bot_token: str):
        self.url = f"https://api.telegram.org/bot{bot_token}"
        self.client = httpx.Client()

    def send_message(self, chat_id: str, text: str):
        return self.client.post(
            f"{self.url}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        )
