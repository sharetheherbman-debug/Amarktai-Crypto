import ProfitsSection from './ProfitsSection';
import BotRadarSection from './BotRadarSection';
import CoinStatsPanel from './CoinStatsPanel';
import HuggingFacePanel from './HuggingFacePanel';

export default function PerformanceSection({ axiosConfig, ...performanceProps }) {
  return (
    <section className="section active">
      <ProfitsSection {...performanceProps} />
      <div className="subsection-gap">
        <BotRadarSection axiosConfig={axiosConfig} />
      </div>
      <div className="subsection-gap">
        <CoinStatsPanel axiosConfig={axiosConfig} />
      </div>
      <div className="subsection-gap">
        <HuggingFacePanel axiosConfig={axiosConfig} />
      </div>
    </section>
  );
}
