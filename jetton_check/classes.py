from datetime import datetime, UTC

from clients import TonViewerClient, GeckoTerminalClient
from models import (
    Event,
    ActionType,
    Account,
    Wallet,
    JettonMaster,
    AccountData,
    LiquidityState,
)


class Ton:
    def __init__(
        self, tv_client: TonViewerClient, gt_client: GeckoTerminalClient
    ):
        self.tv_client = tv_client
        self.gt_client = gt_client

    def check_liquidity_state(
        self,
        liquidity_master: JettonMaster,
    ) -> LiquidityState:
        top_ten = liquidity_master.get_top_ten()
        top_liq_holder = top_ten[0] if top_ten else None
        if not top_liq_holder:
            return LiquidityState.NoHolders

        if top_liq_holder.balance / liquidity_master.data.total_supply < 0.7:
            return LiquidityState.NotSafe

        if top_liq_holder.account.address == LiquidityState.Burned.value:
            return LiquidityState.Burned

        if top_liq_holder.account.address == LiquidityState.TonInuLocked.value:
            return LiquidityState.TonInuLocked

        return LiquidityState.NotSafe

    def rate_jetton(
        self,
        jetton_master: JettonMaster,
        liquidity_master: JettonMaster,
        total_airdrop: float,
    ) -> int:
        rating = 0
        if (
            jetton_master.admin_address
            == "0:0000000000000000000000000000000000000000000000000000000000000000"
        ):
            rating += 1

        if self.check_liquidity_state(liquidity_master) in [
            LiquidityState.Burned,
            LiquidityState.TonInuLocked,
            LiquidityState.Undefined,
        ]:
            rating += 1
        if (
            jetton_master.creator.balance / jetton_master.data.total_supply
            <= 0.1
        ):
            rating += 1

        if total_airdrop <= 20:
            rating += 1

        return rating

    def get_new_pools_and_tokens_addresses(
        self, pages: int
    ) -> list[tuple[str, str, str]]:
        new_pools_datas = []
        for i in range(1, pages + 1):
            new_pools_datas.extend(
                self.gt_client.get_new_pools(page=i)["data"]
            )
        result = []
        for new_pool_data in new_pools_datas:
            fdv_usd = float(new_pool_data["attributes"]["fdv_usd"])
            reserve_usd = float(new_pool_data["attributes"]["reserve_in_usd"])
            if fdv_usd < 2000 or reserve_usd / fdv_usd < 0.05:
                continue
            creation = new_pool_data["attributes"]["pool_created_at"]
            pool_address = new_pool_data["attributes"]["address"]
            token_address = new_pool_data["relationships"]["base_token"][
                "data"
            ]["id"][4:]
            result.append((creation, pool_address, token_address))
        return result

    def get_jetton_pools(
        self, jetton_master_address_b64: str
    ) -> list[JettonMaster]:
        pools_datas = self.gt_client.get_jetton_pools(
            jetton_master_address_b64
        )["data"]
        pools_datas_sorted = sorted(
            pools_datas,
            key=lambda x: x["attributes"]["fdv_usd"],
            reverse=True,
        )
        pools_addresses = [
            pool_data["attributes"]["address"]
            for pool_data in pools_datas_sorted
        ]

        return [self.get_jetton_master(pa) for pa in pools_addresses]

    def get_jetton_admin_address(self, address: str) -> str:
        data = self.tv_client.execute_account_method(
            address, "get_jetton_data"
        )
        return data["decoded"]["admin_address"]

    def get_creator_wallet(
        self, jetton_master_events: list[Event]
    ) -> Wallet | None:
        creator_jetton_wallet_data: AccountData = None
        creator_account_data: AccountData = None
        for event in jetton_master_events:
            for action in event.actions:
                if (
                    action.type == ActionType.SmartContractExec
                    and action.SmartContractExec.operation
                    == "JettonInternalTransfer"
                ):
                    creator_jetton_wallet_data = (
                        action.SmartContractExec.contract
                    )
                elif (
                    action.type == ActionType.SmartContractExec
                    and action.SmartContractExec.operation == "0x00000015"
                ):
                    creator_account_data = action.SmartContractExec.executor

                if creator_jetton_wallet_data and creator_account_data:
                    break

        if not creator_jetton_wallet_data or not creator_account_data:
            return None

        creator_account = self.tv_client.get_account(
            creator_account_data.address
        )
        creator_account_events = self.tv_client.get_account_events(
            creator_jetton_wallet_data.address,
            int(datetime.now(UTC).timestamp()),
        )
        creator_account.events = creator_account_events
        balance = self.tv_client.execute_account_method(
            creator_jetton_wallet_data.address, "get_wallet_data"
        )["decoded"]["balance"]
        return Wallet(
            account=creator_account,
            balance=balance,
            jetton_wallet=creator_jetton_wallet_data.address,
        )

    def get_holders(
        self,
        jetton_master_address_b64: str,
        creator_address: str | None = None,
    ) -> list[Wallet]:
        holders_data = self.tv_client.get_jetton_holders(
            jetton_master_address_b64
        )

        holders = []
        non_wallet_holder_datas = []
        for holder in holders_data:
            if not holder["owner"]["is_wallet"]:
                non_wallet_holder_datas.append(holder)
            else:
                if holder["owner"].get("name"):
                    name = holder["owner"]["name"]
                elif creator_address == holder["owner"]["address"]:
                    name = "Creator"
                else:
                    name = None

                holders.append(
                    Wallet(
                        account=Account(
                            address=holder["owner"]["address"],
                            is_wallet=holder["owner"]["is_wallet"],
                            name=name,
                        ),
                        jetton_wallet=holder["address"],
                        balance=holder["balance"],
                    )
                )

        non_wallet_accounts: list[Account] = []
        for start in range(0, len(non_wallet_holder_datas), 100):
            end = (
                start + 100
                if start + 100 < len(non_wallet_holder_datas)
                else len(non_wallet_holder_datas)
            )
            addresses = [
                holder["owner"]["address"]
                for holder in non_wallet_holder_datas[start:end]
            ]
            non_wallet_accounts += self.tv_client.get_accounts_bulk(addresses)

        for account in non_wallet_accounts:
            if account.address == LiquidityState.TonInuLocked.value:
                account.name = "TON Inu Locker"

            balance: str
            jetton_wallet: str
            for data in non_wallet_holder_datas:
                if data["owner"]["address"] == account.address:
                    balance = data["balance"]
                    jetton_wallet = data["address"]

            holders.append(
                Wallet(
                    account=account,
                    jetton_wallet=jetton_wallet,
                    balance=balance,
                )
            )

        return holders

    def get_jetton_master(
        self, jetton_master_address_b64: str, type="jetton"
    ) -> JettonMaster:
        data = self.tv_client.get_jetton_data(jetton_master_address_b64)
        admin_address = (
            self.get_jetton_admin_address(jetton_master_address_b64)
            if type == "jetton"
            else "None"
        )
        events = self.tv_client.get_account_events(
            jetton_master_address_b64,
            int(datetime.now(UTC).timestamp()),
        )
        account = self.tv_client.get_account(jetton_master_address_b64)
        creator = self.get_creator_wallet(events)
        holders = self.get_holders(
            jetton_master_address_b64,
            creator_address=creator.account.address if creator else None,
        )
        address_b64 = self.tv_client.parse_account(account.address)[
            "bounceable"
        ]["b64url"]
        account.address_b64 = address_b64

        return JettonMaster(
            account=account,
            admin_address=admin_address,
            data=data,
            creator=creator,
            holders=holders,
            events=events,
        )

    def process_airdrops(
        self, jetton_master: JettonMaster
    ) -> tuple[dict[str, dict], int]:
        creator_jetton_events: list[
            Event
        ] = self.tv_client.get_account_jetton_event_history(
            jetton_master.creator.account.address,
            jetton_master.data.metadata.address,
            int(datetime.now(UTC).timestamp()),
        )
        airdrop_receivers: dict[str, dict] = {}
        for event in creator_jetton_events:
            for action in event.actions:
                if (
                    action.type == ActionType.JettonTransfer
                    and action.JettonTransfer.sender.address
                    == jetton_master.creator.account.address
                    and action.JettonTransfer.comment != "Call: DedustSwap"
                ):
                    key = action.JettonTransfer.recipient.address
                    if key not in airdrop_receivers:
                        airdrop_receivers[key] = {
                            "amount": 0,
                            "name": action.JettonTransfer.recipient.name
                            if action.JettonTransfer.recipient
                            else None,
                        }

                    airdrop_receivers[key]["amount"] += int(
                        action.JettonTransfer.amount
                    )

        for holder in jetton_master.holders:
            if holder.account.address in airdrop_receivers:
                airdrop_receivers[holder.account.address][
                    "name"
                ] = holder.account.name
                holder.airdrop_amount = airdrop_receivers[
                    holder.account.address
                ]["amount"]

        filtered_receivers = {}
        airdrop_sum = 0
        for key, data in airdrop_receivers.items():
            if data["name"] not in ["Dedust Vault", "Stonfi Router"]:
                filtered_receivers[key] = data
                airdrop_sum += data["amount"]

        return filtered_receivers, airdrop_sum
