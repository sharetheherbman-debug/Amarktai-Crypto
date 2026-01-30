"""
Bot DNA Evolution System
- Genetic algorithm for bot optimization
- Mutation and crossover of successful bots
- Natural selection based on performance
- Configurable mutation rate (default 25%)
- Pair and exchange diversity requirements
"""

import asyncio
import random
from datetime import datetime, timezone
from logger_config import logger
import database as db
from performance_ranker import performance_ranker
import config


class BotDNAEvolution:
    def __init__(self):
        # Use configurable mutation rate from config (default 25%)
        self.mutation_rate = config.EVOLUTION_MUTATION_RATE
        self.elite_percent = 0.30  # Top 30% survive
        self.generation = 0
    
    async def evolve_bots(self, user_id: str):
        """Run evolution cycle on user's bots"""
        try:
            logger.info(f"Starting bot evolution for user {user_id}")
            
            # Get ranked bots
            ranked_bots = await performance_ranker.rank_bots(user_id)
            
            if len(ranked_bots) < 10:
                logger.info("Insufficient bots for evolution (need 10+)")
                return {"evolved": 0, "message": "Need 10+ bots for evolution"}
            
            # Identify elite bots (top 30%)
            elite_count = max(int(len(ranked_bots) * self.elite_percent), 3)
            elite_bots = ranked_bots[:elite_count]
            
            # Identify weak bots (bottom 30%)
            weak_count = max(int(len(ranked_bots) * 0.30), 3)
            weak_bots = ranked_bots[-weak_count:]
            
            # Evolve weak bots based on elite DNA
            evolved_count = 0
            
            # Track diversity: ensure we have different pairs and exchanges
            evolved_pairs = set()
            evolved_exchanges = set()
            
            for weak_bot in weak_bots:
                # Select two elite parents (prefer different exchanges for diversity)
                parent1 = random.choice(elite_bots)
                parent2 = self._select_diverse_parent(elite_bots, parent1)
                
                # Create child DNA
                new_dna = self._crossover(parent1, parent2)
                
                # Apply mutation
                new_dna = self._mutate(new_dna)
                
                # Ensure diversity: avoid too many bots on same pair/exchange
                new_dna = self._ensure_diversity(new_dna, evolved_pairs, evolved_exchanges, ranked_bots)
                
                # Track what we've created
                evolved_pairs.add(new_dna.get('trading_pair', 'BTC/ZAR'))
                evolved_exchanges.add(new_dna.get('exchange', 'luno'))
                
                # Update weak bot with new DNA
                await self._update_bot_dna(weak_bot['id'], new_dna)
                evolved_count += 1
            
            self.generation += 1
            logger.info(f"Evolution complete: {evolved_count} bots evolved (Generation {self.generation})")
            logger.info(f"Diversity: {len(evolved_pairs)} pairs, {len(evolved_exchanges)} exchanges")
            
            return {
                "evolved": evolved_count,
                "generation": self.generation,
                "elite_count": elite_count,
                "message": f"Evolution cycle {self.generation} complete"
            }
            
        except Exception as e:
            logger.error(f"Bot evolution failed: {e}")
            return {"evolved": 0, "error": str(e)}
    
    def _select_diverse_parent(self, elite_bots: list, parent1: dict) -> dict:
        """Select a second parent, preferring different exchange for diversity"""
        # Try to find a parent from a different exchange
        different_exchange = [b for b in elite_bots if b.get('exchange') != parent1.get('exchange')]
        
        if different_exchange and random.random() < 0.7:  # 70% chance to prefer diversity
            return random.choice(different_exchange)
        else:
            return random.choice(elite_bots)
    
    def _ensure_diversity(self, dna: dict, evolved_pairs: set, evolved_exchanges: set, all_bots: list) -> dict:
        """Ensure genetic diversity by avoiding over-concentration on single pair/exchange"""
        # Count existing bots per exchange
        exchange_counts = {}
        for bot in all_bots:
            ex = bot.get('exchange', 'luno')
            exchange_counts[ex] = exchange_counts.get(ex, 0) + 1
        
        # If proposed exchange is over-represented, try to diversify
        proposed_exchange = dna.get('exchange', 'luno')
        if exchange_counts.get(proposed_exchange, 0) > len(all_bots) * 0.4:  # >40% concentration
            # Try to pick a less-represented exchange
            available_exchanges = ['luno', 'binance', 'kucoin', 'valr', 'ovex']
            under_represented = [ex for ex in available_exchanges 
                               if exchange_counts.get(ex, 0) < len(all_bots) * 0.3]
            if under_represented:
                dna['exchange'] = random.choice(under_represented)
                logger.info(f"Diversity: Switched exchange to {dna['exchange']}")
        
        return dna
    
    def _crossover(self, parent1: dict, parent2: dict) -> dict:
        """Combine DNA from two parents"""
        dna = {}
        
        # Risk mode (50/50 chance from each parent)
        dna['risk_mode'] = random.choice([parent1.get('risk_mode'), parent2.get('risk_mode')])
        
        # Trading pair (favor parent1 if better performing)
        dna['trading_pair'] = parent1.get('trading_pair', 'BTC/ZAR')
        
        # Capital (average of parents)
        dna['initial_capital'] = (
            parent1.get('initial_capital', 1000) + parent2.get('initial_capital', 1000)
        ) / 2
        
        # Exchange (from better parent)
        dna['exchange'] = parent1.get('exchange', 'luno')
        
        return dna
    
    def _mutate(self, dna: dict) -> dict:
        """Apply random mutations to DNA"""
        if random.random() < self.mutation_rate:
            # Mutate risk mode
            risk_modes = ['safe', 'balanced', 'risky']
            dna['risk_mode'] = random.choice(risk_modes)
            logger.info(f"Mutation: risk_mode -> {dna['risk_mode']}")
        
        if random.random() < self.mutation_rate:
            # Mutate trading pair
            pairs = ['BTC/ZAR', 'ETH/ZAR', 'XRP/ZAR']
            dna['trading_pair'] = random.choice(pairs)
            logger.info(f"Mutation: trading_pair -> {dna['trading_pair']}")
        
        if random.random() < self.mutation_rate:
            # Mutate capital (±20%)
            factor = random.uniform(0.8, 1.2)
            dna['initial_capital'] = dna['initial_capital'] * factor
            logger.info(f"Mutation: capital -> R{dna['initial_capital']:.2f}")
        
        return dna
    
    async def _update_bot_dna(self, bot_id: str, new_dna: dict):
        """Update bot with evolved DNA"""
        try:
            update_data = {
                "risk_mode": new_dna['risk_mode'],
                "trading_pair": new_dna.get('trading_pair', 'BTC/ZAR'),
                "initial_capital": new_dna['initial_capital'],
                "current_capital": new_dna['initial_capital'],
                "exchange": new_dna.get('exchange', 'luno'),
                "evolved_at": datetime.now(timezone.utc).isoformat(),
                "generation": self.generation
            }
            
            await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$set": update_data,
                    "$push": {
                        "evolution_history": {
                            "generation": self.generation,
                            "dna": new_dna,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    }
                }
            )
            
            logger.info(f"Bot {bot_id} evolved to generation {self.generation}")
            
        except Exception as e:
            logger.error(f"Bot DNA update failed: {e}")


# Global instance
bot_dna_evolution = BotDNAEvolution()
