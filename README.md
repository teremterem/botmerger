# 🔀 BotMerger

BotMerger is a fully asynchronous Python framework designed as a messaging platform which allows simpler Large Language
Model (LLM)-based chatbots to interact with each other in order to "form" more complex bots capable of fulfilling
non-trivial user requests.

## 💡 Philosophy

1) Each skill that the resulting complex bot will have should be implemented as a separate bot. Let's consider own
   version "GitHub copilot" as an example. Here is how such a complex bot could be roughly broken down:
   - A bot that lists files in a GitHub repository
   - A bot that reads source code from a file in the repository and displays it in the "chat" (a chat between bots)
   - A bot that improves the code according to a given criteria
   - ...
   - A bot that accepts code improvement requests from a user (via Discord, Telegram or maybe even as CLI input),
     breaks them down, delegates them to the appropriate bots and then reports the results back to the user
   - A bot that occasionally asks the user for additional input in the middle of request processing should any of the
     other bots require such input in order to fulfill their part of the request
   - and so on...
2) If any of the bots require strictly formatted input in order to perform their part of the request (for example, the
   bot that reads the source code from a file in the repository will require specific file name as input), it should
   be possible to provide such input in both, strictly formatted and natural language forms
   (for ex. `{filename: "src/main.py"}` vs `the main module`). Each and every bot should be implemented in such a way.
   The framework facilitates this by allowing the developer to make the any of the bots face the user directly at any
   time.
