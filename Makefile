CONTAINER := telegram-gemini-bot-bot-1

logs:
	docker logs -f $(CONTAINER) 2>&1 | grep -v -E "httpx|telegram\.ext\.Application"

logs-full:
	docker logs -f $(CONTAINER)
