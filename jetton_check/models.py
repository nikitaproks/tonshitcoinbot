import re
from enum import Enum
from pydantic import BaseModel, model_validator


class AccountData(BaseModel):
    address: str
    name: str | None = None
    is_scam: bool
    is_wallet: bool


class JettonMetadata(BaseModel):
    address: str
    name: str
    symbol: str
    decimals: int
    description: str | None = None
    socials: list[str] | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_fields(cls, values: dict):
        regex = r"(https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|www\.[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9]+\.[^\s]{2,}|www\.[a-zA-Z0-9]+\.[^\s]{2,})"
        if (description := values.get("description")) is None:
            return values
        socials: list[str] = values.get("socials", [])
        matches = re.findall(regex, description)
        if matches:
            socials += matches

        values["socials"] = socials
        return values


class ActionType(str, Enum):
    SmartContractExec = "SmartContractExec"
    ContractDeploy = "ContractDeploy"
    JettonSwap = "JettonSwap"
    JettonTransfer = "JettonTransfer"
    TonTransfer = "TonTransfer"
    JettonMint = "JettonMint"


class LiquidityState(Enum):
    Burned = (
        "0:0000000000000000000000000000000000000000000000000000000000000000"
    )
    TonInuLocked = (
        "0:f7d8b5faf56677ef9349d32f1be567722b4dd756378e6835ae580553ba2a3563"
    )
    NoHolders = "No owners"
    NotSafe = "Other"
    Undefined = "undefined"


class TokenReport(str, Enum):
    TelegramMessage = "TelegramMessage"
    ConsolePrint = "ConsolePrint"


class Action(BaseModel):
    type: ActionType
    status: str
    simple_preview: dict


class SmartContractExec(BaseModel):
    executor: AccountData
    contract: AccountData
    ton_attached: int
    operation: str
    payload: str | None = None


class JettonTransfer(BaseModel):
    sender: AccountData
    recipient: AccountData
    senders_wallet: str
    recipients_wallet: str
    amount: int
    comment: str | None = None
    jetton: JettonMetadata


class JettonSwap(BaseModel):
    dex: str
    amount_in: str
    amount_out: str | None = None
    ton_out: int | None = None
    user_wallet: AccountData
    router: AccountData
    jetton_master_in: JettonMetadata | None = None


class JettonMint(BaseModel):
    recipient: AccountData
    recipients_wallet: str
    amount: int
    jetton: JettonMetadata


class TonTransfer(BaseModel):
    sender: AccountData
    recipient: AccountData
    amount: int


class SmartContractExecAction(Action):
    SmartContractExec: SmartContractExec


class ContractDeployAction(Action):
    ContractDeploy: dict


class JettonSwapAction(Action):
    JettonSwap: JettonSwap


class JettonTransferAction(Action):
    JettonTransfer: JettonTransfer


class TonTransferAction(Action):
    TonTransfer: TonTransfer


class JettonMintAction(Action):
    JettonMint: JettonMint


class Event(BaseModel):
    event_id: str
    account: AccountData
    timestamp: int
    actions: list[
        SmartContractExecAction
        | ContractDeployAction
        | JettonSwapAction
        | JettonTransferAction
        | TonTransferAction
        | JettonMintAction
    ]
    is_scam: bool
    in_progress: bool

    @model_validator(mode="before")
    @classmethod
    def check_correct_action(cls, values):
        actions = values.get("actions", [])
        new_actions = []
        for action in actions:
            action_type = action.get("type")
            if action_type == ActionType.SmartContractExec:
                new_actions.append(SmartContractExecAction(**action))
            elif action_type == ActionType.ContractDeploy:
                new_actions.append(ContractDeployAction(**action))
            elif action_type == ActionType.JettonSwap:
                new_actions.append(JettonSwapAction(**action))
            elif action_type == ActionType.JettonTransfer:
                new_actions.append(JettonTransferAction(**action))
            elif action_type == ActionType.TonTransfer:
                new_actions.append(TonTransferAction(**action))
            elif action_type == ActionType.JettonMint:
                new_actions.append(JettonMintAction(**action))
        values["actions"] = new_actions
        return values


class Account(BaseModel):
    address: str
    is_wallet: bool
    address_b64: str | None = None
    name: str | None = None
    interfaces: list[str] = []
    events: list[Event] = []

    @model_validator(mode="before")
    @classmethod
    def check(cls, values):
        name: str | None = None
        interfaces = values.get("interfaces", [])
        if not interfaces:
            return values
        if "dedust_vault" in interfaces:
            name = "Dedust Vault"
        elif "dedust_pool" in interfaces:
            name = "Dedust Pool"
        elif "stonfi_pool" in interfaces:
            name = "Stonfi Pool"
        elif "stonfi_router" in interfaces:
            name = "Stonfi Router"
        values["name"] = name
        return values


class Wallet(BaseModel):
    account: Account
    jetton_wallet: str
    balance: int
    airdrop_amount: int = 0
    events: list[Event] = []


class JettonData(BaseModel):
    mintable: bool
    total_supply: int
    metadata: JettonMetadata
    verification: str
    holders_count: int


class JettonMaster(BaseModel):
    account: Account
    admin_address: str
    data: JettonData
    used_cells: int
    creator: Wallet | None
    holders: list[Wallet] = []

    def calculate_holding(self, balance: int) -> float:
        return round(balance / self.data.total_supply * 100, 2)

    def get_holder_string(self, holder: Wallet, with_address: bool = False):
        string = f"{self.calculate_holding(holder.balance):.2f}% "
        if holder.airdrop_amount > 0:
            string += (
                f"(Airdrop {self.calculate_holding(holder.airdrop_amount)}%)"
            )
        string += " \t "
        if with_address:
            string += f"\t  {holder.account.address}"
        if holder.account.name:
            string += f" {holder.account.name}"
        return string

    def get_top_ten(self):
        return sorted(self.holders, key=lambda x: x.balance, reverse=True)[:10]

    def calculate_top_ten_percent(self):
        total = sum(holder.balance for holder in self.get_top_ten())
        return self.calculate_holding(total)

    def build_top_ten_message(self, with_address: bool = False):
        top_ten = self.get_top_ten()
        message = f"\nTop 10 - {self.calculate_top_ten_percent()}%\n"
        for i, holder in enumerate(top_ten):
            message += f"{i+1}. \t {self.get_holder_string(holder, with_address=with_address)}\n"
        return message
