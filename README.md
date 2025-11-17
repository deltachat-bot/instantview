# InstantView Bot

[![Latest Release](https://img.shields.io/pypi/v/instantview.svg)](https://pypi.org/project/instantview)
[![CI](https://github.com/deltachat-bot/instantview/actions/workflows/python-ci.yml/badge.svg)](https://github.com/deltachat-bot/instantview/actions/workflows/python-ci.yml)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A Delta Chat bot that allows to get website URLs previews as HTML messages

## Install

```sh
pip install instantview
```

## Usage

To configure the bot:

```sh
instantview-bot init DCACCOUNT:https://nine.testrun.org/new
```

**(Optional)** To customize the bot name, avatar and status/signature:

```sh
instantview-bot config selfavatar "/path/to/avatar.png"
instantview-bot config displayname "Web Preview"
instantview-bot config selfstatus "Hi, send me some URL to get a preview"
```

To get in contact with the bot, get the bot's invite link:

```sh
instantview-bot link
```

Finally you can start the bot with:

```sh
instantview-bot serve
```

To see the available options, run in the command line:

```
instantview-bot --help
```
