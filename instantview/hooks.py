"""Event handlers and hooks"""

from argparse import Namespace

from deltabot_cli import BotCli
from deltachat2 import Bot, ChatType, CoreEvent, EventType, MsgData, NewMsgEvent, events
from rich.logging import RichHandler

from ._version import __version__
from .web import get_url, send_preview

cli = BotCli("instantview-bot")
cli.add_generic_option("-v", "--version", action="version", version=__version__)
cli.add_generic_option(
    "--no-time",
    help="do not display date timestamp in log messages",
    action="store_false",
)
HELP = (
    "I am a Delta Chat bot, send me any website URL to get a minimal preview."
    " Example: https://delta.chat"
)


@cli.on_init
def on_init(bot: Bot, args: Namespace) -> None:
    bot.logger.handlers = [
        RichHandler(show_path=False, omit_repeated_times=False, show_time=args.no_time)
    ]
    for accid in bot.rpc.get_all_account_ids():
        if not bot.rpc.get_config(accid, "displayname"):
            bot.rpc.set_config(accid, "displayname", "www")
            bot.rpc.set_config(accid, "selfstatus", HELP)
            bot.rpc.set_config(accid, "delete_device_after", str(60 * 60 * 24))


@cli.on(events.RawEvent)
def log_event(bot: Bot, accid: int, event: CoreEvent) -> None:
    if event.kind == EventType.INFO:
        bot.logger.debug(event.msg)
    elif event.kind == EventType.WARNING:
        bot.logger.warning(event.msg)
    elif event.kind == EventType.ERROR:
        bot.logger.error(event.msg)
    elif event.kind == EventType.MSG_DELIVERED:
        bot.rpc.delete_messages(accid, [event.msg_id])
    elif event.kind == EventType.SECUREJOIN_INVITER_PROGRESS:
        if event.progress == 1000:
            if not bot.rpc.get_contact(accid, event.contact_id).is_bot:
                bot.logger.debug("QR scanned by contact id=%s", event.contact_id)
                chatid = bot.rpc.create_chat_by_contact_id(accid, event.contact_id)
                send_help(bot, accid, chatid)


@cli.after(events.NewMessage)
def delete_msgs(bot: Bot, accid: int, event: NewMsgEvent) -> None:
    bot.rpc.delete_messages(accid, [event.msg.id])


@cli.on(events.NewMessage(is_info=False))
def on_msg(bot: Bot, accid: int, event: NewMsgEvent) -> None:
    """Extract the URL from the incoming message and send a preview."""
    if bot.has_command(event.command):
        return
    msg = event.msg
    chat = bot.rpc.get_basic_chat_info(accid, msg.chat_id)
    if chat.chat_type == ChatType.SINGLE:
        bot.rpc.markseen_msgs(accid, [msg.id])
    url = get_url(msg.text)
    if url:
        try:
            send_preview(bot, accid, msg, url)
        except Exception as ex:
            bot.logger.exception(ex)


@cli.on(events.NewMessage(command="/help"))
def _help(bot: Bot, accid: int, event: NewMsgEvent) -> None:
    bot.rpc.markseen_msgs(accid, [event.msg.id])
    send_help(bot, accid, event.msg.chat_id)


def send_help(bot: Bot, accid: int, chatid: int) -> None:
    bot.rpc.send_msg(accid, chatid, MsgData(text=HELP))
