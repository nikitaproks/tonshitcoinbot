#!/usr/bin/env python3

import os
import re
import logging
import time
import threading
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message


import schedule
from dotenv import load_dotenv

from clients import TonViewerClient, GeckoTerminalClient, TelegramBotClient
from classes import Ton
from functions import (
    collect_arguments,
    get_jetton_info,
    process_new_pools,
    build_cli_jetton_info,
    build_telegram_jetton_message,
)
from models import TokenReport


load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TON_VIEWER_API_KEY = os.getenv("TON_VIEWER_API_KEY")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

address_regex = r"^[EU]Q[A-Za-z0-9_-]{46}$"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logging.getLogger("httpx").setLevel(logging.ERROR)

dp = Dispatcher()
tv_client = TonViewerClient(
    "https://tonapi.io/v2",
    auth="AEY3CRGXLSSUGQIAAAAEFEU3GVXEWZFOORXSKXOIJKOYAJ5IGM2GCSLWPFBORPY26WM5DUI",
)
gt_client = GeckoTerminalClient("https://api.geckoterminal.com/api/v2")
ton = Ton(tv_client, gt_client)
telegram_client = TelegramBotClient(TELEGRAM_BOT_TOKEN)


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer("Hello, add me to your chat!")


@dp.message()
async def token_handler(message: Message) -> None:
    addresses = re.findall(address_regex, message.text)
    if not addresses:
        return
    logging.info(f"Got addresses to scan: {addresses}")
    for address in addresses:
        try:
            (
                jetton_master,
                pools_masters,
                airdrop_receivers,
                total_airdrop,
            ) = get_jetton_info(ton, address)

            if not pools_masters:
                await message.answer(
                    f"No liquidity pools found for token {address}"
                )
                return

            liquidity_state = ton.check_liquidity_state(pools_masters[0])
            text = build_telegram_jetton_message(
                jetton_master,
                liquidity_state,
                pools_masters[0].account.address_b64,
                airdrop_receivers=airdrop_receivers,
                total_airdrop=total_airdrop,
            )
            await message.answer(text)
        except Exception as e:
            logging.error(f"Error while processing token {address}: {e}")
            await message.answer(
                f"Error while processing token {address}: {e}"
            )


def run_scheduler(
    ton: Ton,
    telegram_client: TelegramBotClient,
    schedule_minutes: int,
    pages: int,
):
    logging.info(f"Running scan every {schedule_minutes} minutes")
    schedule.every(schedule_minutes).minutes.do(
        process_new_pools,
        ton=ton,
        telegram_client=telegram_client,
        chat_id=TELEGRAM_CHAT_ID,
        pages=pages,
        report=TokenReport.TelegramMessage,
    )
    # Initial run
    process_new_pools(
        ton,
        telegram_client,
        TELEGRAM_CHAT_ID,
        pages,
        report=TokenReport.TelegramMessage,
    )
    # Run scheduler
    while True:
        schedule.run_pending()
        time.sleep(1)


async def run_bot():
    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await dp.start_polling(bot)


def main():
    cli_args = collect_arguments()
    if cli_args.info is not None:
        logging.info(f"Getting info for jetton {cli_args.info}")
        (
            jetton_master,
            pools_masters,
            airdrop_receivers,
            total_airdrop,
        ) = get_jetton_info(ton, cli_args.info)
        print(
            build_cli_jetton_info(
                jetton_master,
                pools_masters,
                airdrop_receivers=airdrop_receivers,
                total_airdrop=total_airdrop,
            )
        )
    elif cli_args.new:
        if cli_args.schedule:
            scheduler_thread = threading.Thread(
                target=run_scheduler,
                args=(
                    ton,
                    telegram_client,
                    cli_args.schedule,
                    cli_args.pages,
                ),
            )
            logging.info("Starting scheduler thread")
            scheduler_thread.start()
            logging.info("Running bot")
            asyncio.run(run_bot())
            scheduler_thread.join()

        else:
            logging.info("Running scan once")
            process_new_pools(
                ton, telegram_client, TELEGRAM_CHAT_ID, cli_args.pages
            )


if __name__ == "__main__":
    main()
