import ctypes
import logging
import os
import sys


def _console_stream():
    """Where log lines go when the windowed exe left us without a stdout.

    The GUI's log panel reads the same logger through a QueueHandler, so nothing is lost
    by sinking these; `--console` opens a real console for a run that has to be watched
    from outside the window.
    """
    if "--console" in sys.argv:
        try:
            ctypes.windll.kernel32.AllocConsole()
            return open("CONOUT$", "w", buffering=1, encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    return open(os.devnull, "w", encoding="utf-8")


class ConvaiLogger:
    """Centralized logging for Convai Modding Tool with consistent formatting."""
    
    def __init__(self, name: str = "ConvaiTool", level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Remove existing handlers
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # Every message here carries an emoji prefix, and a Windows console is cp1252:
        # unencodable characters make logging raise on each line instead of printing it.
        # The exe redirects stdout to a pipe, where the same applies.
        # The windowed build has no stdout at all, and StreamHandler(None) logs to a
        # sys.stderr that is None there too, so every log call would raise.
        stream = sys.stdout or _console_stream()
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # A stream that cannot be reconfigured (already wrapped, or detached) still
            # has to be logged to; the replacement below keeps it printable.
            pass

        console_handler = logging.StreamHandler(stream)
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