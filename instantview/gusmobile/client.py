# client.py
#
# Copyright 2019 Jason McBrayer
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import codecs
import collections
import fnmatch
import io
import mimetypes
import os.path
import random
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse
from email.message import EmailMessage


class Response:
    content = None
    content_type = None
    charset = None
    lang = None
    url = None
    status = None
    status_meta = None
    prompt = None
    num_bytes = None
    error_message = None

    def __init__(
        self,
        content=None,
        content_type=None,
        charset=None,
        lang=None,
        url=None,
        status=None,
        status_meta=None,
        prompt=None,
        num_bytes=None,
        error_message=None,
    ):
        self.content = content
        self.content_type = content_type
        self.charset = charset
        self.lang = lang
        self.url = url
        self.status = status
        self.status_meta = status_meta
        self.prompt = prompt
        self.num_bytes = num_bytes
        self.error_message = error_message


def fetch(raw_url):
    # Do everything which touches the network in one block,
    # so we only need to catch exceptions once
    url = urllib.parse.urlparse(raw_url, "gemini")
    header = ""
    try:
        # Is this a local file?
        if not url.netloc:
            print("ERROR: {} parses with no netloc".format(raw_url))
            f.close()
            return
        else:
            address, f = _send_request(url)
        # Read response header
        header = f.readline(1027)
        header = header.decode("UTF-8")
        if not header or header[-1] != "\n":
            _debug("ERROR: Received invalid header from server!")
            return
        header = header.strip()
        _debug("Response header: %s." % header)

    # Catch network errors which may happen on initial connection
    except Exception as err:
        # Print an error message
        if isinstance(err, socket.gaierror):
            print("ERROR: DNS error!")
            return
        elif isinstance(err, ConnectionRefusedError):
            print("ERROR: Connection refused!")
            return
        elif isinstance(err, ConnectionResetError):
            print("ERROR: Connection reset!")
            return
        elif isinstance(err, (TimeoutError, socket.timeout)):
            print(
                """ERROR: Connection timed out!
                Slow internet connection?  Use 'set timeout' to be more patient."""
            )
            return
        else:
            print("ERROR: " + str(err))
            return
    # Validate header
    header_split = header.split(maxsplit=1)
    if len(header_split) < 1:
        print("ERROR: Received invalid header from server!")
        f.close()
        return
    status = header_split[0]
    if len(header_split) > 1:
        meta = header_split[1]
    if len(header) > 1024 or len(status) != 2 or not status.isnumeric():
        print("ERROR: Received invalid header from server!")
        f.close()
        return

    # Handle headers. Not all headers are handled yet.
    # Input
    if status.startswith("1"):
        if len(header_split) < 2:
            print("ERROR: Input status requires a meta value in header!")
            return
        return Response(
            url=url.geturl(),
            status=status,
            prompt=meta,
        )
    # Redirects
    elif status.startswith("3"):
        if len(header_split) < 2:
            print("ERROR: Redirect status requires a meta value in header!")
            return
        return Response(
            url=urllib.parse.urlparse(meta).geturl(),
            status=status,
        )
    # Errors
    elif status.startswith("4") or status.startswith("5"):
        if len(header_split) < 2:
            print("ERROR: Error status requires a meta value in header!")
            return
        return Response(
            status=status,
            error_message=meta,
        )
        return
    # Client cert
    elif status.startswith("6"):
        print("ERROR: The requested resource requires client-certificate")
        return
    # Invalid status
    elif not status.startswith("2"):
        print("ERROR: Server returned undefined status code %s!" % status)
        return

    # Handle success
    assert status.startswith("2")
    if len(header_split) < 2:
        print("ERROR: Success status requires a meta value in header!")
        return
    mime = meta
    if mime == "":
        mime = "text/gemini; charset=utf-8"
    msg = EmailMessage()
    msg["content-type"] = mime
    mime, mime_options = msg.get_content_type(), msg["Content-Type"].params
    default_charset = "utf-8"
    charset = None
    if "charset" in mime_options:
        try:
            codecs.lookup(mime_options["charset"])
            charset = mime_options["charset"]
        except LookupError:
            print("Header declared unknown encoding %s" % mime_options["charset"])
            return
    lang = mime_options["lang"] if "lang" in mime_options else None
    # Read the response body over the network
    try:
        body = f.read()
    except Exception:
        print("Error reading response over network!")
        return
    if mime.startswith("text/"):
        try:
            content = codecs.decode(body, charset or default_charset)
        except:
            # print("ERROR: problem decoding content with %s charset" % charset)
            return
    else:
        content = body
    return Response(
        content=content,
        content_type=mime,
        charset=charset,
        lang=lang,
        num_bytes=len(body),
        url=url.geturl(),
        status=status,
    )


def _send_request(url):
    """Send a selector to a given host and port.
    Returns the resolved address and binary file with the reply."""
    port = url.port if url.port is not None else 1965
    addresses = _get_addresses(url.hostname, port)
    # Connect to remote host by any address possible
    err = None
    for address in addresses:
        _debug("Connecting to: " + str(address[4]))
        s = socket.socket(address[0], address[1])
        s.settimeout(15.0)
        context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        # Impose minimum TLS version
        if sys.version_info.minor == 7:
            context.minimum_version = ssl.TLSVersion.TLSv1_2
        else:
            context.options | ssl.OP_NO_TLSv1_1
            context.options | ssl.OP_NO_SSLv3
            context.options | ssl.OP_NO_SSLv2
        context.set_ciphers(
            "AES256-GCM-SHA384:AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!3DES:!MD5:!PSK"
        )
        # print(context.get_ciphers())
        s = context.wrap_socket(s, server_hostname=url.hostname)
        try:
            s.connect(address[4])
            break
        except OSError as e:
            err = e
    else:
        # If we couldn't connect to *any* of the addresses, just
        # bubble up the exception from the last attempt and deny
        # knowledge of earlier failures.
        raise err

    _debug("Established {} connection.".format(s.version()))
    _debug("Cipher is: {}.".format(s.cipher()))

    # Send request and wrap response in a file descriptor
    _debug("Sending %s<CRLF>" % url.geturl())
    s.sendall((url.geturl() + "\r\n").encode("UTF-8"))
    return address, s.makefile(mode="rb")


def _get_addresses(host, port):
    # DNS lookup - will get IPv4 and IPv6 records if IPv6 is enabled
    if ":" in host:
        # This is likely a literal IPv6 address, so we can *only* ask for
        # IPv6 addresses or getaddrinfo will complain
        family_mask = socket.AF_INET6
    elif socket.has_ipv6:
        # Accept either IPv4 or IPv6 addresses
        family_mask = 0
    else:
        # IPv4 only
        family_mask = socket.AF_INET
    addresses = socket.getaddrinfo(
        host, port, family=family_mask, type=socket.SOCK_STREAM
    )
    # Sort addresses so IPv6 ones come first
    addresses.sort(key=lambda add: add[0] == socket.AF_INET6, reverse=True)
    return addresses


def _parse_url(url):
    """Work around issues with Python's urrlib.parse"""
    pass


def _debug(message):
    pass
