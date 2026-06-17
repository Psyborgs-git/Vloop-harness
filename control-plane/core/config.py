import os

# Support for Python < 3.11 TOML parsing
try:
    import tomllib
except ImportError:
    import tomli as tomllib

class ConfigManager:
    def __init__(self, config_path: str = None):
        if not config_path:
            # Default to the path created by the Rust microkernel
            home = os.path.expanduser("~")
            self.config_path = os.path.join(home, ".vloop", "rust", "active.toml")
        else:
            self.config_path = config_path
            
        self.config_data = {}

    def load_config(self) -> dict:
        try:
            with open(self.config_path, "rb") as f:
                self.config_data = tomllib.load(f)
                print(f"Loaded config from {self.config_path}")
        except FileNotFoundError:
            print(f"Warning: Config file not found at {self.config_path}. Using defaults.")
            self.config_data = {
                "max_memory_bytes": 1024 * 1024 * 512, # 512MB fallback
                "data_dir": os.path.expanduser("~/.vloop")
            }
        
        return self.config_data

    @property
    def max_memory_bytes(self) -> int:
        return self.config_data.get("max_memory_bytes", 1024 * 1024 * 512)
        
    @property
    def data_dir(self) -> str:
        return self.config_data.get("data_dir", os.path.expanduser("~/.vloop"))
