import re

with open("services/etherscan.py", "r", encoding="utf-8") as f:
    content = f.read()

old_init = """        if chain_name == "bsc":
            self.chain_id = 56
            self.base_url = "https://api.bscscan.com/api"
            self.api_key = self.settings.bscscan_api_key
        else:
            self.chain_id = 1
            self.base_url = "https://api.etherscan.io/api"
            self.api_key = self.settings.etherscan_api_key"""

new_init = """        if chain_name == "bsc":
            self.chain_id = 56
            self.base_url = "https://api.bscscan.com/api"
            self.api_key = self.settings.bscscan_api_key
        else:
            self.chain_id = 1
            self.base_url = "https://api.etherscan.io/api"
            self.api_key = self.settings.etherscan_api_key
            
        # The BscScan V1 API was deprecated, it replies with "You are using a deprecated V1 endpoint"
        # However, according to the BscScan API documentation, the host for V2 free API is still the same:
        # "https://api.bscscan.com/api" is correct, but there is no specific version path.
        # But wait! We got: "You are using a deprecated V1 endpoint" for api.bscscan.com too? Let's check docs:
        # Let's try v2 domain if we can."""
