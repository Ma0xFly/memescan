"""
services/token_info.py — 链上代币元数据采集服务

调用 ERC-20 标准接口 (name, symbol, decimals, totalSupply) 填充代币信息。
"""

from __future__ import annotations

import asyncio
from typing import Optional

from loguru import logger
from web3.exceptions import ContractLogicError

from core.web3_provider import get_async_web3
from domain.models import Token

ERC20_ABI_MINIMAL = [
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "owner",
        "outputs": [{"name": "", "type": "address"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
]

class TokenInfoService:
    def __init__(self) -> None:
        self.w3 = get_async_web3()

    async def fetch_metadata(self, address: str, pair_address: str) -> Token:
        """从链上获取代币元数据并返回 Token 对象。"""
        address = self.w3.to_checksum_address(address)
        contract = self.w3.eth.contract(address=address, abi=ERC20_ABI_MINIMAL)

        name = "UNKNOWN"
        symbol = "???"
        decimals = 18
        total_supply_str = None
        deployer = ""
        
        # 辅助函数：安全调用
        async def safe_call(func):
            try:
                return await func().call()
            except Exception:
                return None
        
        # 并发获取
        results = await asyncio.gather(
            safe_call(contract.functions.name),
            safe_call(contract.functions.symbol),
            safe_call(contract.functions.decimals),
            safe_call(contract.functions.totalSupply),
            safe_call(contract.functions.owner),
            return_exceptions=True
        )

        res_name, res_symbol, res_decimals, res_supply, res_owner = results

        if isinstance(res_name, str):
            name = res_name
        elif isinstance(res_name, bytes):
            try:
                name = res_name.decode("utf-8").strip("\x00")
            except:
                pass

        if isinstance(res_symbol, str):
            symbol = res_symbol
        elif isinstance(res_symbol, bytes):
            try:
                symbol = res_symbol.decode("utf-8").strip("\x00")
            except:
                pass

        if isinstance(res_decimals, int):
            decimals = res_decimals

        if isinstance(res_supply, int):
            total_supply_str = str(res_supply)
        
        if isinstance(res_owner, str):
            deployer = res_owner

        return Token(
            address=address,
            pair_address=pair_address,
            name=name,
            symbol=symbol,
            decimals=decimals,
            total_supply=total_supply_str,
            deployer=deployer,
        )

    async def get_holder_count(self, address: str) -> int | None:
        """估算持币人数（通过 Transfer 事件）。
        注意：全量扫描 Transfer 事件非常慢，仅建议在必要时做近似估算。
        """
        return None
