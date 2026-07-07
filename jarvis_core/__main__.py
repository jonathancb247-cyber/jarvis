from jarvis_core.runtime import build_runtime


def main():
    bus = build_runtime()
    text = "what time is it?"
    response = bus.publish("user.input", {"text": text})[0]
    print("Jarvis AVP-001")
    print("jarvis> " + text)
    print("Jarvis: " + response)


if __name__ == "__main__":
    main()
