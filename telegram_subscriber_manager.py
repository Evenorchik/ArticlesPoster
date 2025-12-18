"""
Утилита для управления подписчиками Telegram бота.
Синхронизирует список пользователей, которые нажали /start в боте.
"""
import logging
import sys
from telegram_bot import (
    sync_subscribers_from_start_commands,
    load_subscribers,
    send_message
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def main():
    """Интерактивное управление подписчиками."""
    print("="*60)
    print("Telegram Bot Subscriber Manager")
    print("="*60)
    print()
    print("This tool syncs subscribers who sent /start command to the bot.")
    print()
    print("Commands:")
    print("  1. Sync subscribers from /start commands")
    print("  2. List all subscribers")
    print("  3. Send test message to all subscribers")
    print("  4. Exit")
    print()
    
    while True:
        choice = input("Enter command (1-4): ").strip()
        
        if choice == '1':
            print("Syncing subscribers from /start commands...")
            count = sync_subscribers_from_start_commands()
            subscribers = load_subscribers()
            print(f"✓ Found {len(subscribers)} total subscriber(s)")
            if count > 0:
                print(f"✓ Added {count} new subscriber(s)")
            print()
        
        elif choice == '2':
            subscribers = load_subscribers()
            print(f"\nCurrent subscribers ({len(subscribers)}):")
            if subscribers:
                for chat_id in sorted(subscribers):
                    print(f"  - {chat_id}")
            else:
                print("  (no subscribers)")
            print()
        
        elif choice == '3':
            test_message = "🧪 Test message from Articles Poster bot"
            print(f"Sending test message to all subscribers...")
            success = send_message(test_message)
            if success:
                print("✓ Test message sent successfully")
            else:
                print("❌ Failed to send test message")
            print()
        
        elif choice == '4':
            print("Exiting...")
            break
        
        else:
            print("❌ Invalid command. Please enter 1-4.")
            print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
