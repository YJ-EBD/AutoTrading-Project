import json
import time
import logging
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from trading_bot import TradingBot

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)

class ConfigFileHandler(FileSystemEventHandler):
    def __init__(self, trading_bot):
        self.trading_bot = trading_bot
        
    def on_modified(self, event):
        if event.src_path.endswith('config.json'):
            logging.info("Config file modified, reloading configuration...")
            self.trading_bot.reload_config()

def main():
    # Load initial configuration
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    # Initialize trading bot
    bot = TradingBot(config)
    
    # Set up config file watching
    event_handler = ConfigFileHandler(bot)
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=False)
    observer.start()
    
    try:
        while True:
            bot.evaluate_positions()
            time.sleep(config['evaluation_interval'])
            
    except KeyboardInterrupt:
        observer.stop()
        bot.cleanup()
        
    observer.join()

if __name__ == "__main__":
    main()