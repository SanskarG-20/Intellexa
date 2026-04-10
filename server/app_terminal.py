import asyncio

import httpx


SERVER_URL = "http://127.0.0.1:8000"
CHAT_PATH = "/api/v1/chat"


async def _post_to_embedded_app(message: str) -> httpx.Response:
    """
    Fall back to the local FastAPI app so the terminal client still works
    when the HTTP server is not already running in another terminal.
    """
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://embedded-app",
        timeout=90.0,
    ) as client:
        return await client.post(CHAT_PATH, json={"message": message})


def send_message(message: str) -> tuple[httpx.Response, str]:
    """
    Prefer the live server, but gracefully fall back to the embedded app.
    """
    try:
        response = httpx.post(
            f"{SERVER_URL}{CHAT_PATH}",
            json={"message": message},
            timeout=httpx.Timeout(90.0, connect=2.0),
        )
        return response, "server"
    except httpx.RequestError:
        response = asyncio.run(_post_to_embedded_app(message))
        return response, "embedded"


def main():
    print("=" * 50)
    print("      Intellexa Core - Terminal Chat")
    print("=" * 50)
    print("Type your message and press Enter. Type 'exit' to quit.")
    print("If the API server is not running, the terminal will use the app directly.\n")

    embedded_mode_announced = False

    while True:
        user_input = input("You: ")

        if user_input.lower() in ["exit", "quit", "bye"]:
            print("\nGoodbye!")
            break

        if not user_input.strip():
            continue

        try:
            response, mode = send_message(user_input)

            if mode == "embedded" and not embedded_mode_announced:
                print("\nUsing the embedded FastAPI app because no server was detected on port 8000.\n")
                embedded_mode_announced = True

            if response.status_code == 200:
                ai_response = response.json().get("response")
                print(f"\nIntellexa: {ai_response}\n")
            else:
                try:
                    error_detail = response.json().get("detail", response.text)
                except ValueError:
                    error_detail = response.text

                print(f"\nError {response.status_code}: {error_detail}\n")

        except Exception as exc:
            print(f"\nRequest failed: {exc}")
            print("Start the API with 'python -m app.main' if you want to use the standalone server.\n")


if __name__ == "__main__":
    main()
