#!/usr/bin/env python3

import os
import re
import logging
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message


from dotenv import load_dotenv

from clients import TonViewerClient, GeckoTerminalClient
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
bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

tv_client = TonViewerClient(
    "https://tonapi.io/v2",
    auth="AEY3CRGXLSSUGQIAAAAEFEU3GVXEWZFOORXSKXOIJKOYAJ5IGM2GCSLWPFBORPY26WM5DUI",
)
gt_client = GeckoTerminalClient("https://api.geckoterminal.com/api/v2")
ton = Ton(tv_client, gt_client)
# telegram_client = TelegramBotClient(TELEGRAM_BOT_TOKEN)


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer("Hello, add me to your chat!")


@dp.message()
async def token_handler(message: Message) -> None:
    if not isinstance(message.text, str):
        return

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
                total_airdrop_percent=total_airdrop,
            )
            await message.answer(**text)
        except Exception as e:
            logging.error(f"Error while processing token {address}: {e}")
            await message.answer(
                f"Error while processing token {address}: {e}"
            )


async def run_scheduler(ton, bot, chat_id, schedule_minutes, pages):
    while True:
        await process_new_pools(
            ton, bot, chat_id, pages, TokenReport.TelegramMessage
        )
        await asyncio.sleep(schedule_minutes * 60)


async def run_bot():
    await dp.start_polling(bot)


async def main():
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
            asyncio.create_task(
                run_scheduler(
                    ton,
                    bot,
                    TELEGRAM_CHAT_ID,
                    cli_args.schedule,
                    cli_args.pages,
                )
            )
        await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
