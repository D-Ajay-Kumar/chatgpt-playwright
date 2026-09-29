from chatgpt_playwright import ChatSession, ask_chatgpt

if __name__ == "__main__":
    print(ask_chatgpt("hello"))

    with ChatSession() as s:
        print(s.ask("Remember this number: 42"))
        print(s.ask("What number did I ask you to remember?"))
        url = s.url

    # Later (even in another process), continue the same conversation
    with ChatSession(conversation_url=url) as s:
        print(s.ask("Add 8 to that number."))
