#!/usr/bin/env python
# run.py
import os
import argparse
from app import create_app

def parse_args():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(description='Запуск Faktura App')
    parser.add_argument('--config', type=str, default='production',
                      help='Конфигурация приложения (development, production)')
    parser.add_argument('--host', type=str, default='0.0.0.0',
                      help='Хост для запуска приложения')
    parser.add_argument('--port', type=int, default=5000,
                      help='Порт для запуска приложения')
    parser.add_argument('--debug', action='store_true',
                      help='Запуск в режиме отладки')
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Устанавливаем переменную окружения для Flask
    os.environ['FLASK_CONFIG'] = args.config
    
    # Создаем экземпляр приложения
    app = create_app(args.config)
    
    # Запускаем приложение
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug
    )

if __name__ == '__main__':
    main()
