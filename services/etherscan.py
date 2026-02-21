"""
services/etherscan.py — Etherscan API 客户端

封装对 Etherscan API 的调用，用于获取合约源码、ABI 和创建者信息。
需配置 ETHERSCAN_API_KEY。
"""

from __future__ import annotations

import httpx
from loguru import logger
from core.config import get_settings

class EtherscanService:
    def __init__(self, chain_name: str = "ethereum") -> None:
        self.settings = get_settings()
        self.chain_name = chain_name
        
        # 根据链的不同切换域名，并始终使用 v1 endpoint，因为免费版 API 不再完全支持 v2
        if chain_name == "bsc":
            self.chain_id = 56
            self.base_url = "https://api.bscscan.com/api"
            self.api_key = self.settings.bscscan_api_key
        else:
            self.chain_id = 1
            self.base_url = "https://api.etherscan.io/api"
            self.api_key = self.settings.etherscan_api_key
    
    async def get_contract_source(self, address: str) -> str | None:
        """获取合约源码。"""
        if not self.api_key:
            logger.warning(f"API key for {self.chain_name} is missing. Skipping source code fetch.")
            return None
            
        params = {
            "module": "contract",
            "action": "getsourcecode",
            "address": address,
            "apikey": self.api_key,
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.base_url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") == "1" and data.get("result"):
                    # result is a list of dicts, usually one element
                    source_code = data["result"][0].get("SourceCode", "")
                    return source_code if source_code else None
                else:
                    logger.warning(f"Etherscan API error or no source found for {address}: {data.get('message')}")
                    return None
        except Exception as e:
            logger.error(f"Failed to fetch contract source for {address}: {e}")
            return None

    async def get_abi(self, address: str) -> str | None:
        """获取合约 ABI。"""
        if not self.api_key:
            return None
            
        params = {
            "module": "contract",
            "action": "getabi",
            "address": address,
            "apikey": self.api_key,
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.base_url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") == "1" and data.get("result"):
                    return data["result"]
                else:
                    return None
        except Exception as e:
            logger.error(f"Failed to fetch ABI for {address}: {e}")
            return None
    
    async def is_verified(self, address: str) -> bool:
        """检查合约是否已验证。"""
        source = await self.get_contract_source(address)
        return bool(source)
