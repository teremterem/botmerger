# 🔀 BotMerger

BotMerger is a fully asynchronous Python framework designed as a messaging platform which allows Large Language Model
(LLM)-based chatbots to interact with each other in order to "merge" into more complex bots capable of fulfilling
non-trivial user requests.

## 📦 Installation

```shell
pip install --upgrade botmerger
```

## 🚀 Quickstart

TODO

## 💡 Philosophy

### 🧩 Implement each skill as a separate bot

Let's consider our own version "GitHub Copilot" as an example. Here is how it could be roughly broken down into smaller
bots:
- A bot that lists files in a GitHub repository
- A bot that reads source code from a file in the repository and displays it in the "chat" (an internal chat between
  bots)
- A bot that improves the code according to a given criteria
- A bot that accepts code improvement requests from a user (via Discord, Telegram or maybe as CLI input), breaks
  them down, delegates them to the appropriate bots from the list above and then reports back to the user
- A bot that occasionally asks the user for additional input in the middle of request processing should any of the
  other bots require such input in order to fulfill their part of the request
- and so on...

### 🎭 Each "mini-bot" should be able to interact with the user directly

If any of the bots require strictly formatted input in order to perform their part of the request (for example, the
bot that reads the source code from a file in a repository will require a specific file name as input), it should be
possible to provide such input in both strictly formatted and natural language forms (for example,
`{"filename": "src/main.py"}` vs `src/main.py` vs `the main module`; it would rely on the output of the "list repo files"
bot to translate free text into the actual file path).

It is preferable that each of the bots that together comprise a more complicated bot is implemented this way. The
framework facilitates that by allowing developers to easily make any of these "mini-bots" face the user directly for
debugging purposes.

## 🍭 Example projects

TODO
