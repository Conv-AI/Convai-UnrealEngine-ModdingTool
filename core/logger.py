import logging
import sys
from typing import Optional

class ConvaiLogger:
    """Centralized logging for Convai Modding Tool with consistent formatting."""
    
    def __init__(self, name: str = "ConvaiTool", level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Remove existing handlers
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # Create console handler with custom formatting
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        
        # Custom formatter without timestamps for user-friendly output
        formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(console_handler)
        self.logger.propagate = False
    
    def step(self, message: str):
        """Log a major step in the process."""
        self.logger.info(f"🔧 {message}")
    
    def success(self, message: str):
        """Log a successful operation."""
        self.logger.info(f"✅ {message}")
    
    def info(self, message: str):
        """Log general information."""
        self.logger.info(f"ℹ️  {message}")
    
    def warning(self, message: str):
        """Log a warning."""
        self.logger.warning(f"⚠️  {message}")
    
    def error(self, message: str):
        """Log an error."""
        self.logger.error(f"❌ {message}")
    
    def debug(self, message: str):
        """Log debug information (only shown in verbose mode)."""
        self.logger.debug(f"🔍 {message}")
    
    def progress(self, current: int, total: int, operation: str):
        """Log progress for multi-step operations."""
        percentage = (current / total) * 100
        self.logger.info(f"📦 {operation} ({current}/{total} - {percentage:.0f}%)")
    
    def section(self, title: str):
        """Log a major section separator."""
        self.logger.info(f"\n{'=' * 50}")
        self.logger.info(f"🎯 {title}")
        self.logger.info(f"{'=' * 50}")
    
    def subsection(self, title: str):
        """Log a subsection separator."""
        self.logger.info(f"\n📋 {title}")
        self.logger.info(f"{'-' * 30}")

# Global logger instance
logger = ConvaiLogger()

def set_verbose_mode(verbose: bool = True):
    """Enable or disable verbose logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logger.logger.setLevel(level)
    for handler in logger.logger.handlers:
        handler.setLevel(level)

def suppress_external_logging():
    """Suppress verbose logging from external libraries."""
    # Suppress file utility manager logging
    logging.getLogger('core.file_utility_manager').setLevel(logging.WARNING)
    
    # Suppress other verbose loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING) 