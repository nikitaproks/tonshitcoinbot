import threading
import time
import os
from pprint import pprint

import httpx

from dotenv import load_dotenv


class ApiClient:
    def __init__(self, url: str, auth: str = None, pause_seconds: int = 1):
        self.url = url
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {auth}"
        self.client = httpx.Client(headers=headers)
        self.last_exec: float = 0.0
        self.pause_seconds = pause_seconds
        self.semaphore = threading.Semaphore(pause_seconds)

    def _request(
        self, method: str, url: str, data: dict | None = None
    ) -> dict:
        with self.semaphore:
            time.sleep(self.pause_seconds)
            response = self.client.request(method, url, json=data)

            if response.status_code > 299:
                raise Exception(response.json())

            return response.json()


class TonViewerClient(ApiClient):
    def execute_account_method(self, address: str, method: str) -> dict:
        return self._request(
            "GET",
            f"{self.url}/blockchain/accounts/{address}/methods/{method}",
        )

    def low_level_account_info(self, address: str) -> dict:
        return self._request(
            "GET",
            f"{self.url}/blockchain/accounts/{address}",
        )


load_dotenv()


TON_VIEWER_API_KEY = os.getenv("TON_VIEWER_API_KEY")

tv_client = TonViewerClient("https://tonapi.io/v2", pause_seconds=2)


addresses = [
    "EQD5VcjYY2LNARcGyGrG8eT0Wrq5j6RYfel2xLB-1lV4uBK_",
    "EQC4TawpHpDjG8XEEQW6mYPqpFKb1Th6g4aj6RBWa2ndQrhD",
    "EQBjxFh6EQoAlkgtuICaeWNheu3ycuVxfUksyDGgtQMkYQFE",
]
results = []
for address in addresses:
    res = tv_client.low_level_account_info(address)
    results.append(res["storage"]["used_cells"])
pprint(results)
