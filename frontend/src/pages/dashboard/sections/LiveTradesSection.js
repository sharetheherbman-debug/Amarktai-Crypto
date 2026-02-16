import SectionHeader from '@/ui/components/SectionHeader';
import { getPlatformDisplayName } from '../../../constants/platforms';

const NOT_AVAILABLE = 'Not available';
const formatZAR = (value, digits = 2, fallback = NOT_AVAILABLE) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  const formatted = Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${num < 0 ? '-R' : 'R'}${formatted}`;
};
const safeToFixed = (value, digits = 2, fallback = '0.00') => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : fallback;
};

export default function LiveTradesSection({
  recentTrades,
  selectedTradeId,
  setSelectedTradeId,
  setTradeBotFilter,
  setTradeExchangeFilter,
  setTradePairFilter,
  tradeBotFilter,
  tradeExchangeFilter,
  tradePairFilter,
}) {
  const exchanges = Array.from(new Set(recentTrades.map(trade => trade.exchange?.toLowerCase()).filter(Boolean)));
  const botsList = Array.from(new Set(recentTrades.map(trade => trade.bot_name).filter(Boolean)));
  const pairsList = Array.from(new Set(recentTrades.map(trade => trade.symbol).filter(Boolean)));

  const filteredTrades = recentTrades.filter((trade) => {
    const tradeExchange = trade.exchange?.toLowerCase();
    if (tradeExchangeFilter !== 'all' && tradeExchange !== tradeExchangeFilter) return false;
    if (tradeBotFilter !== 'all' && trade.bot_name !== tradeBotFilter) return false;
    if (tradePairFilter !== 'all' && trade.symbol !== tradePairFilter) return false;
    return true;
  });

  const resolvedTradeId = filteredTrades.some(trade => trade.id === selectedTradeId)
    ? selectedTradeId
    : filteredTrades[0]?.id;
  const selectedTrade = filteredTrades.find(trade => trade.id === resolvedTradeId) || null;

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="📊 Live Trades"
          subtitle="Track live executions and drill into order details."
        />

        <div className="trade-filters">
          <select value={tradeExchangeFilter} onChange={(e) => setTradeExchangeFilter(e.target.value)}>
            <option value="all">All Exchanges</option>
            {exchanges.map(exchange => (
              <option key={exchange} value={exchange}>{getPlatformDisplayName(exchange)}</option>
            ))}
          </select>
          <select value={tradeBotFilter} onChange={(e) => setTradeBotFilter(e.target.value)}>
            <option value="all">All Bots</option>
            {botsList.map(bot => (
              <option key={bot} value={bot}>{bot}</option>
            ))}
          </select>
          <select value={tradePairFilter} onChange={(e) => setTradePairFilter(e.target.value)}>
            <option value="all">All Pairs</option>
            {pairsList.map(pair => (
              <option key={pair} value={pair}>{pair}</option>
            ))}
          </select>
        </div>

        <div className="trade-feed-layout">
          <div className="trade-feed-list">
            {filteredTrades.length === 0 ? (
              <div className="live-trades-empty">
                <p>📭 No trades match this filter yet.</p>
              </div>
            ) : (
              filteredTrades.slice(0, 40).map((trade, idx) => {
                const isWin = trade.is_profitable || trade.profit_loss > 0;
                const side = (trade.side || trade.action || 'trade').toString().toLowerCase();
                const sideLabel = side === 'buy' || side === 'sell' ? side : 'trade';
                return (
                  <button
                    key={trade.id || trade.timestamp || `trade-${trade.symbol}-${idx}`}
                    type="button"
                    className={`trade-row ${resolvedTradeId === trade.id ? 'active' : ''}`}
                    onClick={() => setSelectedTradeId(trade.id)}
                  >
                    <div>
                      <strong>{trade.bot_name || 'Bot'}</strong>
                      <span>{trade.symbol || NOT_AVAILABLE}</span>
                    </div>
                    <div className="trade-row-meta">
                      <span className={`trade-side ${sideLabel}`}>{sideLabel}</span>
                      <span className={`trade-profit ${isWin ? 'win' : 'loss'}`}>
                        R{safeToFixed(trade.profit_loss, 2)}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>

          <div className="trade-detail-panel">
            {!selectedTrade ? (
              <div className="trade-empty-detail">Select a trade to see details.</div>
            ) : (
              <div className="trade-detail-card">
                <div className="trade-detail-header">
                  <div>
                    <h3>{selectedTrade.symbol || NOT_AVAILABLE}</h3>
                    <p>{selectedTrade.bot_name || 'Bot'} • {getPlatformDisplayName(selectedTrade.exchange?.toLowerCase())}</p>
                  </div>
                  <span>{new Date(selectedTrade.timestamp).toLocaleString()}</span>
                </div>
                <div className="trade-detail-grid">
                  <div>
                    <span>Side</span>
                    <strong>{selectedTrade.side || selectedTrade.action || 'Trade'}</strong>
                  </div>
                  <div>
                    <span>Price</span>
                    <strong>{formatZAR(selectedTrade.price || selectedTrade.avg_price)}</strong>
                  </div>
                  <div>
                    <span>Size</span>
                    <strong>{selectedTrade.size || selectedTrade.quantity || NOT_AVAILABLE}</strong>
                  </div>
                  <div>
                    <span>Fees</span>
                    <strong>{formatZAR(selectedTrade.fees || selectedTrade.fee)}</strong>
                  </div>
                  <div>
                    <span>Slippage</span>
                    <strong>{selectedTrade.slippage || NOT_AVAILABLE}</strong>
                  </div>
                  <div>
                    <span>Decision Trace</span>
                    <strong>{selectedTrade.reason || selectedTrade.decision_trace || NOT_AVAILABLE}</strong>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
