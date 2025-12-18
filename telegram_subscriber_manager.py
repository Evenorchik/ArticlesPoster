"""
Утилита для управления подписчиками Telegram бота.
Позволяет добавлять/удалять подписчиков и синхронизировать из обновлений бота.
"""
import logging
import sys
from telegram_bot import (
    add_subscriber,
    remove_subscriber,
    get_subscribers,
    sync_subscribers_from_updates,
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
    print("Commands:")
    print("  1. Add subscriber (chat_id)")
    print("  2. Remove subscriber (chat_id)")
    print("  3. List all subscribers")
    print("  4. Sync subscribers from bot updates")
    print("  5. Send test message to all subscribers")
    print("  6. Exit")
    print()
    
    while True:
        choice = input("Enter command (1-6): ").strip()
        
        if choice == '1':
            chat_id = input("Enter chat_id to add: ").strip()
            if chat_id:
                if add_subscriber(chat_id):
                    print(f"✓ Subscriber {chat_id} added successfully")
                else:
                    print(f"⚠ Subscriber {chat_id} already exists")
            else:
                print("❌ Invalid chat_id")
        
        elif choice == '2':
            chat_id = input("Enter chat_id to remove: ").strip()
            if chat_id:
                if remove_subscriber(chat_id):
                    print(f"✓ Subscriber {chat_id} removed successfully")
                else:
                    print(f"⚠ Subscriber {chat_id} not found")
            else:
                print("❌ Invalid chat_id")
        
        elif choice == '3':
            subscribers = get_subscribers()
            print(f"\nCurrent subscribers ({len(subscribers)}):")
            if subscribers:
                for chat_id in sorted(subscribers):
                    print(f"  - {chat_id}")
            else:
                print("  (no subscribers)")
            print()
        
        elif choice == '4':
            print("Syncing subscribers from bot updates...")
            count = sync_subscribers_from_updates()
            print(f"✓ Synced {count} new subscriber(s)")
            subscribers = get_subscribers()
            print(f"Total subscribers: {len(subscribers)}")
        
        elif choice == '5':
            test_message = "🧪 Test message from Articles Poster bot"
            print(f"Sending test message to all subscribers...")
            success = send_message(test_message)
            if success:
                print("✓ Test message sent successfully")
            else:
                print("❌ Failed to send test message")
        
        elif choice == '6':
            print("Exiting...")
            break
        
        else:
            print("❌ Invalid command. Please enter 1-6.")
        
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)

