import csv
import os
import logging
from datetime import datetime, timedelta, UTC, timezone

import argparse
from tqdm import tqdm

from clients import TelegramBotClient
from classes import Ton
from models import JettonMaster, LiquidityState, TokenReport

logger = logging.getLogger(__name__)


def read_csv(file_path) -> list[list[str]]:
    data = []
    if os.path.exists(file_path):
        with open(file_path, mode="r", newline="") as file:
            reader = csv.reader(file)
            data = list(reader)
    else:
        with open(file_path, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerows(data)
    return data


def append_csv(file_path, data: list[list[str | int]]):
    with open(file_path, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerows(data)


def build_cli_jetton_info(
    jetton_master: JettonMaster,
    pools_masters: list[JettonMaster],
    airdrop_receivers: dict[str, dict] = {},
    total_airdrop: float = 0.0,
):
    print(
        f"\nJetton: {jetton_master.data.metadata.name} ({jetton_master.data.metadata.symbol})\nSocials: \n{'\n'.join(jetton_master.data.metadata.socials)}\n"
    )

    print(f"Mintable: {jetton_master.data.mintable}")
    print(
        f"Ownership revoked: {jetton_master.admin_address == '0:0000000000000000000000000000000000000000000000000000000000000000'}"
    )
    print(f"Admin address: {jetton_master.admin_address}")
    print(f"Creators address: {jetton_master.creator.account.address}")
    print()
    print(f"Creators holdings after airdrop: {100.0-total_airdrop}%")
    print(f"Airdrop total amount: {total_airdrop}%")
    print(f"\nAirdrop receivers: {len(airdrop_receivers)}")
    for i, (address, data) in enumerate(airdrop_receivers.items()):
        string = f"{i}.\t{round(data["amount"]/jetton_master.data.total_supply*100, 2)}% \t {address}"
        if data["name"]:
            string += f" ({data["name"]})"
        print(string)
    print()
    print(f"Top 10 sum: {jetton_master.calculate_top_ten_percent()}")
    print(jetton_master.build_top_ten_message())

    print("Liquidities:")
    for pool_master in pools_masters:
        print(pool_master.build_top_ten_message())


def get_jetton_info(ton: Ton, jetton_master_address_b64: str):
    jetton_master = ton.get_jetton_master(jetton_master_address_b64)
    pools_masters = ton.get_jetton_pools(jetton_master_address_b64)

    # Processing airdrops
    airdrop_receivers, airdrop_sum = ton.process_airdrops(jetton_master)
    total_airdrop = round(
        airdrop_sum / jetton_master.data.total_supply * 100,
        2,
    )
    return jetton_master, pools_masters, airdrop_receivers, total_airdrop


def build_telegram_jetton_message(
    jetton_master: JettonMaster,
    liquidity_state: LiquidityState,
    liquidity_master_address_b64: str,
    airdrop_receivers: dict[str, dict] = {},
    total_airdrop_percent: float = 0.0,
):
    message: str = "💹💹💹💹💹💹💹💹"
    message += f"\n💩<b>Jetton: {jetton_master.data.metadata.name} ({jetton_master.data.metadata.symbol})</b>💩"
    message += f"\n<b>Address:</b> {jetton_master.account.address_b64}"
    message += "\n"
    message += f"\n<b>Socials:</b> {'\n' + '\n'.join(jetton_master.data.metadata.socials) if jetton_master.data.metadata.socials else "No socials found" }"
    message += "\n"
    message += f"\n<b>Contract:</b> {'Custom (MIGHT BE A SCAM)' if jetton_master.used_cells <42 else 'Seems okay'}"
    message += f"\n<b>Mintable:</b> {jetton_master.data.mintable}"
    message += f"\n<b>Ownership revoked:</b> {jetton_master.admin_address == '0:0000000000000000000000000000000000000000000000000000000000000000'}"
    message += f"\n<b>Liquidity:</b> {liquidity_state.name}"
    message += f"\n<b>Airdrop:</b> amount - {total_airdrop_percent}%, receivers - {len(airdrop_receivers)}"
    message += "\n"
    message += jetton_master.build_top_ten_message()
    message += "\n"
    message += f"https://www.geckoterminal.com/ton/pools/{liquidity_master_address_b64}"
    return message


def is_token_to_process(
    token_address: str, scanned_tokens: list[list[str | int]]
) -> bool:
    clone_tokens = [token[:] for token in scanned_tokens]
    for token in clone_tokens:
        if token[2] == token_address:
            created_at, _, token_address, is_good = token
            created_at_dt = datetime.strptime(
                created_at, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
            if int(is_good) == 1 or created_at_dt < datetime.now(
                UTC
            ) - timedelta(hours=2):
                return False
            else:
                scanned_tokens.remove(token)
                return True
    return True


def process_new_pools(
    ton: Ton,
    telegram_client: TelegramBotClient,
    chat_id: str,
    pages: int,
    report: TokenReport = TokenReport.ConsolePrint,
) -> str:
    logger.info(f"Processing {pages} pages of new pools")
    addresses = ton.get_new_pools_and_tokens_addresses(pages)
    logger.info(f"Found {len(addresses)} new pools")

    scanned_tokens = read_csv("scanned_tokens.csv")
    logger.info("Processing pools")
    pbar = tqdm(addresses)
    for created_at, pool_address, token_address in addresses:
        try:
            is_good: int = 0
            pbar.set_description(
                f"Processing pool {pool_address} with token {token_address}"
            )
            if not is_token_to_process(token_address, scanned_tokens):
                pbar.update(1)
                continue

            try:
                jetton_master = ton.get_jetton_master(token_address)
                liquidity_master = ton.get_jetton_master(
                    pool_address, type="pool"
                )
                airdrop_receivers, airdrop_sum = ton.process_airdrops(
                    jetton_master
                )
                total_airdrop_percent = round(
                    airdrop_sum / jetton_master.data.total_supply * 100,
                    2,
                )
                rating = ton.rate_jetton(
                    jetton_master, liquidity_master, total_airdrop_percent
                )
                if rating >= 4:
                    if report == TokenReport.ConsolePrint:
                        build_cli_jetton_info(
                            jetton_master,
                            [liquidity_master],
                            airdrop_receivers=airdrop_receivers,
                            total_airdrop=total_airdrop_percent,
                        )
                    elif report == TokenReport.TelegramMessage:
                        liquidity_state = ton.check_liquidity_state(
                            liquidity_master
                        )
                        logger.info(f"Sending message for pool {pool_address}")
                        liquidity_state = ton.check_liquidity_state(
                            liquidity_master
                        )
                        telegram_client.send_message(
                            chat_id,
                            build_telegram_jetton_message(
                                jetton_master,
                                liquidity_state,
                                liquidity_master.account.address_b64,
                                airdrop_receivers=airdrop_receivers,
                                total_airdrop_percent=total_airdrop_percent,
                            ),
                        )
                    is_good = 1
                del jetton_master, liquidity_master

            except Exception as e:
                logger.error(f"Error processing pool {pool_address}: {e}")

            scanned_tokens.append(
                [created_at, pool_address, token_address, is_good]
            )
            pbar.update(1)
        except KeyboardInterrupt:
            break
    pbar.close()
    logger.info("Saving scanned tokens")
    append_csv("scanned_tokens.csv", scanned_tokens)
    logger.info("Finished processing pools")


def collect_arguments():
    parser = argparse.ArgumentParser(description="Ton jetton info scanner")
    parser.add_argument(
        "--pages",
        default=10,
        type=int,
        help="Number of pages of new pools to scan",
    )
    parser.add_argument(
        "--schedule", type=int, help="Number of minutes to wait between scans"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--info",
        type=str,
        help="Scan info for a specific jetton",
    )
    group.add_argument(
        "--new", action="store_true", help="Run a scan for new pools"
    )
    args = parser.parse_args()
    return args
