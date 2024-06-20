"""Web scrapping"""

import functools
import mimetypes
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote_plus

import bs4
import requests
from deltachat2 import Bot, Message, MsgData

session = requests.Session()
session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:104.0)"
            " Gecko/20100101 Firefox/104.0"
        )
    }
)
session.request = functools.partial(session.request, timeout=15)  # type: ignore
url_regex = re.compile(
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)
MAX_SIZE = 1024**2 * 15


def get_url(text: str) -> str:
    """Extract URL from text."""
    match = url_regex.search(text)
    if match:
        return match.group()
    return ""


def send_preview(bot: Bot, accid: int, msg: Message, url: str) -> None:
    """Fetch URL and send a preview reply if file is not too big"""
    with session.get(url, stream=True) as resp:
        resp.raise_for_status()
        url = resp.url
        content_type = resp.headers.get("content-type", "").lower()
        content_size = int(resp.headers.get("content-size") or -1)
        content = b""
        if content_size < MAX_SIZE:
            size = 0
            for chunk in resp.iter_content(chunk_size=102400):
                size += len(chunk)
                if size > MAX_SIZE:
                    del content
                    break
                content += chunk
        else:
            size = content_size
    reply = MsgData(quoted_message_id=msg.id)
    if size > MAX_SIZE:
        typ = content_type.split(";")[0] or "-"
        reply.text = f"Type: {typ}\nSize: >{_sizeof_fmt(MAX_SIZE)}"
        bot.rpc.send_msg(accid, msg.chat_id, reply)
    elif "text/html" in content_type:
        addr = bot.rpc.get_config(accid, "configured_addr")
        reply.text, reply.html = prepare_html(addr, url, content)
        bot.rpc.send_msg(accid, msg.chat_id, reply)
    else:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir, f"file{get_extension(resp)}")
            with path.open("wb") as file:
                file.write(content)
            reply.file = str(path)
            bot.rpc.send_msg(accid, msg.chat_id, reply)


def get_extension(resp: requests.Response) -> str:
    """Get file extension based in response content"""
    disp = resp.headers.get("content-disposition")
    if disp is not None and re.findall("filename=(.+)", disp):
        fname = re.findall("filename=(.+)", disp)[0].strip('"')
    else:
        fname = resp.url.split("/")[-1].split("?")[0].split("#")[0]
    if "." in fname:
        ext = "." + fname.rsplit(".", maxsplit=1)[-1]
    else:
        ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        ext = mimetypes.guess_extension(ctype) or ""
    return ext


def _sizeof_fmt(num: float) -> str:
    suffix = "B"
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)  # noqa
        num /= 1024.0
    return "%.1f%s%s" % (num, "Yi", suffix)  # noqa


def prepare_html(
    bot_addr: str, url: str, content: bytes, link_prefix: str = ""
) -> tuple:
    """Sanitize HTML.

    Returns a tuple with page title and sanitized HTML.
    """
    soup = bs4.BeautifulSoup(content, "html5lib")

    _remove_unused_tags(soup)

    # fix URLs
    index = url.find("/", 8)
    if index == -1:
        root = url
    else:
        root = url[:index]
        url = url.rsplit("/", 1)[0]
    tags = (
        ("a", "href", ("mailto:", "openpgp4fpr:", "#")),
        ("img", "src", "data:"),
        ("source", "src", "data:"),
        ("link", "href", None),
    )
    for tag, attr, iprefix in tags:
        for element in soup(tag, attrs={attr: True}):
            if iprefix and element[attr].lower().startswith(iprefix):
                continue
            element[attr] = re.sub(
                r"^(//.*)", rf"{root.split(':', 1)[0]}:\1", element[attr]
            )
            element[attr] = re.sub(r"^(/.*)", rf"{root}\1", element[attr])
            if not re.match(r"^\w+:", element[attr]):
                element[attr] = f"{url}/{element[attr]}"
            if tag == "a":
                element[attr] = (
                    f"mailto:{bot_addr}?body={quote_plus(link_prefix + element['href'])}"
                )

    title = soup.title and soup.title.get_text().strip()
    return (title or "Page without title", str(soup))


def _remove_unused_tags(soup: bs4.BeautifulSoup) -> None:
    for tag in soup("script"):
        tag.extract()
    for tag in soup(["button", "input"]):
        if tag.has_attr("type") and tag["type"] == "hidden":
            tag.extract()
    for tag in soup.find_all(text=lambda text: isinstance(text, bs4.Comment)):
        tag.extract()
