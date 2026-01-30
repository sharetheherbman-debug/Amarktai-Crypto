"""
Web3 Service for DeFi/DEX Trading
Handles blockchain interactions, DEX swaps, and liquidity pools
"""

import logging
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from datetime import datetime, timezone

try:
    from web3 import Web3
    from web3.exceptions import Web3Exception
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("web3 not installed - DeFi features will be limited")

import config

logger = logging.getLogger(__name__)


# Uniswap V2 Router ABI (minimal for swaps)
UNISWAP_V2_ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# ERC20 ABI (minimal for approvals and balance)
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]


class Web3Service:
    """Service for interacting with Web3 and DEXs"""
    
    def __init__(self):
        self.providers = {}
        self.contracts = {}
        
        if not WEB3_AVAILABLE:
            logger.warning("Web3 not available - DeFi features disabled")
            return
        
        # Initialize Web3 providers for different chains
        try:
            self.providers['ethereum'] = Web3(Web3.HTTPProvider(config.ETH_RPC_URL))
            self.providers['bsc'] = Web3(Web3.HTTPProvider(config.BSC_RPC_URL))
            self.providers['polygon'] = Web3(Web3.HTTPProvider(config.POLYGON_RPC_URL))
            
            logger.info("Web3 providers initialized for Ethereum, BSC, and Polygon")
        except Exception as e:
            logger.error(f"Failed to initialize Web3 providers: {e}")
    
    def is_connected(self, chain: str = 'ethereum') -> bool:
        """Check if connected to blockchain"""
        if not WEB3_AVAILABLE or chain not in self.providers:
            return False
        
        try:
            return self.providers[chain].is_connected()
        except Exception as e:
            logger.error(f"Connection check failed for {chain}: {e}")
            return False
    
    def verify_wallet_signature(self, wallet_address: str, message: str, signature: str, chain: str = 'ethereum') -> bool:
        """
        Verify that a wallet owns a signature
        Used for WalletConnect authentication
        """
        if not WEB3_AVAILABLE or chain not in self.providers:
            logger.warning("Web3 not available for signature verification")
            return False
        
        try:
            w3 = self.providers[chain]
            
            # Recover address from signature
            message_hash = Web3.keccak(text=message)
            recovered_address = w3.eth.account.recover_message(message_hash, signature=signature)
            
            # Compare addresses (case-insensitive)
            return recovered_address.lower() == wallet_address.lower()
            
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False
    
    def get_token_balance(self, token_address: str, wallet_address: str, chain: str = 'ethereum') -> Optional[Decimal]:
        """Get ERC20 token balance"""
        if not WEB3_AVAILABLE or chain not in self.providers:
            return None
        
        try:
            w3 = self.providers[chain]
            token_contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )
            
            balance = token_contract.functions.balanceOf(
                Web3.to_checksum_address(wallet_address)
            ).call()
            
            # Get decimals
            decimals = token_contract.functions.decimals().call()
            
            return Decimal(balance) / Decimal(10 ** decimals)
            
        except Exception as e:
            logger.error(f"Failed to get token balance: {e}")
            return None
    
    def get_swap_quote(
        self, 
        token_in: str, 
        token_out: str, 
        amount_in: float,
        dex: str = 'uniswap',
        chain: str = 'ethereum'
    ) -> Optional[Dict]:
        """
        Get swap quote from DEX
        Returns expected output amount and route
        """
        if not WEB3_AVAILABLE or chain not in self.providers:
            return None
        
        try:
            w3 = self.providers[chain]
            
            # Get router address based on DEX
            router_address = self._get_router_address(dex, chain)
            if not router_address:
                logger.error(f"Unsupported DEX/chain combination: {dex}/{chain}")
                return None
            
            # Create router contract
            router = w3.eth.contract(
                address=Web3.to_checksum_address(router_address),
                abi=UNISWAP_V2_ROUTER_ABI
            )
            
            # Get token decimals
            token_in_contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_in),
                abi=ERC20_ABI
            )
            decimals_in = token_in_contract.functions.decimals().call()
            
            token_out_contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_out),
                abi=ERC20_ABI
            )
            decimals_out = token_out_contract.functions.decimals().call()
            
            # Convert amount to wei
            amount_in_wei = int(amount_in * (10 ** decimals_in))
            
            # Get quote
            path = [
                Web3.to_checksum_address(token_in),
                Web3.to_checksum_address(token_out)
            ]
            
            amounts = router.functions.getAmountsOut(amount_in_wei, path).call()
            
            # Convert output to human-readable
            amount_out = amounts[-1] / (10 ** decimals_out)
            
            return {
                'amount_in': amount_in,
                'amount_out': amount_out,
                'price_impact': self._calculate_price_impact(amount_in, amount_out),
                'path': path,
                'dex': dex,
                'chain': chain,
                'quote_time': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get swap quote: {e}")
            return None
    
    def check_token_approval(
        self,
        token_address: str,
        owner_address: str,
        spender_address: str,
        amount: float,
        chain: str = 'ethereum'
    ) -> bool:
        """Check if token is approved for spending"""
        if not WEB3_AVAILABLE or chain not in self.providers:
            return False
        
        try:
            w3 = self.providers[chain]
            token_contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )
            
            # Get decimals
            decimals = token_contract.functions.decimals().call()
            amount_wei = int(amount * (10 ** decimals))
            
            # Check allowance
            allowance = token_contract.functions.allowance(
                Web3.to_checksum_address(owner_address),
                Web3.to_checksum_address(spender_address)
            ).call()
            
            return allowance >= amount_wei
            
        except Exception as e:
            logger.error(f"Failed to check token approval: {e}")
            return False
    
    def estimate_gas_for_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: float,
        wallet_address: str,
        dex: str = 'uniswap',
        chain: str = 'ethereum'
    ) -> Optional[int]:
        """Estimate gas for swap transaction"""
        if not WEB3_AVAILABLE or chain not in self.providers:
            return None
        
        try:
            w3 = self.providers[chain]
            
            # For now, return conservative estimate
            # In production, would simulate transaction
            return config.GAS_LIMIT_SWAP
            
        except Exception as e:
            logger.error(f"Failed to estimate gas: {e}")
            return None
    
    def get_current_gas_price(self, chain: str = 'ethereum') -> Optional[int]:
        """Get current gas price in wei"""
        if not WEB3_AVAILABLE or chain not in self.providers:
            return None
        
        try:
            w3 = self.providers[chain]
            return w3.eth.gas_price
            
        except Exception as e:
            logger.error(f"Failed to get gas price: {e}")
            return None
    
    def _get_router_address(self, dex: str, chain: str) -> Optional[str]:
        """Get DEX router address for chain"""
        router_map = {
            'uniswap': {
                'ethereum': config.UNISWAP_V2_ROUTER
            },
            'pancakeswap': {
                'bsc': config.PANCAKESWAP_ROUTER
            },
            'quickswap': {
                'polygon': config.QUICKSWAP_ROUTER
            }
        }
        
        return router_map.get(dex, {}).get(chain)
    
    def _calculate_price_impact(self, amount_in: float, amount_out: float) -> float:
        """Calculate price impact percentage"""
        if amount_in == 0:
            return 0.0
        
        # Simple price impact calculation
        # In production, would compare to spot price
        return abs((amount_out / amount_in - 1.0) * 100)


# Global instance
web3_service = Web3Service()
